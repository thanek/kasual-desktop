"""Shared base for the menu cursors — the selection state and the bits that do
not depend on the layout (1-D list vs 2-D grid).

Owns the selected index plus the behaviour common to :class:`MenuCursor` and
:class:`GridCursor`: ``reset`` / ``hover`` / ``index``, the "move there, repaint
and play the cursor cue only when the index actually changes" rule (`_go_to`),
and the SELECT / CANCEL / CLOSE handling (`_handle_common`). Subclasses add only
the layout-specific movement by implementing ``_destination`` — the new index
for a movement event, or ``None`` when the event is not a movement.

Pure application logic: no Qt, no sound backend. It repaints through an injected
``render(index)`` callback and reports intent via ``on_activate(index)`` /
``on_dismiss``, with cursor feedback through the :class:`Feedback` port.
"""

from __future__ import annotations

import abc
from collections.abc import Callable

from domain.input.vocabulary import Event
from domain.shared.feedback import Cue, Feedback


class Cursor(abc.ABC):
    def __init__(
        self,
        count: Callable[[], int],
        render: Callable[[int], None],
        on_activate: Callable[[int], None],
        on_dismiss: Callable[[], None],
        feedback: Feedback,
    ) -> None:
        self._count       = count
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
        """Set the selection (e.g. when the menu is (re)shown) and repaint."""
        self._index = index
        self._render(self._index)

    def hover(self, index: int) -> None:
        """Pointer moved onto item *index* — select it (with cursor feedback)."""
        self._go_to(index)

    def handle_pad(self, event: str) -> None:
        destination = self._destination(event)
        if destination is not None:
            self._go_to(destination)
        else:
            self._handle_common(event)

    @abc.abstractmethod
    def _destination(self, event: str) -> int | None:
        """The index a movement *event* leads to, or None when it is not a
        movement (SELECT / CANCEL / CLOSE). Implemented per layout."""

    def _handle_common(self, event: str) -> None:
        if event == Event.SELECT:
            self._on_activate(self._index)
        elif event in (Event.CANCEL, Event.CLOSE):
            self._on_dismiss()

    def _go_to(self, new: int) -> None:
        """Move the selection to *new*, repainting and playing the cursor cue
        only when it actually changed."""
        if new != self._index:
            self._index = new
            self._render(self._index)
            self._feedback.play(Cue.CURSOR)
