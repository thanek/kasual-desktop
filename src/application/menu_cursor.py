"""Vertical menu navigation — a moving selection over a list of items.

Owns the selected index and the move / select / dismiss semantics shared by the
home-menu overlay and the tile popover (previously copy-pasted in each, and
duplicated again between their gamepad and keyboard handlers).

Pure application logic: no Qt, no sound backend. It repaints through an injected
`render(index)` callback and reports intent via `on_activate(index)` /
`on_dismiss`, with cursor feedback through the `Feedback` port. Both gamepad
events and translated keyboard events feed `handle_pad`; the widget owns only
presentation and the dismiss sound.

`wrap`: True  → up/down wrap around the ends (home menu);
        False → movement clamps at the ends (tile popover).
"""

from __future__ import annotations

from collections.abc import Callable

from domain.input import Event
from ports import Feedback


class MenuCursor:
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
        self._count       = count
        self._render      = render
        self._on_activate = on_activate
        self._on_dismiss  = on_dismiss
        self._feedback    = feedback
        self._wrap        = wrap
        self._index       = 0

    @property
    def index(self) -> int:
        return self._index

    @index.setter
    def index(self, value: int) -> None:
        """Place the selection without repaint/feedback (e.g. from a slot)."""
        self._index = value

    def reset(self, index: int = 0) -> None:
        """Set the selection (e.g. when the menu is (re)shown) and repaint."""
        self._index = index
        self._render(self._index)

    def handle_pad(self, event: str) -> None:
        if event == Event.UP:
            self._move(-1)
        elif event == Event.DOWN:
            self._move(+1)
        elif event == Event.SELECT:
            self._on_activate(self._index)
        elif event in (Event.CANCEL, Event.CLOSE):
            self._on_dismiss()

    def hover(self, index: int) -> None:
        """Pointer moved onto item *index* — select it (with cursor feedback)."""
        if index != self._index:
            self._index = index
            self._render(self._index)
            self._feedback.play("cursor")

    def _move(self, delta: int) -> None:
        n = self._count()
        if n == 0:
            return
        if self._wrap:
            new = (self._index + delta) % n
        else:
            new = max(0, min(self._index + delta, n - 1))
        if new != self._index:
            self._index = new
            self._render(self._index)
            self._feedback.play("cursor")
