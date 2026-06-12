"""Generic event emitter — framework-agnostic pub/sub with unsubscribe tokens.

Replaces Qt's signal/slot machinery with a simple, testable contract so the
domain never imports PyQt: ``subscribe`` registers a handler and returns an
``Unsubscribe`` token that removes it again.

Note on threading: ``emit`` runs handlers synchronously in the calling thread.
Infrastructure that emits from a background thread (e.g. the gamepad watcher
reading evdev) is responsible for hopping onto the GUI thread *before* calling
``emit`` — this hub does no marshalling of its own.
"""

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class Unsubscribe:
    """Opaque token returned by ``EventEmitter.subscribe``.

    Calling it removes the associated handler from the emitter. Idempotent:
    calling it more than once is harmless.
    """

    __slots__ = ("_callback",)

    def __init__(self, callback: Callable[[], None]) -> None:
        self._callback = callback

    def __call__(self) -> None:
        self._callback()


class EventEmitter(Generic[T]):
    """Minimal pub/sub hub.

    >>> bus = EventEmitter[int]()
    >>> token = bus.subscribe(print)
    >>> bus.emit(1)
    1
    >>> token()        # removes the handler
    >>> bus.emit(2)    # nothing happens
    """

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: list[Callable[[T], None]] = []

    def subscribe(self, handler: Callable[[T], None]) -> Unsubscribe:
        """Register ``handler`` and return a token that removes it."""
        self._handlers.append(handler)

        def _remove() -> None:
            # Guard against double-unsubscribe: the token is idempotent.
            if handler in self._handlers:
                self._handlers.remove(handler)

        return Unsubscribe(_remove)

    def emit(self, event: T) -> None:
        """Dispatch ``event`` to every registered handler.

        Iterates a snapshot so a handler may unsubscribe during dispatch.
        """
        for handler in list(self._handlers):
            handler(event)

    def clear(self) -> None:
        """Remove all handlers (convenience for shutdown)."""
        self._handlers.clear()
