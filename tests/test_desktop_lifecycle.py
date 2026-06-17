"""
Testy cyklu życia Desktop: pause().
"""

from unittest.mock import MagicMock


class _NoWallpaper:
    """SystemWallpaper port returning nothing — Desktop paints the fallback."""

    def current(self):
        return None


class _FakeVolume:
    """VolumeControl port — no pactl I/O."""

    def get(self):
        return 50

    def set(self, percent):
        pass


class _FakeBrightness:
    """BrightnessControl port — no backend I/O."""

    def get(self):
        return 70

    def set(self, percent):
        pass


class _FakePower:
    """PowerControl port — no systemctl I/O."""

    def suspend(self): ...
    def reboot(self): ...
    def poweroff(self): ...


class _FakeScheduler:
    """Scheduler port — fires nothing (no QTimer)."""

    def call_later(self, delay_ms, callback):
        pass


def _make_desktop(mock_gamepad):
    """Tworzy Desktop z minimalnym zestawem mocków."""
    wm = MagicMock()
    wm.on_windows_updated = MagicMock()
    wm.refresh_now = MagicMock()

    from infrastructure.qt.desktop import build_desktop
    from infrastructure.system.app_manager import AppManager
    from domain.notifications.center import NotificationCenter
    return build_desktop(
        apps=[], gamepad=mock_gamepad, window_manager=wm,
        wallpaper=_NoWallpaper(), feedback=MagicMock(),
        volume=_FakeVolume(), brightness=_FakeBrightness(),
        power=_FakePower(), scheduler=_FakeScheduler(),
        process_manager=AppManager(), notifications=NotificationCenter(),
        network_control=MagicMock(),
        order_store=MagicMock(),
    )


# ── pause() ───────────────────────────────────────────────────────────────────

class TestPause:
    def test_pause_pops_handler(self, mock_gamepad):
        desktop = _make_desktop(mock_gamepad)
        mock_gamepad.push_handler(desktop._handle_pad)
        desktop.pause()
        assert desktop._handle_pad not in mock_gamepad._stack

    def test_pause_hides_widget(self, mock_gamepad):
        desktop = _make_desktop(mock_gamepad)
        desktop.show()
        desktop.pause()
        assert not desktop.isVisible()


# ── on_app_finished (via AppLifecycle) ──────────────────────────────────────────

class TestOnAppFinished:
    """
    AppLifecycle.on_app_finished powinien pokazać desktop tylko gdy jest
    niewidoczny (crash / samodzielne zamknięcie). Gdy użytkownik potwierdził
    zamknięcie, desktop jest już widoczny i nie powinien być pokazywany ponownie.

    Test integracyjny przez prawdziwy Desktop (DesktopView) + koordynator.
    """

    def test_shows_desktop_when_not_visible(self, mock_gamepad):
        """App zakończyła się sama — desktop niewidoczny → powinien się pokazać."""
        desktop = _make_desktop(mock_gamepad)
        assert not desktop.isVisible()

        desktop._lifecycle.on_app_finished(0)

        assert desktop.isVisible()
        assert desktop._handle_pad in mock_gamepad._stack

    def test_does_not_push_handler_again_when_already_visible(self, mock_gamepad):
        """Użytkownik potwierdził zamknięcie — desktop już widoczny, handler już w stosie."""
        desktop = _make_desktop(mock_gamepad)
        mock_gamepad.push_handler(desktop._handle_pad)
        desktop.showFullScreen()

        handlers_before = list(mock_gamepad._stack)
        desktop._lifecycle.on_app_finished(0)

        # handler nie powinien być dodany po raz drugi (push jest idempotentny,
        # ale liczymy, że liczba handlerów nie rośnie)
        assert list(mock_gamepad._stack) == handlers_before
