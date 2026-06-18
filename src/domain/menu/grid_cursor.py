"""Grid navigation — a moving selection over items laid out in rows of a fixed
width (the tile-colour picker's swatch grid).

The 2-D twin of :class:`MenuCursor`: items are a flat list rendered left-to-right,
top-to-bottom into rows at most ``columns`` wide (the last row may be short).
LEFT/RIGHT cycle the column within the current row; UP/DOWN move the row within
the current column. Both axes wrap, and a vertical move into a short last row
that lacks the current column clamps to that row's last item.

State and layout-independent behaviour (reset/hover/select/dismiss) come from the
shared :class:`domain.menu.cursor_base.Cursor`; this adds only the 2-D movement,
so the same widget plumbing and hover/keyboard wiring apply as for MenuCursor.
"""

from __future__ import annotations

from collections.abc import Callable

from domain.input.vocabulary import Event
from domain.menu.cursor_base import Cursor
from domain.shared.feedback import Feedback


class GridCursor(Cursor):
    def __init__(
        self,
        count: Callable[[], int],
        columns: int,
        render: Callable[[int], None],
        on_activate: Callable[[int], None],
        on_dismiss: Callable[[], None],
        feedback: Feedback,
    ) -> None:
        super().__init__(count, render, on_activate, on_dismiss, feedback)
        self._columns = max(1, columns)

    def _destination(self, event: str) -> int | None:
        if event == Event.LEFT:
            return self._horizontal(-1)
        if event == Event.RIGHT:
            return self._horizontal(+1)
        if event == Event.UP:
            return self._vertical(-1)
        if event == Event.DOWN:
            return self._vertical(+1)
        return None

    def _horizontal(self, delta: int) -> int:
        """Next column within the current row, wrapping at the row's ends."""
        n = self._count()
        if n == 0:
            return 0
        cols = self._columns
        row_start = (self._index // cols) * cols
        row_len = min(cols, n - row_start)
        col = (self._index - row_start + delta) % row_len
        return row_start + col

    def _vertical(self, delta: int) -> int:
        """Same column in the row above/below, wrapping top↔bottom. A short last
        row that lacks the column clamps to its last existing item."""
        n = self._count()
        if n == 0:
            return 0
        cols = self._columns
        rows = (n + cols - 1) // cols
        row, col = divmod(self._index, cols)
        new_row = (row + delta) % rows
        return min(new_row * cols + col, n - 1)
