"""Routing of the Escape key in Desktop.eventFilter.

Escape has three jobs depending on context, all resolved by the same filter:

  * tiles mode, Desktop owns the pad  → open Home overlay (ESCAPE_HOME)
  * an overlay is open                → close it (falls through to CANCEL)
  * topbar mode                       → return to tiles (falls through to CANCEL)

The last two rely on Escape *not* being hijacked into ESCAPE_HOME. Layer-shell
overlays keep the Desktop the active Qt window (keyboard=NONE, no
activateWindow), so this app-wide filter keeps firing while one is open — the
top_handler guard is what lets Escape reach CANCEL then. We exercise the filter
with a stand-in ``self`` so no QApplication is needed.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt, QEvent

from infrastructure.qt.desktop.desktop import Desktop
from domain.input.vocabulary import Event


def _key_event(key):
    return SimpleNamespace(type=lambda: QEvent.Type.KeyPress, key=lambda: key)


def _desktop(*, active=True, in_tiles=True, overlay_on_top=False):
    """A minimal stand-in exposing only what eventFilter touches."""
    handle_pad = object()                       # the Desktop's own pad handler
    top = object() if overlay_on_top else handle_pad
    return SimpleNamespace(
        isActiveWindow=lambda: active,
        _nav=SimpleNamespace(in_tiles=in_tiles),
        _gamepad=MagicMock(**{"top_handler.return_value": top}),
        _handle_pad=handle_pad,
    )


def _filter(d, key=Qt.Key.Key_Escape):
    return Desktop.eventFilter(d, MagicMock(), _key_event(key))


class TestEscapeRouting:
    def test_tiles_and_desktop_owns_pad_opens_home(self):
        d = _desktop(in_tiles=True, overlay_on_top=False)
        assert _filter(d) is True
        d._gamepad.inject.assert_called_once_with(Event.ESCAPE_HOME)

    def test_overlay_on_top_falls_through_to_cancel(self):
        # The regression guard: an open overlay sits on top of the pad stack, so
        # Escape must close it (CANCEL), not open the Home overlay.
        d = _desktop(in_tiles=True, overlay_on_top=True)
        assert _filter(d) is True
        d._gamepad.inject.assert_called_once_with(Event.CANCEL)

    def test_topbar_mode_falls_through_to_cancel(self):
        d = _desktop(in_tiles=False, overlay_on_top=False)
        assert _filter(d) is True
        d._gamepad.inject.assert_called_once_with(Event.CANCEL)

    def test_inactive_window_ignored(self):
        d = _desktop(active=False)
        assert _filter(d) is False
        d._gamepad.inject.assert_not_called()
