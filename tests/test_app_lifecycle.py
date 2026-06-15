"""Tests for AppLifecycle — the launch / restore / close / exit coordinator
extracted from the Desktop (E2 of the refactoring roadmap).

Pure orchestration over injected fakes (DesktopView, Scheduler, Feedback,
Prompts) and mocked infra; no QWidget, no Qt event loop. The Scheduler fake just
records deferrals without firing them, matching production's singleShot timing
(callbacks never run mid-test).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from domain.input.vocabulary import Trigger
from domain.lifecycle.app_lifecycle import AppLifecycle
from domain.catalog.app import App
from domain.shell.foreground import ForegroundState
from domain.catalog.target import AppTarget, WindowTarget
from domain.catalog.window import Window


class FakeScheduler:
    """Records call_later deferrals without running the callbacks."""

    def __init__(self):
        self.calls: list[tuple[int, object]] = []

    def call_later(self, delay_ms: int, callback) -> None:
        self.calls.append((delay_ms, callback))


class FakePrompts:
    """Returns plain strings echoing the argument (no Qt translation)."""

    def close_confirm(self, name: str) -> str:
        return f"close? {name}"

    def launch_failed(self, error: str) -> str:
        return f"failed: {error}"


class FakeView:
    """In-memory DesktopView: tracks visibility and records dialog/error calls."""

    def __init__(self, visible: bool = False):
        self._visible = visible
        self.shown = 0
        self.activated = 0
        self.hidden = 0
        self.dialog_closed = 0
        self.errors: list[str] = []
        self.confirm: tuple | None = None

    def is_visible(self) -> bool:
        return self._visible

    def show_fullscreen(self) -> None:
        self._visible = True
        self.shown += 1

    def activate(self) -> None:
        self.activated += 1

    def hide_view(self) -> None:
        self._visible = False
        self.hidden += 1

    def close_active_dialog(self) -> None:
        self.dialog_closed += 1

    def show_error(self, message: str) -> None:
        self.errors.append(message)

    def show_confirm(self, question, on_confirmed, on_cancelled=None) -> None:
        self.confirm = (question, on_confirmed, on_cancelled)


def _app(command="prog", trigger=Trigger.CLICK):
    return App(name="App", command=command, recall_menu_trigger=trigger)


def _make(apps=None, visible=False):
    view = FakeView(visible=visible)
    gamepad = MagicMock()
    gamepad.top_handler.return_value = None
    wm = MagicMock()
    app_manager = MagicMock()
    apps = apps if apps is not None else [_app()]
    foreground = ForegroundState()
    deferred_hide = MagicMock()
    tilebar = MagicMock()
    tilebar.is_closing.return_value = False
    pad = object()  # sentinel pad-handler identity
    scheduler = FakeScheduler()
    feedback = MagicMock()
    prompts = FakePrompts()
    # Default: no open windows, so current_app() never overrides the foreground
    # unless a test sets cached_windows explicitly.
    wm.cached_windows.return_value = []
    lc = AppLifecycle(
        view=view,
        gamepad=gamepad,
        window_manager=wm,
        app_manager=app_manager,
        apps=apps,
        foreground=foreground,
        deferred_hide=deferred_hide,
        tilebar=tilebar,
        pad_handler=pad,
        scheduler=scheduler,
        feedback=feedback,
        prompts=prompts,
    )
    return SimpleNamespace(
        lc=lc, view=view, gamepad=gamepad, wm=wm, am=app_manager,
        apps=apps, fg=foreground, dh=deferred_hide, tilebar=tilebar, pad=pad,
        scheduler=scheduler, feedback=feedback, prompts=prompts,
    )


# ── current_app ─────────────────────────────────────────────────────────────

class TestCurrentApp:
    def test_idle_is_none(self):
        c = _make()
        assert c.lc.current_app() is None

    def test_plain_app_returned_when_no_spawned_window(self):
        c = _make()
        target = AppTarget(index=0, name="App")
        c.fg.set(target)
        c.am.running_pid.return_value = 100
        c.wm.cached_windows.return_value = []
        assert c.lc.current_app() == target

    def test_active_unmanaged_window_reports_it(self):
        """Steam (foreground) launched a game in its own window — a window that
        matches no app tile: BTN_MODE should target the game, inheriting Steam's
        recall trigger."""
        c = _make(apps=[_app(command="steam", trigger=Trigger.HOLD_1S)])
        c.fg.set(AppTarget(index=0, name="Steam"))
        c.wm.cached_windows.return_value = [
            Window(id="g1", title="Witcher 3", pid=200, active=True,
                   resource_class="steam_app_292030"),
            Window(id="s1", title="Steam", pid=100, active=False,
                   resource_class="steam"),
        ]
        result = c.lc.current_app()
        assert result == WindowTarget(
            window_id="g1", name="Witcher 3", trigger=Trigger.HOLD_1S
        )

    def test_own_window_active_keeps_app_target(self):
        """Steam's own window is active → it matches the Steam tile, no override."""
        c = _make(apps=[_app(command="steam")])
        target = AppTarget(index=0, name="Steam")
        c.fg.set(target)
        c.wm.cached_windows.return_value = [
            Window(id="s1", title="Steam", pid=100, active=True,
                   resource_class="steam"),
        ]
        assert c.lc.current_app() == target

    def test_no_active_window_keeps_app_target(self):
        c = _make(apps=[_app(command="steam")])
        target = AppTarget(index=0, name="Steam")
        c.fg.set(target)
        c.wm.cached_windows.return_value = [
            Window(id="s1", title="Steam", pid=100, active=False,
                   resource_class="steam"),
        ]
        assert c.lc.current_app() == target

    def test_window_target_foreground_passes_through(self):
        c = _make()
        target = WindowTarget(window_id="w1", name="Win", trigger=Trigger.CLICK)
        c.fg.set(target)
        assert c.lc.current_app() == target


# ── on_tile_activated ───────────────────────────────────────────────────────

class TestOnTileActivated:
    def test_window_target_restores(self):
        c = _make()
        target = WindowTarget(window_id="w1", name="Win", trigger=Trigger.CLICK)
        c.lc.on_tile_activated(target)
        # restore path: foreground set, window activated, handler popped, view hidden
        assert c.fg.current == target
        c.wm.activate_window.assert_called_once_with("w1")
        c.gamepad.pop_handler.assert_called_once_with(c.pad)
        assert c.view.hidden == 1
        c.dh.arm.assert_not_called()

    def test_running_app_restores_not_launches(self):
        c = _make()
        c.am.is_running.return_value = True
        c.lc.on_tile_activated(AppTarget(index=0, name="App"))
        c.am.launch.assert_not_called()
        assert c.view.hidden == 1  # restore hides the desktop

    def test_idle_app_launches_and_arms_hide(self):
        c = _make(apps=[_app(trigger=Trigger.HOLD_1S)])
        c.am.is_running.return_value = False
        c.am.launch.return_value = True
        c.lc.on_tile_activated(AppTarget(index=0, name="App"))
        app = c.apps[0]
        c.am.launch.assert_called_once_with(0, app.command, app.args, app.env)
        c.gamepad.set_app_btn_mode_trigger.assert_called_with(Trigger.HOLD_1S)
        c.gamepad.pop_handler.assert_called_once_with(c.pad)
        c.dh.arm.assert_called_once_with(0)

    def test_failed_launch_does_not_arm_hide(self):
        c = _make()
        c.am.is_running.return_value = False
        c.am.launch.return_value = False
        c.lc.on_tile_activated(AppTarget(index=0, name="App"))
        c.dh.arm.assert_not_called()

    def test_closing_app_activation_is_ignored(self):
        """Activating an app tile mid-shutdown is a no-op (the relocated guard)."""
        c = _make()
        c.tilebar.is_closing.return_value = True
        c.lc.on_tile_activated(AppTarget(index=0, name="App"))
        assert c.fg.is_idle()              # foreground untouched
        c.am.launch.assert_not_called()
        c.am.is_running.assert_not_called()
        assert c.view.hidden == 0


# ── dispatch_tile_action (tile Popover) ──────────────────────────────────────

class TestDispatchTileAction:
    def test_launch_activates_target(self):
        from domain.menu.entry import LAUNCH
        from domain.menu.item import MenuItem
        c = _make()
        c.am.is_running.return_value = False
        c.am.launch.return_value = True
        target = AppTarget(index=0, name="App")
        c.lc.dispatch_tile_action(MenuItem("Launch", LAUNCH, target=target))
        c.am.launch.assert_called_once()
        assert c.fg.current == target

    def test_restore_activates_target(self):
        from domain.menu.entry import RESTORE
        from domain.menu.item import MenuItem
        c = _make()
        c.am.is_running.return_value = True
        target = AppTarget(index=0, name="App")
        c.lc.dispatch_tile_action(MenuItem("Restore", RESTORE, target=target))
        assert c.view.hidden == 1          # restore hides the desktop

    def test_close_requests_close(self):
        from domain.menu.entry import CLOSE
        from domain.menu.item import MenuItem
        c = _make()
        target = AppTarget(index=0, name="App")
        c.lc.dispatch_tile_action(MenuItem("Close", CLOSE, target=target))
        assert c.view.confirm is not None  # request_close_app opened a confirm


# ── restore_app ─────────────────────────────────────────────────────────────

class TestRestoreApp:
    def test_app_target_uses_app_trigger_and_arranges(self):
        c = _make(apps=[_app(trigger=Trigger.HOLD_1S)])
        c.am.running_pid.return_value = 4321
        c.lc.restore_app(AppTarget(index=0, name="App"))
        c.gamepad.set_app_btn_mode_trigger.assert_called_once_with(Trigger.HOLD_1S)
        c.wm.activate_windows_for_pids.assert_called_once_with({4321})
        c.gamepad.pop_handler.assert_called_once_with(c.pad)
        assert c.view.hidden == 1

    def test_window_target_uses_own_trigger(self):
        c = _make()
        target = WindowTarget(window_id="w9", name="Win", trigger=Trigger.HOLD_1S)
        c.lc.restore_app(target)
        c.gamepad.set_app_btn_mode_trigger.assert_called_once_with(Trigger.HOLD_1S)
        c.wm.activate_window.assert_called_once_with("w9")
        assert c.view.hidden == 1


# ── arrange_windows ─────────────────────────────────────────────────────────

class TestArrangeWindows:
    def test_activates_target_and_minimizes_others(self):
        c = _make()
        c.am.all_running_pids.return_value = [100, 200, 300]
        c.lc.arrange_windows(activate_pid=200)
        c.wm.activate_windows_for_pids.assert_called_once_with({200})
        c.wm.minimize_windows_for_pids.assert_called_once_with({100, 300})

    def test_no_target_minimizes_all_running(self):
        c = _make()
        c.am.all_running_pids.return_value = [100, 200]
        c.lc.arrange_windows()
        c.wm.activate_windows_for_pids.assert_not_called()
        c.wm.minimize_windows_for_pids.assert_called_once_with({100, 200})

    def test_nothing_running_is_noop(self):
        c = _make()
        c.am.all_running_pids.return_value = []
        c.lc.arrange_windows(activate_pid=7)
        c.wm.minimize_windows_for_pids.assert_not_called()


# ── on_app_finished ─────────────────────────────────────────────────────────

class TestOnAppFinished:
    def test_reactivates_when_hidden(self):
        c = _make(visible=False)
        c.fg.set(AppTarget(index=0, name="App"))
        c.lc.on_app_finished(0)
        c.dh.cancel.assert_called_once()
        assert c.view.dialog_closed == 1
        assert c.view.shown == 1          # desktop brought back
        assert c.fg.is_idle()             # foreground cleared (was app 0)
        c.gamepad.push_handler.assert_called_with(c.pad)

    def test_does_not_reshow_when_visible(self):
        c = _make(visible=True)
        c.fg.set(AppTarget(index=0, name="App"))
        c.lc.on_app_finished(0)
        assert c.view.shown == 0          # already visible — no re-show
        c.gamepad.push_handler.assert_not_called()

    def test_keeps_foreground_for_other_app(self):
        c = _make(visible=True)
        c.fg.set(AppTarget(index=2, name="Other"))
        c.lc.on_app_finished(0)           # a different app exited
        assert c.fg.current == AppTarget(index=2, name="Other")


# ── on_app_launch_failed ────────────────────────────────────────────────────

class TestOnAppLaunchFailed:
    def test_cancels_hide_clears_fg_and_shows_error(self):
        c = _make(visible=False)
        c.fg.set(AppTarget(index=0, name="App"))
        c.lc.on_app_launch_failed(0, "command not found")
        c.dh.cancel.assert_called_once()
        assert c.fg.is_idle()
        assert c.view.shown == 1          # reactivated for the dialog
        assert len(c.view.errors) == 1
        assert "command not found" in c.view.errors[0]


# ── check_active_dyn_gone ───────────────────────────────────────────────────

class TestCheckActiveDynGone:
    def test_clears_and_reactivates_when_window_gone(self):
        c = _make(visible=True)
        c.tilebar.has_dynamic_window.return_value = False
        c.gamepad.top_handler.return_value = c.pad  # we own the stack
        c.fg.set(WindowTarget(window_id="w1", name="Win"))
        c.lc.check_active_dyn_gone()
        assert c.fg.is_idle()
        assert c.view.activated == 1

    def test_noop_when_window_still_present(self):
        c = _make(visible=True)
        c.tilebar.has_dynamic_window.return_value = True
        c.fg.set(WindowTarget(window_id="w1", name="Win"))
        c.lc.check_active_dyn_gone()
        assert c.fg.current == WindowTarget(window_id="w1", name="Win")
        assert c.view.activated == 0

    def test_noop_when_foreground_is_app(self):
        c = _make(visible=True)
        c.fg.set(AppTarget(index=0, name="App"))
        c.lc.check_active_dyn_gone()
        c.tilebar.has_dynamic_window.assert_not_called()

    def test_does_not_steal_handler_owned_by_overlay(self):
        c = _make(visible=True)
        c.tilebar.has_dynamic_window.return_value = False
        c.gamepad.top_handler.return_value = object()  # someone else on top
        c.fg.set(WindowTarget(window_id="w1", name="Win"))
        c.lc.check_active_dyn_gone()
        assert c.fg.is_idle()             # still drops the dead window
        assert c.view.activated == 0      # but does not reactivate


# ── request_close_app ───────────────────────────────────────────────────────

class TestRequestCloseApp:
    def test_opens_confirm_dialog(self):
        c = _make()
        c.lc.request_close_app(AppTarget(index=0, name="App"))
        assert c.view.confirm is not None

    def test_confirm_terminates_running_app(self):
        c = _make(visible=True)
        c.am.is_running.return_value = True
        c.lc.request_close_app(AppTarget(index=0, name="App"))
        _, on_confirmed, _ = c.view.confirm
        on_confirmed()
        c.tilebar.set_static_closing.assert_called_once_with(0)
        c.am.terminate.assert_called_once_with(0)

    def test_confirm_closes_windows_when_no_live_process(self):
        c = _make(apps=[_app(command="/usr/bin/steam")])
        c.am.is_running.return_value = False
        c.wm.cached_windows.return_value = [
            Window(id="win1", title="", resource_class="Steam"),
            Window(id="win2", title="", resource_class="other"),
        ]
        c.lc.request_close_app(AppTarget(index=0, name="Steam"))
        _, on_confirmed, _ = c.view.confirm
        on_confirmed()
        c.am.terminate.assert_not_called()
        c.wm.close_window.assert_called_once_with("win1")

    def test_confirm_closes_window_target(self):
        c = _make()
        target = WindowTarget(window_id="w5", name="Win")
        c.fg.set(target)
        c.lc.request_close_app(target)
        _, on_confirmed, _ = c.view.confirm
        on_confirmed()
        c.wm.close_window.assert_called_once_with("w5")
        assert c.fg.is_idle()

    def test_cancel_from_desktop_restores_view(self):
        c = _make(visible=True)            # opened from the tile menu
        c.lc.request_close_app(AppTarget(index=0, name="App"))
        _, _, on_cancelled = c.view.confirm
        on_cancelled()
        # restore_desktop_view path raises the desktop via KWin
        c.wm.raise_self.assert_called_once()
        assert c.view.hidden == 0

    def test_cancel_over_app_restores_app(self):
        c = _make(visible=False)           # overlay opened over the running app
        c.am.is_running.return_value = True
        c.lc.request_close_app(AppTarget(index=0, name="App"))
        _, _, on_cancelled = c.view.confirm
        on_cancelled()
        assert c.view.hidden == 1          # restore_app hides the desktop again
