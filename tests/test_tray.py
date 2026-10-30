"""Tests for the system tray icon and how its icon source is chosen.

The COSMIC case is the reason the source is injectable at all: its status area
renders a StatusNotifierItem's ``IconName`` and ignores a pixmap-only item, so a
Font Awesome glyph is invisible there.
"""

from unittest.mock import patch

import pytest

from domain.display.display import SYSTEM_DECIDES, Display
from infrastructure.common.qt.ui.tray import SystemTray, glyph_icon, themed_icon


class FakeDisplays:
    def __init__(self, options=(), chosen=SYSTEM_DECIDES):
        self._options = list(options)
        self._chosen = chosen
        self.choices = []

    def options(self):
        return self._options

    def chosen(self):
        return self._chosen

    def choose(self, display_id):
        self.choices.append(display_id)
        self._chosen = display_id


@pytest.fixture
def tray(qapp):
    def build(icon_for=glyph_icon, displays=None):
        recorded = {'shown': 0, 'quit': 0}
        tray = SystemTray(
            on_show=lambda: recorded.__setitem__('shown', recorded['shown'] + 1),
            on_logs=lambda: None,
            on_about=lambda: None,
            on_quit=lambda: recorded.__setitem__('quit', recorded['quit'] + 1),
            displays=displays or FakeDisplays(),
            icon_for=icon_for,
        )
        return tray, recorded
    return build


class TestIconSource:
    def test_uses_the_injected_source_for_each_state(self, tray):
        asked = []
        widget, _ = tray(lambda connected: (asked.append(connected), glyph_icon(connected))[1])
        widget.set_connected(True)
        widget.set_connected(False)
        assert asked == [False, True, False]   # the initial icon, then both updates

    def test_glyph_icon_carries_no_theme_name(self):
        # Which is exactly why COSMIC cannot render it: Qt then publishes only
        # IconPixmap, and the status area has nothing to look up.
        assert glyph_icon(True).name() == ""

    def test_themed_icon_carries_a_theme_name(self, qapp):
        icon = themed_icon(True)
        if icon.name() == "":
            pytest.skip("no input-gaming icon in this environment's theme")
        assert icon.name() == "input-gaming"

    def test_themed_icon_falls_back_to_the_glyph_when_absent(self, qapp):
        from PyQt6.QtGui import QIcon
        with patch.object(QIcon, "fromTheme", lambda _name, fallback: fallback):
            assert not themed_icon(True).isNull()


class TestTooltip:
    def test_states_the_connection_in_words(self, tray):
        widget, _ = tray()
        widget.set_connected(True)
        assert "gamepad connected" in widget._tray.toolTip()
        widget.set_connected(False)
        assert "no gamepad" in widget._tray.toolTip()

    def test_starts_disconnected(self, tray):
        widget, _ = tray()
        assert "no gamepad" in widget._tray.toolTip()


class TestMenu:
    def test_offers_the_four_actions_and_the_screen_menu(self, tray):
        widget, _ = tray()
        labels = [a.text() for a in widget._menu.actions() if not a.isSeparator()]
        assert len(labels) == 5

    def test_quit_action_is_wired(self, tray):
        widget, recorded = tray()
        [a for a in widget._menu.actions() if not a.isSeparator()][-1].trigger()
        assert recorded['quit'] == 1


class TestScreenMenu:
    MONITORS = [Display("DP-1", "Dell (DP-1)"), Display("HDMI-A-1", "LG TV (HDMI-A-1)")]

    def _choices(self, widget):
        return [a for a in widget._screens.actions() if not a.isSeparator()]

    def test_offers_the_system_first_then_every_screen(self, tray):
        widget, _ = tray(displays=FakeDisplays(self.MONITORS))
        labels = [a.text() for a in self._choices(widget)]
        assert labels[1:] == ["Dell (DP-1)", "LG TV (HDMI-A-1)"]

    def test_marks_the_system_while_nothing_was_chosen(self, tray):
        widget, _ = tray(displays=FakeDisplays(self.MONITORS))
        assert [a.isChecked() for a in self._choices(widget)] == [True, False, False]

    def test_marks_the_chosen_screen(self, tray):
        widget, _ = tray(displays=FakeDisplays(self.MONITORS, chosen="HDMI-A-1"))
        assert [a.isChecked() for a in self._choices(widget)] == [False, False, True]

    def test_picking_a_screen_chooses_it(self, tray):
        displays = FakeDisplays(self.MONITORS)
        widget, _ = tray(displays=displays)
        self._choices(widget)[1].trigger()
        assert displays.choices == ["DP-1"]

    def test_picking_the_system_chooses_no_screen(self, tray):
        displays = FakeDisplays(self.MONITORS, chosen="DP-1")
        widget, _ = tray(displays=displays)
        self._choices(widget)[0].trigger()
        assert displays.choices == [SYSTEM_DECIDES]

    def test_a_remembered_absent_screen_shows_but_cannot_be_picked(self, tray):
        absent = Display("DP-3", "DP-3", connected=False)
        widget, _ = tray(displays=FakeDisplays([*self.MONITORS, absent], chosen="DP-3"))
        last = self._choices(widget)[-1]
        assert (last.isChecked(), last.isEnabled()) == (True, False)
        assert "DP-3" in last.text()


class TestSourceSelection:
    def _source_for(self, desktop, monkeypatch):
        from infrastructure.linux.compositor import build_tray_icon_source
        # XDG_SESSION_DESKTOP counts as a session name too, so a run on one of
        # these desktops would otherwise answer for itself rather than the case.
        for var in ("KDE_FULL_SESSION", "XDG_SESSION_DESKTOP", "SWAYSOCK",
                    "HYPRLAND_INSTANCE_SIGNATURE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", desktop)
        return build_tray_icon_source()

    def test_cosmic_gets_the_themed_icon(self, monkeypatch):
        assert self._source_for("COSMIC", monkeypatch) is themed_icon

    @pytest.mark.parametrize("desktop", ["KDE", "GNOME", "sway"])
    def test_every_other_host_keeps_the_glyph(self, desktop, monkeypatch):
        assert self._source_for(desktop, monkeypatch) is glyph_icon
