"""Tests for LayerShellSurface — the keyboard-cede/return logic.

The layer-shell bindings are monkeypatched (no Wayland here); the widget is a real
offscreen top-level, so its map state is Qt's own.
"""

from PyQt6.QtWidgets import QWidget

import infrastructure.linux.wayland.surface as surface_mod
from infrastructure.linux.wayland.surface import LayerShellSurface
from infrastructure.common.qt.ui.layer_shell import Keyboard


def _make(qapp, monkeypatch, layered=True, cede_to_bottom=False):
    calls = {"keyboard": []}
    monkeypatch.setattr(surface_mod, "make_layer_surface",
                        lambda *_a, **_k: layered)

    def fake_set_keyboard(_w, kbd):
        calls["keyboard"].append(kbd)
        return True

    monkeypatch.setattr(surface_mod, "set_keyboard", fake_set_keyboard)
    surface = LayerShellSurface(cede_to_bottom=cede_to_bottom)
    widget = QWidget()
    surface.install(widget)
    return surface, widget, calls


class TestLayeredPath:
    def test_show_fullscreen_grabs_keyboard(self, qapp, monkeypatch):
        surface, widget, calls = _make(qapp, monkeypatch)
        surface.show_fullscreen()
        assert widget.isVisible() is True
        assert surface.is_visible() is True
        assert calls["keyboard"][-1] == Keyboard.ON_DEMAND

    def test_drop_below_keeps_widget_mapped(self, qapp, monkeypatch):
        surface, widget, calls = _make(qapp, monkeypatch)
        surface.show_fullscreen()
        surface.drop_below()
        assert widget.isVisible() is True      # still mapped on TOP
        assert surface.is_visible() is False   # logically ceded (no keyboard)
        assert calls["keyboard"][-1] == Keyboard.NONE

    def test_return_from_drop_below(self, qapp, monkeypatch):
        surface, widget, calls = _make(qapp, monkeypatch)
        surface.show_fullscreen()
        surface.drop_below()
        surface.show_fullscreen()
        assert surface.is_visible() is True
        assert calls["keyboard"][-1] == Keyboard.ON_DEMAND

    def test_hide_truly_unmaps(self, qapp, monkeypatch):
        surface, widget, _ = _make(qapp, monkeypatch)
        surface.show_fullscreen()
        surface.hide()
        assert widget.isVisible() is False
        assert surface.is_visible() is False

    def test_a_ceded_surface_is_still_on_screen(self, qapp, monkeypatch):
        surface, _, _ = _make(qapp, monkeypatch)
        surface.show_fullscreen()
        surface.drop_below()
        assert surface.is_on_screen() is True
        surface.hide()
        assert surface.is_on_screen() is False

    def test_drop_below_before_first_show_hides(self, qapp, monkeypatch):
        surface, widget, calls = _make(qapp, monkeypatch)
        surface.drop_below()
        assert widget.isVisible() is False


class TestSunkState:
    """is_sunk reports whether the ceded surface sits under the app's ordinary
    windows — what a behavioral test asserts on when a splash is up."""

    def test_ceded_surface_is_not_sunk_until_it_sinks(self, qapp, monkeypatch):
        surface, _, _ = _make(qapp, monkeypatch)
        surface.show_fullscreen()
        surface.drop_below()
        assert surface.is_sunk() is False
        surface.sink(True)
        assert surface.is_sunk() is True
        surface.sink(False)
        assert surface.is_sunk() is False

    def test_returning_to_the_front_unsinks(self, qapp, monkeypatch):
        surface, _, _ = _make(qapp, monkeypatch)
        surface.show_fullscreen()
        surface.drop_below()
        surface.sink(True)
        surface.show_fullscreen()
        assert surface.is_sunk() is False

    def test_ceding_to_bottom_is_already_sunk(self, qapp, monkeypatch):
        surface, _, _ = _make(qapp, monkeypatch, cede_to_bottom=True)
        surface.show_fullscreen()
        surface.drop_below()
        assert surface.is_sunk() is True

    def test_hide_clears_sunk(self, qapp, monkeypatch):
        surface, _, _ = _make(qapp, monkeypatch)
        surface.show_fullscreen()
        surface.drop_below()
        surface.sink(True)
        surface.hide()
        assert surface.is_sunk() is False


class TestDegradedPaths:
    def test_unlayered_drop_below_hides(self, qapp, monkeypatch):
        surface, widget, _ = _make(qapp, monkeypatch, layered=False)
        surface.show_fullscreen()
        surface.drop_below()
        assert widget.isVisible() is False
        assert surface.is_visible() is False

    def test_unlayered_surface_never_reports_sunk(self, qapp, monkeypatch):
        surface, _, _ = _make(qapp, monkeypatch, layered=False)
        surface.show_fullscreen()
        surface.drop_below()
        surface.sink(True)
        assert surface.is_sunk() is False