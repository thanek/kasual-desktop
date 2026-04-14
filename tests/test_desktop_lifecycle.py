"""
Testy cyklu życia Desktop: pause().
"""

from unittest.mock import MagicMock, patch


def _make_desktop(mock_gamepad):
    """Tworzy Desktop z minimalnym zestawem mocków."""
    wm = MagicMock()
    wm.windows_updated = MagicMock()
    wm.windows_updated.connect = MagicMock()
    wm.refresh_now = MagicMock()

    with patch("desktop.desktop.load_kde_wallpaper", return_value=None):
        from desktop import Desktop
        desktop = Desktop(apps=[], gamepad=mock_gamepad, window_manager=wm)
    return desktop


# ── pause() ───────────────────────────────────────────────────────────────────

class TestPause:
    def test_pause_pops_handler(self, mock_gamepad):
        desktop = _make_desktop(mock_gamepad)
        mock_gamepad.push_handler(desktop._handle_pad)
        desktop.pause()
        assert desktop._handle_pad not in mock_gamepad._handlers

    def test_pause_hides_widget(self, mock_gamepad):
        desktop = _make_desktop(mock_gamepad)
        desktop.show()
        desktop.pause()
        assert not desktop.isVisible()


# ── _on_app_finished ──────────────────────────────────────────────────────────

class TestOnAppFinished:
    """
    Desktop._on_app_finished powinien pokazać desktop tylko gdy jest niewidoczny
    (crash / samodzielne zamknięcie). Gdy użytkownik potwierdził zamknięcie,
    desktop jest już widoczny i nie powinien być pokazywany ponownie.
    """

    def test_shows_desktop_when_not_visible(self, mock_gamepad):
        """App zakończyła się sama — desktop niewidoczny → powinien się pokazać."""
        desktop = _make_desktop(mock_gamepad)
        assert not desktop.isVisible()

        desktop._on_app_finished(0)

        assert desktop.isVisible()
        assert desktop._handle_pad in mock_gamepad._handlers

    def test_does_not_push_handler_again_when_already_visible(self, mock_gamepad):
        """Użytkownik potwierdził zamknięcie — desktop już widoczny, handler już w stosie."""
        desktop = _make_desktop(mock_gamepad)
        mock_gamepad.push_handler(desktop._handle_pad)
        desktop.showFullScreen()

        handlers_before = list(mock_gamepad._handlers)
        desktop._on_app_finished(0)

        # handler nie powinien być dodany po raz drugi (push jest idempotentny,
        # ale liczymy, że liczba handlerów nie rośnie)
        assert mock_gamepad._handlers == handlers_before
