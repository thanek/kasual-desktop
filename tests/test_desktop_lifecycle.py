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
