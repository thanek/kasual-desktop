"""Coordinates the launch / restore / close / exit flows for apps."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping

from domain.catalog.app import App
from domain.catalog.live_catalog import LiveCatalog
from domain.catalog.window_rules import is_app_running
from domain.input.vocabulary import Trigger
from domain.shell.foreground import ForegroundState
from domain.catalog.target import AppTarget, Target, WindowTarget
from domain.input.pad_control import PadControl
from domain.lifecycle.app_control import AppControl
from domain.lifecycle.cede_depth import CedeDepth
from domain.lifecycle.foreground_inspector import ForegroundInspector
from domain.lifecycle.launch_hide import LaunchHide
from domain.lifecycle.launch_show import LaunchShow
from domain.menu.entry import CLOSE, LAUNCH, RESTORE
from domain.menu.item import MenuItem
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.prompts import Prompts
from domain.lifecycle.tile_bar_view import TileBarView
from domain.lifecycle.window_arranger import WindowArranger
from domain.lifecycle.window_manager import WindowManager
from domain.shared.feedback import Cue, Feedback
from domain.shared.scheduler import Scheduler
from domain.shell.desktop_view import DesktopView

logger = logging.getLogger(__name__)

# A Steam forwarder exits the instant it hands the game to an already-running Steam;
# the game's own window can be a minute or more behind it — Steam's own progress is what
# belongs on the screen until then, so the Desktop stays ceded this long before taking it
# back. It keeps expecting the window either way, and cedes again whenever it maps.
_FORWARDER_CEDE_GRACE_MS = 120_000


class AppLifecycle(AppControl):
    def __init__(
        self,
        view: DesktopView,
        gamepad: PadControl,
        window_manager: WindowManager,
        app_manager: ProcessManager,
        apps: LiveCatalog,
        foreground: ForegroundState,
        deferred_hide: LaunchHide,
        deferred_show: LaunchShow,
        cede_depth: CedeDepth,
        tilebar: TileBarView,
        pad_handler: Callable[[str], None],
        scheduler: Scheduler,
        feedback: Feedback,
        prompts: Prompts,
        inspector: ForegroundInspector,
        is_paused: Callable[[], bool] = lambda: False,
        launch_env: Callable[[App], Mapping[str, str]] = lambda _app: {},
    ):
        self._view          = view
        self._gamepad       = gamepad
        self._wm            = window_manager
        self._app_manager   = app_manager
        self._arranger      = WindowArranger(window_manager, app_manager)
        self._apps          = apps
        self._foreground    = foreground
        self._deferred_hide = deferred_hide
        self._deferred_show = deferred_show
        self._cede_depth    = cede_depth
        self._tilebar       = tilebar
        self._pad_handler   = pad_handler
        self._scheduler     = scheduler
        self._feedback      = feedback
        self._prompts       = prompts
        self._inspector     = inspector
        self._is_paused     = is_paused
        self._launch_env    = launch_env
        self._pending_return: str | None = None
        self._awaited_launch: str | None = None

    def _app_by_id(self, app_id: str) -> App | None:
        return next((a for a in self._apps if a.id == app_id), None)

    def _index_by_id(self, app_id: str) -> int | None:
        return next((i for i, a in enumerate(self._apps) if a.id == app_id), None)

    def current_app(self) -> Target | None:
        return self._inspector.current_app()

    def foreground_pid(self) -> int | None:
        return self._inspector.foreground_pid()

    def foreground_is_game(self) -> bool:
        return self._inspector.foreground_is_game()

    # ── Launch / restore ────────────────────────────────────────────────────

    def _is_running(self, idx: int) -> bool:
        """Window-aware, so a Steam game whose forwarder exited but whose window is
        still up restores rather than relaunching."""
        return is_app_running(
            idx, self._apps, self._wm.cached_windows(), self._app_manager.is_running
        )

    def on_tile_activated(self, target: Target) -> None:
        # proc.poll() still reports a shutting-down app as running, so a restore
        # would activate a window that's about to disappear.
        if isinstance(target, AppTarget) and self._tilebar.is_closing(target.index):
            return
        # Whatever is picked now supersedes a launch still waiting for its window.
        self._awaited_launch = None
        self._foreground.set(target)
        if not isinstance(target, AppTarget):
            self.restore_app(target)
            return

        idx = target.index
        if self._is_running(idx):
            logger.info("Restoring application %s", target.app_id)
            self.restore_app(target)
        else:
            logger.info("Launching application %s", target.app_id)
            self._feedback.play(Cue.SELECT)
            # So other apps' virtual pads don't interfere.
            self.arrange_windows()
            app = self._apps[idx]
            self._gamepad.set_app_btn_mode_trigger(app.recall_menu_trigger)
            self._gamepad.pop_handler(self._pad_handler)
            # launch() reports immediate failure synchronously (the Desktop is
            # already reactivated); only arm the deferred hide on a real launch.
            env = {**self._launch_env(app), **app.env}   # app.env wins
            if self._app_manager.launch(app.id, app.command, app.args, env):
                # Defer the hide until the window maps, so no DE-desktop flash.
                self._deferred_hide.arm(app)
                self._deferred_show.arm(app)
                self._cede_depth.arm(app)

    def dispatch_tile_action(self, item: MenuItem) -> None:
        if item.action in (LAUNCH, RESTORE):
            self.on_tile_activated(item.target)
        elif item.action == CLOSE:
            self.request_close_app(item.target)

    def restore_app(self, target: Target) -> None:
        self._feedback.play(Cue.SELECT)
        if isinstance(target, AppTarget):
            app = self._apps[target.index]
            self._gamepad.set_app_btn_mode_trigger(app.recall_menu_trigger)
            self._arranger.raise_app(app)
            self._deferred_show.arm(app)
            self._cede_depth.arm(app)
        else:
            self._gamepad.set_app_btn_mode_trigger(target.trigger)
            self._wm.activate_window(target.window_id)
        self._gamepad.pop_handler(self._pad_handler)
        if self._target_is_fullscreen(target):
            self._view.hide_view()
        else:
            self._view.withdraw_view()

    def _target_is_fullscreen(self, target: Target) -> bool:
        """True if the restored app's/existing window covers the screen — KWin
        stacks such a window above layer-shell TOP, so ceding (staying mapped
        on TOP with Keyboard.NONE) keeps the app visible."""
        windows = self._wm.cached_windows()
        if isinstance(target, AppTarget):
            app = self._apps[target.index]
            return any(
                (w.pid != 0 and w.matches_app(app))
                and (w.fullscreen or w.covers_screen)
                for w in windows
            )
        return any(
            w.id == target.window_id and (w.fullscreen or w.covers_screen)
            for w in windows
        )

    def arrange_windows(self, activate_pid: int | None = None) -> None:
        self._arranger.arrange(activate_pid)

    # ── Closing an application ──────────────────────────────────────────────

    def request_close_app(self, target: Target) -> None:
        # Capture where Cancel should return to now, before the dialog changes it.
        from_desktop = self._view.is_visible()
        self._view.show_confirm(
            question=self._prompts.close_confirm(target.name),
            on_confirmed=lambda: self._close_confirmed(target),
            on_cancelled=lambda: self._close_cancelled(target, from_desktop),
        )

    def _close_confirmed(self, target: Target) -> None:
        self.restore_desktop_view()
        if isinstance(target, AppTarget):
            idx = target.index
            app = self._apps[idx]
            self._tilebar.set_static_closing(idx)
            if app.steam_app_id is not None:
                # Terminating the tracked process would quit all of Steam, not
                # the game; close the game's own window instead.
                self._close_app_windows(idx)
            elif self._app_manager.is_running(app.id):
                self._app_manager.terminate(app.id)
            else:
                # Forwarder-launched: no live process to kill, so close windows.
                self._close_app_windows(idx)
        else:
            self._foreground.clear()
            self._wm.close_window(target.window_id)
            self._scheduler.call_later(1000, self._wm.refresh_now)

    def _close_cancelled(self, target: Target, from_desktop: bool) -> None:
        if from_desktop:
            self.restore_desktop_view()
        else:
            self.restore_app(target)

    def _close_app_windows(self, idx: int) -> None:
        """Close a static app's windows by identity, for when no live process
        exists (forwarder-launched, so the real PID differs)."""
        app = self._apps[idx]
        matched = [w.id for w in self._wm.cached_windows() if w.matches_app(app)]
        logger.info("Closing app %d via windows %s (keys=%s)", idx, matched, app.window_match_keys)
        for win_id in matched:
            self._wm.close_window(win_id)
        self._scheduler.call_later(1500, self._wm.refresh_now)

    # ── Exit handling ───────────────────────────────────────────────────────

    def on_app_launch_failed(self, app_id: str, error: str) -> None:
        logger.warning("Application %s failed to launch: %s", app_id, error)
        # Keep the Desktop up for the error dialog.
        self._deferred_hide.cancel()
        # The optimistic foreground set in on_tile_activated never started, so
        # clear it or BTN_MODE would target the never-launched app.
        self._foreground.clear_if_app(app_id)
        self.reactivate_desktop()
        self._view.show_error(self._prompts.launch_failed(error))

    def on_app_finished(self, app_id: str) -> None:
        if self._forwarder_launch_in_flight(app_id):
            # A Steam forwarder hands the game to a running Steam and exits before the
            # game has drawn anything. Its exit is not the app ending: DeferredHide,
            # DeferredShow and CedeDepth are already armed and will cede once the
            # window maps and return once it is gone. Tearing down here would strand
            # KD's chrome over the game that maps a moment later.
            logger.info("%s forwarder handed off; awaiting the game's window", app_id)
            self._scheduler.call_later(
                _FORWARDER_CEDE_GRACE_MS,
                lambda: self._forwarder_cede_grace_elapsed(app_id))
            return

        logger.info("Application %s finished – returning to desktop", app_id)
        # Don't hide onto a closed app.
        self._deferred_hide.cancel()
        self._view.close_active_dialog()
        self._tilebar.refresh_status()
        self._wm.refresh_now()
        if self._still_windowed(app_id):
            # Forwarder launch (flatpak/single-instance): the process handed off
            # and exited, but its window lives on under another pid — not closed.
            # The refresh above is asynchronous, so this also reads a window that is
            # already dead; either way check_pending_return finishes what it started.
            logger.info("%s still has a window; deferring return to window-gone", app_id)
            self._pending_return = app_id
            return
        self._return_from(app_id)

    def check_pending_return(self) -> None:
        """Finish a return that waited on the app's window. Called on every refreshed
        window list — nothing else would, and the foreground would stay on an app that
        is gone, with the Home menu still offering to close it."""
        app_id = self._pending_return
        if app_id is not None and not self._still_windowed(app_id):
            logger.info("%s window gone – returning to desktop", app_id)
            self._return_from(app_id)

    def _return_from(self, app_id: str) -> None:
        self._pending_return = None
        self._deferred_show.cancel()
        self._cede_depth.cancel()
        self._foreground.clear_if_app(app_id)
        if not self._view.is_visible():
            self.reactivate_desktop()
        # Steam re-enumerates the gamepad on exit, leaving our evdev fd dead;
        # delay long enough for the kernel to surface the replacement.
        self._scheduler.call_later(1000, self._gamepad.refresh)

    def _still_windowed(self, app_id: str) -> bool:
        app = self._app_by_id(app_id)
        if app is None:
            return False
        return any(w.matches_app(app) for w in self._wm.cached_windows())

    def _forwarder_launch_in_flight(self, app_id: str) -> bool:
        """A Steam-forwarder tile whose game window has not mapped yet: the forwarder
        handed the launch to a running Steam and exited before the game drew anything,
        so its exit says nothing about whether the game is still coming.

        Four things have to hold, and the launch is over the moment any of them stops:
        the tile is still what is in front, the Desktop is still ceded to it, the game
        has never had a window under this launch, and it has none right now. That third
        one tells a handoff from an ending: a cold-started game tile *is* the Steam
        client, so its process ends when Steam quits, long after the game left the
        screen. Reading the armed *hide* instead would miss all three: it disarms itself
        a few seconds in whether or not a window ever came.
        """
        app = self._app_by_id(app_id)
        if app is None or app.steam_app_id is None:
            return False
        target = self._foreground.current
        return (isinstance(target, AppTarget) and target.app_id == app_id
                and self._deferred_show.is_armed
                and not self._deferred_show.has_seen_window
                and not self._still_windowed(app_id))

    def _forwarder_cede_grace_elapsed(self, app_id: str) -> None:
        """The game's window has not come yet — take the screen back rather than sit
        ceded behind nothing, and keep expecting it.

        The launch is re-checked rather than assumed: the grace outlives what it was
        armed for, and one belonging to a launch that has since ended would pull the
        screen out from under whatever is running now.
        """
        if not self._forwarder_launch_in_flight(app_id):
            return
        logger.info("%s window has not mapped; returning to the desktop to wait", app_id)
        self._deferred_hide.cancel()
        self._return_from(app_id)
        self._awaited_launch = app_id

    def check_awaited_launch(self) -> None:
        """Cede to a launch whose window outlived its grace — a game that spends minutes
        on shaders before it draws, over a Desktop that has already come back.

        Only while the Desktop is idle: once the user has put something else in front,
        the late window is no longer what they asked for.
        """
        app_id = self._awaited_launch
        if app_id is None or not self._foreground.is_idle():
            return
        index = self._index_by_id(app_id)
        if index is None or not self._still_windowed(app_id):
            return
        logger.info("%s window mapped after its grace – ceding to it", app_id)
        self._awaited_launch = None
        app = self._apps[index]
        target = AppTarget(index=index, app_id=app.id, name=app.name, is_game=app.is_game)
        self._foreground.set(target)
        self.restore_app(target)

    def check_active_dyn_gone(self) -> None:
        """Show the Desktop if the active dynamic window was closed by its app."""
        ctx = self._foreground.current
        if isinstance(ctx, WindowTarget):
            if not self._tilebar.has_dynamic_window(ctx.window_id):
                self._foreground.clear()
                # restore_app() popped our handler, so reclaim input — but only if
                # nobody else owns it (an open Home surface must keep receiving).
                top = self._gamepad.top_handler()
                if top is None or top == self._pad_handler:
                    self.reactivate_desktop()
                # Dyn apps skip on_app_finished, so force the same Steam rebind.
                self._scheduler.call_later(1000, self._gamepad.refresh)

    def on_app_windows_gone(self) -> None:
        """Take the screen back once the launched app has unmapped its last
        window, without waiting out its process teardown. A paused Desktop stays
        down: the user asked for the DE, not for us."""
        if self._is_paused():
            return
        # A forwarder's on_app_finished already fired without clearing this, so
        # drop the stale foreground as we take the screen back.
        self._foreground.clear()
        self.reactivate_desktop()

    # ── Focus / Reactivation ────────────────────────────────────────────────

    def on_focus_gained(self) -> None:
        """Reactivate the Desktop on regained focus, if it isn't paused, the
        foreground is idle and no gamepad handler is active. The pause check
        keeps a stray focus event from bouncing a minimized Desktop back."""
        if self._is_paused():
            return
        if self._foreground.is_idle() and self._gamepad.top_handler() is None:
            self.reactivate_desktop()

    def reactivate_desktop(self) -> None:
        """Restore Desktop input control and surface it. Idempotent. Resets the
        BTN_MODE trigger so no app-specific HOLD_1S lingers."""
        self._deferred_show.cancel()
        self._cede_depth.cancel()
        self._gamepad.set_app_btn_mode_trigger(Trigger.CLICK)
        self._gamepad.push_handler(self._pad_handler)
        if not self._gamepad.is_connected():
            # An app closing must not put the Desktop back on a screen with no
            # controller to drive it; reconnecting one surfaces it again. Input
            # control above is still restored, so it comes back ready.
            return
        if not self._view.is_visible():
            self._view.show_fullscreen()
        self._view.activate()

    def restore_desktop_view(self) -> None:
        self.reactivate_desktop()
        # Wayland can ignore activateWindow while a dying app holds focus.
        self._wm.raise_self()
