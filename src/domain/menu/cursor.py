"""Vertical menu navigation — a moving selection over a list of items.

Owns the selected index and the move / select / dismiss semantics shared by the
home-menu overlay and the tile popover (previously copy-pasted in each, and
duplicated again between their gamepad and keyboard handlers).

Pure application logic: no Qt, no sound backend. It repaints through an injected
`render(index)` callback and reports intent via `on_activate(index)` /
`on_dismiss`, with cursor feedback through the `Feedback` port. Both gamepad
events and translated keyboard events feed `handle_pad`; the widget owns only
presentation and the dismiss sound.

The state and the layout-independent behaviour (reset/hover/select/dismiss) live
in :class:`domain.menu.cursor_base.Cursor`; this adds only the 1-D up/down move.

`wrap`: True  → up/down wrap around the ends (home menu);
        False → movement clamps at the ends (tile popover).

`is_selectable`: a predicate skipped over when moving (e.g. a SEPARATOR row in
the unified tile menu, §7.3). Defaults to "every row selectable", so menus
without dividers behave exactly as before.
"""

from __future__ import annotations

from collections.abc import Callable

from domain.input.vocabulary import Event
from domain.menu.cursor_base import Cursor
from domain.shared.feedback import Feedback


class MenuCursor(Cursor):
    def __init__(
        self,
        count: Callable[[], int],
        render: Callable[[int], None],
        on_activate: Callable[[int], None],
        on_dismiss: Callable[[], None],
        feedback: Feedback,
        *,
        wrap: bool = False,
        is_selectable: Callable[[int], bool] | None = None,
    ) -> None:
        super().__init__(count, render, on_activate, on_dismiss, feedback)
        self._wrap = wrap
        self._is_selectable = is_selectable or (lambda _i: True)

    def _destination(self, event: str) -> int | None:
        if event == Event.UP:
            return self._shifted(-1)
        if event == Event.DOWN:
            return self._shifted(+1)
        return None

    def _shifted(self, delta: int) -> int:
        """The next selectable index *delta*-wards, wrapping or clamping at the
        ends and stepping over non-selectable rows. A no-op (current index) when
        the list is empty or nothing selectable lies that way."""
        n = self._count()
        if n == 0:
            return self._index
        idx = self._index
        for _ in range(n):
            if self._wrap:
                idx = (idx + delta) % n
            else:
                nxt = idx + delta
                if nxt < 0 or nxt >= n:
                    return self._index  # clamped at an end → stay put
                idx = nxt
            if self._is_selectable(idx):
                return idx
        return self._index
