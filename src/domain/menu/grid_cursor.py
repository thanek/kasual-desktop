"""Grid navigation — a moving selection over items laid out in rows of a fixed
width (the tile-colour picker's swatch grid).

The 2-D twin of :class:`MenuCursor`: items are a flat list rendered left-to-right,
top-to-bottom into rows at most ``columns`` wide (the last row may be short).
LEFT/RIGHT cycle the column within the current row; UP/DOWN move the row within
the current column. Both axes wrap, and a vertical move into a short last row
that lacks the current column clamps to that row's last item.

Pure application logic: no Qt, no sound backend — it repaints through an injected
``render(index)`` callback and reports intent via ``on_activate(index)`` /
``on_dismiss``, exactly like :class:`MenuCursor`, so the same widget plumbing and
hover/keyboard wiring apply.
"""

from __future__ import annotations

from collections.abc import Callable

from domain.input.vocabulary import Event
from domain.shared.feedback import Cue, Feedback


class GridCursor:
    def __init__(
        self,
        count: Callable[[], int],
        columns: int,
        render: Callable[[int], None],
        on_activate: Callable[[int], None],
        on_dismiss: Callable[[], None],
        feedback: Feedback,
    ) -> None:
        self._count       = count
        self._columns     = max(1, columns)
        self._render      = render
        self._on_activate = on_activate
        self._on_dismiss  = on_dismiss
        self._feedback    = feedback
        self._index       = 0

    @property
    def index(self) -> int:
        return self._index

    @index.setter
    def index(self, value: int) -> None:
        """Place the selection without repaint/feedback (e.g. from a slot)."""
        self._index = value

    def reset(self, index: int = 0) -> None:
        """Set the selection (e.g. when the picker is (re)shown) and repaint."""
        self._index = index
        self._render(self._index)

    def handle_pad(self, event: str) -> None:
        if event == Event.LEFT:
            self._move_to(self._horizontal(-1))
        elif event == Event.RIGHT:
            self._move_to(self._horizontal(+1))
        elif event == Event.UP:
            self._move_to(self._vertical(-1))
        elif event == Event.DOWN:
            self._move_to(self._vertical(+1))
        elif event == Event.SELECT:
            self._on_activate(self._index)
        elif event in (Event.CANCEL, Event.CLOSE):
            self._on_dismiss()

    def hover(self, index: int) -> None:
        """Pointer moved onto item *index* — select it (with cursor feedback)."""
        if index != self._index:
            self._index = index
            self._render(self._index)
            self._feedback.play(Cue.CURSOR)

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

    def _move_to(self, new: int) -> None:
        if new != self._index:
            self._index = new
            self._render(self._index)
            self._feedback.play(Cue.CURSOR)
