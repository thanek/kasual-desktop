"""Executable specification of Kasual in its own language — the DSL of section I.

These read like sentences about what Kasual does, wired purely from the domain /
application vocabulary (compose_tile_menu, MenuCursor, Feedback, DesktopState,
the Desktop coordinator) with no Qt anywhere. They are living documentation: if
the application layer still tells the story, they pass.
"""

from unittest.mock import MagicMock

from domain.shell.desktop import Desktop
from domain.menu.entry import CLOSE, LAUNCH, RESTORE
from domain.menu.cursor import MenuCursor
from domain.menu.tile import compose_tile_menu
from domain.shell.desktop_state import DesktopState
from domain.input.vocabulary import Event
from domain.catalog.target import AppTarget


def _popover(target, is_running, *, on_close, on_launch, on_restore, feedback):
    """A tile Popover: its entries composed by the rule, navigated by the cursor."""
    menu = compose_tile_menu(target, is_running)
    effects = {LAUNCH: on_launch, RESTORE: on_restore, CLOSE: on_close}
    cursor = MenuCursor(
        count=lambda: len(menu),
        render=lambda i: None,
        on_activate=lambda i: effects[menu[i].action](),
        on_dismiss=lambda: None,
        feedback=feedback,
    )
    return cursor, menu


# ── The Popover ──────────────────────────────────────────────────────────────

def test_close_from_popover_over_app_tile_closes_the_application():
    feedback = MagicMock()
    closed = []
    # A Popover over a running App Tile
    cursor, _ = _popover(
        AppTarget(0, "Steam"), is_running=True,
        on_close=lambda: closed.append("Steam"),
        on_launch=lambda: None, on_restore=lambda: None,
        feedback=feedback,
    )
    # Navigating the Popover Menu → Sounds are heard
    cursor.handle_pad(Event.DOWN)                 # Restore → Close
    feedback.play.assert_called_with("cursor")
    # Choosing Close → the Application closes
    cursor.handle_pad(Event.SELECT)
    assert closed == ["Steam"]


def test_launch_from_popover_over_idle_app_tile_launches_it():
    feedback = MagicMock()
    launched = []
    # A Popover over an App Tile that is not running offers only Launch
    cursor, menu = _popover(
        AppTarget(0, "Steam"), is_running=False,
        on_close=lambda: None, on_launch=lambda: launched.append("Steam"),
        on_restore=lambda: None, feedback=feedback,
    )
    assert [e.action for e in menu] == [LAUNCH]
    cursor.handle_pad(Event.SELECT)
    assert launched == ["Steam"]


# ── Minimize / reconnect ──────────────────────────────────────────────────────

def test_minimizing_the_desktop_then_reconnecting_round_trips():
    feedback = MagicMock()
    coord = Desktop(
        state=DesktopState(), view=MagicMock(), feedback=feedback,
        overlays=MagicMock(),
    )
    coord.show_desktop()
    # The user chose "Minimize Desktop": an exit sound, and it goes away
    coord.pause()
    feedback.play.assert_called_with("exit")
    # The controller reconnects: a start sound, and it comes back
    coord.resume()
    feedback.play.assert_called_with("start")
