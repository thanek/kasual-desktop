"""App-lifecycle coordinator — the launch / restore / finish / close flows
extracted from the Desktop view.

This is the application-layer orchestration that used to live inline on the
`Desktop` God Object: deciding when to launch vs restore an app, what to do when
one exits or fails, and how to seize/cede gamepad control and the foreground
state around all of that. It drives the Qt side exclusively through the
`DesktopView` port (show/hide/activate, dialogs), so the branching logic is
testable against a fake view rather than a live QWidget.

The Desktop keeps ownership of the gamepad pad-handler identity: it passes its
own `_handle_pad` bound method in as `pad_handler` so push/pop/compare on the
gamepad handler stack stays consistent with the rest of the widget.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from domain.catalog.catalog import AppCatalog
from domain.input.vocabulary import Trigger
from domain.shell.foreground import ForegroundState
from domain.catalog.target import AppTarget, Target, WindowTarget
from domain.input.pad_control import PadControl
from domain.lifecycle.app_control import AppControl
from domain.lifecycle.launch_hide import LaunchHide
from domain.menu.entry import CLOSE, LAUNCH, RESTORE
from domain.menu.item import MenuItem
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.prompts import Prompts
from domain.lifecycle.tile_bar_view import TileBarView
from domain.lifecycle.window_manager import WindowManager
from domain.shared.feedback import Cue, Feedback
from domain.shared.scheduler import Scheduler
from domain.shell.desktop_view import DesktopView

logger = logging.getLogger(__name__)


class AppLifecycle(AppControl):
    """Coordinates launching, restoring, closing and exit-handling of apps.

    Owns no Qt widgets; reads/writes the shared `ForegroundState` and drives the
    Desktop through the `DesktopView` port. Implements `AppControl`, the port the
    `Application` controller drives for foreground-app operations.
    """

    def __init__(
        self,
        view: DesktopView,
        gamepad: PadControl,
        window_manager: WindowManager,
        app_manager: ProcessManager,
        apps: AppCatalog,
        foreground: ForegroundState,
        deferred_hide: LaunchHide,
        tilebar: TileBarView,
        pad_handler: Callable[[str], None],
        scheduler: Scheduler,
        feedback: Feedback,
        prompts: Prompts,
    ):
        self._view          = view
        self._gamepad       = gamepad
        self._wm            = window_manager
        self._app_manager   = app_manager
        self._apps          = apps
        self._foreground    = foreground
        self._deferred_hide = deferred_hide
        self._tilebar       = tilebar
        self._pad_handler   = pad_handler
        self._scheduler     = scheduler
        self._feedback      = feedback
        self._prompts       = prompts

    # ── AppControl queries (driven by the Application controller) ────────────

    def current_app(self) -> Target | None:
        """The foreground Target, or None on the bare Desktop."""
        return self._foreground.current

    def foreground_pid(self) -> int | None:
        """OS pid of the foreground app, if one is a running App tile."""
        target = self._foreground.current
        if isinstance(target, AppTarget):
            return self._app_manager.running_pid(target.index)
        return None

    # ── Launch / restore ────────────────────────────────────────────────────

    def on_tile_activated(self, target: Target) -> None:
        """A tile (static app or open window) was chosen via gamepad, click or
        the tile Popover."""
        # Ignore activation while a static app is shutting down — proc.poll() still
        # reports it as running, so a restore would hide the Desktop and try to
        # activate a window that's about to disappear. Covers every activation
        # path (click / select_current / popover) at the single domain entry.
        if isinstance(target, AppTarget) and self._tilebar.is_closing(target.index):
            return
        self._foreground.set(target)
        if not isinstance(target, AppTarget):
            self.restore_app(target)
            return

        idx = target.index
        if self._app_manager.is_running(idx):
            logger.info("Restoring application %d", idx)
            self.restore_app(target)
        else:
            logger.info("Launching application %d", idx)
            self._feedback.play(Cue.SELECT)
            # Minimize other already-running apps to prevent virtual pad interference
            self.arrange_windows()
            trigger = self._apps[idx].recall_menu_trigger
            self._gamepad.set_app_btn_mode_trigger(trigger)
            self._gamepad.pop_handler(self._pad_handler)
            # launch() reports an immediate failure (e.g. command not found)
            # synchronously via app_launch_failed — on_app_launch_failed has
            # already reactivated the Desktop and shown the error by the time
            # this returns False. Only arm the deferred hide for a real launch;
            # arming it for a failed one would strand a window-poll + 5 s guard
            # that later hides the Desktop and churns the tile selection.
            app = self._apps[idx]
            if self._app_manager.launch(idx, app.command, app.args, app.env):
                # The Desktop is a top-layer surface and must be hidden for the
                # windowed app to show — but we defer that until the app's window
                # is actually mapped, so the DE desktop never flashes through the
                # start-up gap. Re-shown by on_app_finished.
                self._deferred_hide.arm(idx)

    def dispatch_tile_action(self, item: MenuItem) -> None:
        """Perform the behaviour for an activated tile-Popover item — the twin of
        the Home Overlay's dispatch, kept in the domain rather than the widget."""
        if item.action in (LAUNCH, RESTORE):
            self.on_tile_activated(item.target)
        elif item.action == CLOSE:
            self.request_close_app(item.target)

    def restore_app(self, target: Target) -> None:
        self._feedback.play(Cue.SELECT)
        if isinstance(target, AppTarget):
            idx = target.index
            trigger = self._apps[idx].recall_menu_trigger
            self._gamepad.set_app_btn_mode_trigger(trigger)
            self.arrange_windows(self._app_manager.running_pid(idx))
        else:
            self._gamepad.set_app_btn_mode_trigger(target.trigger)
            self._wm.activate_window(target.window_id)
        self._gamepad.pop_handler(self._pad_handler)
        self._view.hide_view()

    def arrange_windows(self, activate_pid: int | None = None) -> None:
        """Activate windows for activate_pid and minimize all other running apps."""
        all_pids = set(self._app_manager.all_running_pids())
        if activate_pid:
            self._wm.activate_windows_for_pids({activate_pid})
        other_pids = all_pids - ({activate_pid} if activate_pid else set())
        if other_pids:
            self._wm.minimize_windows_for_pids(other_pids)

    # ── Closing an application ──────────────────────────────────────────────

    def request_close_app(self, target: Target) -> None:
        # Where the close was triggered from decides where Cancel returns to:
        # the Desktop (tile menu, KD visible) or the running app (overlay opened
        # over it, KD hidden). Captured now, before the dialog changes anything.
        from_desktop = self._view.is_visible()

        def _confirmed() -> None:
            self.restore_desktop_view()
            if isinstance(target, AppTarget):
                idx = target.index
                self._tilebar.set_static_closing(idx)
                if self._app_manager.is_running(idx):
                    self._app_manager.terminate(idx)
                else:
                    # App was launched via a forwarder (e.g. `steam steam://...`)
                    # whose launcher process has already exited — AppManager has
                    # no live process to kill. Close matching KWin windows instead.
                    self._close_app_windows(idx)
            else:
                self._foreground.clear()
                self._wm.close_window(target.window_id)
                self._scheduler.call_later(1000, self._wm.refresh_now)

        def _cancelled() -> None:
            # Cancelling closes the dialog without consequences: return to the
            # context the user came from rather than yanking up the Desktop.
            if from_desktop:
                self.restore_desktop_view()
            else:
                self.restore_app(target)

        self._view.show_confirm(
            question=self._prompts.close_confirm(target.name),
            on_confirmed=_confirmed,
            on_cancelled=_cancelled,
        )

    def _close_app_windows(self, idx: int) -> None:
        """Close all windows belonging to a static app, matched by app identity.

        Used when the process manager has no live process for the app — e.g. apps
        started via a one-shot forwarder (steam://...) whose launcher exits
        immediately while the real process continues under a different PID.
        """
        app = self._apps[idx]
        matched = [w.id for w in self._wm.cached_windows() if w.matches_app(app)]
        logger.info("Closing app %d via windows %s (cmd=%s)", idx, matched, app.command_basename)
        for win_id in matched:
            self._wm.close_window(win_id)
        self._scheduler.call_later(1500, self._wm.refresh_now)

    # ── Exit handling ───────────────────────────────────────────────────────

    def on_app_launch_failed(self, idx: int, error: str) -> None:
        logger.warning("Application %d failed to launch: %s", idx, error)
        # Launch failed before any window: drop the pending hide so the Desktop
        # stays up for the error dialog instead of vanishing.
        self._deferred_hide.cancel()
        # on_tile_activated set the foreground optimistically when the tile was
        # chosen; the app never started, so clear it (if it is still ours).
        # Otherwise BTN_MODE would target the never-launched app instead of
        # opening the general Home Overlay.
        self._foreground.clear_if_app(idx)
        self.reactivate_desktop()
        self._view.show_error(self._prompts.launch_failed(error))

    def on_app_finished(self, idx: int) -> None:
        logger.info("Application %d finished – returning to desktop", idx)
        # App exited (possibly before its window ever mapped) — stop waiting to
        # hide the Desktop, otherwise we would hide onto a closed app.
        self._deferred_hide.cancel()
        self._view.close_active_dialog()
        self._tilebar.refresh_status()
        self._wm.refresh_now()
        # Drop back to the Desktop if the app that exited was in front.
        self._foreground.clear_if_app(idx)
        if not self._view.is_visible():
            # App exited on its own (crash / self-close) — show desktop now
            self.reactivate_desktop()
        # Some apps (notably Steam) re-enumerate the gamepad on exit,
        # leaving our evdev fd pointing at a dead device with no error.
        # Delay long enough for the kernel to surface the replacement.
        self._scheduler.call_later(1000, self._gamepad.refresh)

    def check_active_dyn_gone(self) -> None:
        """If the active dynamic window disappeared (closed by the app) → show desktop."""
        ctx = self._foreground.current
        if isinstance(ctx, WindowTarget):
            if not self._tilebar.has_dynamic_window(ctx.window_id):
                self._foreground.clear()
                # Re-establish gamepad control even when the Desktop window is
                # already visible: restore_app() popped our handler, so a bare
                # visible window would leave the pad unresponsive. Only seize
                # input if nobody else owns it (an open HomeOverlay sits on top
                # of the handler stack and must keep receiving events).
                top = self._gamepad.top_handler()
                if top is None or top == self._pad_handler:
                    self.reactivate_desktop()
                # Some apps (notably Steam) re-enumerate the gamepad when they
                # exit, silently invalidating our evdev fd. Externally-launched
                # (dyn) apps don't go through on_app_finished, so force the
                # rebind here too — same delay as the AppManager path.
                self._scheduler.call_later(1000, self._gamepad.refresh)

    # ── Focus / Reactivation ────────────────────────────────────────────────

    def on_focus_gained(self) -> None:
        """Decide whether to reactivate the desktop after the window regains focus.

        Called from the Qt event loop when the Desktop window regains activation
        (e.g. after the app that ceded pad control has closed).  The decision
        logic — *foreground idle AND no gamepad handler active* — lives here so
        the infrastructure layer only signals the event.
        """
        if self._foreground.is_idle() and self._gamepad.top_handler() is None:
            self.reactivate_desktop()

    def reactivate_desktop(self) -> None:
        """Restore Desktop input control and bring it to the front.

        Idempotent: push_handler() moves our handler to the top if it is already
        present, and the window is only re-shown when actually hidden. The
        BTN_MODE trigger is reset to the Desktop default so no app-specific
        HOLD_1S setting lingers after the app is gone.
        """
        self._gamepad.set_app_btn_mode_trigger(Trigger.CLICK)
        self._gamepad.push_handler(self._pad_handler)
        if not self._view.is_visible():
            self._view.show_fullscreen()
        self._view.activate()

    def restore_desktop_view(self) -> None:
        self.reactivate_desktop()
        # Wayland focus-stealing prevention can ignore Qt's activateWindow
        # when another app (still dying) holds focus. Force Desktop to the
        # top of the stack via KWin scripting.
        self._wm.raise_self()
