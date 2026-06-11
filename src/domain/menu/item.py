"""A composed menu item — a domain citizen shared by the Home Overlay and the
tile Popover.

This is *what* a menu offers: a render-ready localized label, the icon, and the
abstract `action` the presenter dispatches on (a menu-entry kind from
`domain.menu.entry` or a system-action key from `domain.system.actions`), plus an
optional `target` payload for actions that operate on a specific app/window.

The Qt widgets render the label/icon and, on activation, hand the item back to a
controller-supplied `on_select`; they never hold the behaviour itself.
"""

from dataclasses import dataclass

from domain.catalog.target import Target


@dataclass(frozen=True)
class MenuItem:
    label:  str                   # localized, ready to render
    action: str                   # the intent the presenter dispatches on
    icon:   str | None = None     # qtawesome glyph; None where the menu shows no icons
    target: Target | None = None  # payload for target-specific actions (return/close/launch)
