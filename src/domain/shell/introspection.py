"""What the shell currently has on screen, as a value a test harness can assert on."""

from dataclasses import dataclass
from typing import Protocol

TILES  = 'tiles'
HEADER = 'header'

# The tile bar's sections, in display order.
TILE_APP    = 'app'
TILE_ADD    = 'add'
TILE_WINDOW = 'window'


@dataclass(frozen=True)
class TileSnapshot:
    index:  int
    app_id: str
    name:   str


@dataclass(frozen=True)
class FocusSnapshot:
    """Where the pad's cursor sits.

    ``tile_index`` and ``app_id`` are None outside the app section; ``cursor`` and
    ``kind`` place the cursor across the whole bar.
    """

    zone:       str
    cursor:     int | None = None
    kind:       str | None = None
    tile_index: int | None = None
    app_id:     str | None = None


@dataclass(frozen=True)
class MenuItemSnapshot:
    label:   str
    action:  str
    focused: bool


@dataclass(frozen=True)
class MenuSectionSnapshot:
    """A zone of the Home menu — the sliders, the action cards — in zone order.

    ``columns`` says how it navigates: a one-column zone ignores left/right.
    """

    kind:    str
    columns: int
    items:   tuple[MenuItemSnapshot, ...]


@dataclass(frozen=True)
class HomeMenuSnapshot:
    """What the Home menu offers and where its cursor sits. Closed it offers
    nothing: the sections are composed for the context it is opened in."""

    open:     bool
    sections: tuple[MenuSectionSnapshot, ...] = ()

    @property
    def focused(self) -> MenuItemSnapshot | None:
        for section in self.sections:
            for item in section.items:
                if item.focused:
                    return item
        return None


@dataclass(frozen=True)
class ConfirmSnapshot:
    """The confirmation a destructive pick is gated by — closing an app, unpinning.

    ``confirm_focused`` is which button a press of A would hit.
    """

    open:            bool
    question:        str = ''
    confirm_focused: bool = False


@dataclass(frozen=True)
class ShellSnapshot:
    """The Home view (tiles, focus), the Home menu, and which shell surfaces are
    on screen.

    Three states tell apart the ways the Desktop leaves the foreground:
    ``desktop_visible`` — in front and owning input; ``desktop_mapped`` — ceded but
    still on screen, so it covers an app's ordinary window unless it also sank;
    ``desktop_sunk`` — ceded and under those windows.

    ``foreground`` is the app the shell believes it launched, which outlives the
    app's process.
    """

    desktop_visible:    bool
    desktop_mapped:     bool
    desktop_sunk:       bool
    home_header_mapped: bool
    hint_bar_mapped:    bool
    home_menu:          HomeMenuSnapshot
    confirm:            ConfirmSnapshot
    focus:              FocusSnapshot
    tiles:              tuple[TileSnapshot, ...]
    foreground:         str | None = None


class ShellIntrospection(Protocol):
    def snapshot(self) -> ShellSnapshot: ...
