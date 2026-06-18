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
    ) -> None:
        super().__init__(count, render, on_activate, on_dismiss, feedback)
        self._wrap = wrap

    def _destination(self, event: str) -> int | None:
        if event == Event.UP:
            return self._shifted(-1)
        if event == Event.DOWN:
            return self._shifted(+1)
        return None

    def _shifted(self, delta: int) -> int:
        """The index *delta* steps away, wrapping or clamping at the ends. A
        no-op (current index) when the list is empty."""
        n = self._count()
        if n == 0:
            return self._index
        if self._wrap:
            return (self._index + delta) % n
        return max(0, min(self._index + delta, n - 1))
