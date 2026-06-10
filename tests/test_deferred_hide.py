"""Tests for DeferredHide — the launch→hide state machine extracted from Desktop.

The window-detection and arm/cancel/guard logic was previously untested inside
the Desktop God Object. The KWinWindowManager and AppManager are mocked; QTimers
are created but never fire (no event loop) — methods are driven directly.
"""

from unittest.mock import MagicMock, patch

import pytest

from infrastructure.qt.desktop.deferred_hide import DeferredHide
from domain.catalog.app import App


def _make(apps=None, running_pid=None):
    wm = MagicMock()
    am = MagicMock()
    am.running_pid.return_value = running_pid
    apps = apps or [App(name="Foo", command="/usr/bin/foo")]
    on_hide = MagicMock()
    dh = DeferredHide(wm, am, apps, on_hide=on_hide)
    return dh, wm, am, on_hide


def _win(pid=0, rc="", df=""):
    return {"pid": pid, "resourceClass": rc, "desktopFile": df}


class TestAppWindowPresent:
    def test_matches_by_pid_subtree(self, qapp):
        dh, _, _, _ = _make(running_pid=1000)
        with patch("infrastructure.qt.desktop.deferred_hide.expand_pid_tree", return_value={1000, 1001}):
            assert dh._app_window_present(0, [_win(pid=1001)]) is True

    def test_matches_by_resource_class(self, qapp):
        dh, _, _, _ = _make(apps=[App(name="Foo", command="/usr/bin/foo")])
        assert dh._app_window_present(0, [_win(pid=9, rc="foo")]) is True

    def test_matches_by_desktop_file(self, qapp):
        dh, _, _, _ = _make(apps=[App(name="Foo", command="foo")])
        assert dh._app_window_present(0, [_win(pid=9, df="foo.desktop")]) is True

    def test_no_match(self, qapp):
        dh, _, _, _ = _make(apps=[App(name="Foo", command="foo")])
        assert dh._app_window_present(0, [_win(pid=9, rc="bar", df="baz.desktop")]) is False


class TestArmCancel:
    def test_arm_sets_armed_connects_and_refreshes(self, qapp):
        dh, wm, _, _ = _make()
        dh.arm(0)
        assert dh.is_armed is True
        wm.windows_updated.connect.assert_called_once()
        wm.refresh_now.assert_called()

    def test_cancel_clears(self, qapp):
        dh, _, _, _ = _make()
        dh.arm(0)
        dh.cancel()
        assert dh.is_armed is False

    def test_cancel_when_idle_is_noop(self, qapp):
        dh, _, _, _ = _make()
        dh.cancel()
        assert dh.is_armed is False

    def test_arm_rearms_cleanly(self, qapp):
        dh, _, _, _ = _make()
        dh.arm(0)
        dh.arm(0)   # cancel() inside arm() must not leave it stuck
        assert dh.is_armed is True


class TestHideTrigger:
    def test_hides_when_window_appears_without_grace(self, qapp):
        dh, _, _, on_hide = _make(apps=[App(name="Foo", command="foo")])
        dh.arm(0)
        dh._on_windows([_win(pid=1, rc="foo")])
        on_hide.assert_called_once()
        assert dh.is_armed is False

    def test_defers_hide_when_grace_configured(self, qapp):
        dh, _, _, on_hide = _make(
            apps=[App(name="Foo", command="foo", launch_hide_grace_ms=500)]
        )
        dh.arm(0)
        dh._on_windows([_win(pid=1, rc="foo")])
        on_hide.assert_not_called()   # waits for the grace timer to fire

    def test_no_hide_while_window_absent(self, qapp):
        dh, _, _, on_hide = _make(apps=[App(name="Foo", command="foo")])
        dh.arm(0)
        dh._on_windows([_win(pid=1, rc="bar")])
        on_hide.assert_not_called()
        assert dh.is_armed is True

    def test_guard_force_hides_without_a_window(self, qapp):
        dh, _, _, on_hide = _make()
        dh.arm(0)
        dh._force()   # safety-timeout path
        on_hide.assert_called_once()
        assert dh.is_armed is False
