"""Serving a log's text to a viewer — the policy, kept apart from presentation.

`LogProvider` owns *what* a log viewer is served: the latest text, but only when
it actually changed since the last look, so a polling viewer repaints on change
rather than every tick. The bytes themselves come from an injected `LogSource`
(a file on disk in production) — the policy stays I/O-free and unit-testable,
the I/O stays in infrastructure.
"""

from typing import Protocol


class LogSource(Protocol):
    """Where a log's bytes and lifecycle live (a file on disk in production)."""

    def name(self) -> str: ...
    def revision(self) -> int: ...   # change token; -1 when unavailable
    def read(self) -> str: ...
    def clear(self) -> None: ...


class LogProvider:
    """Serves log text, re-reading the source only when it changed.

    `poll()` returns fresh text on a change and `None` otherwise (including when
    the source is unavailable), so the viewer can skip repaints. `invalidate()`
    forces the next poll to re-serve (e.g. when the window is shown again).
    """

    def __init__(self, source: LogSource) -> None:
        self._source = source
        self._last_revision: int | None = None

    @property
    def name(self) -> str:
        """A short label for the log (its file's basename in production)."""
        return self._source.name()

    def poll(self) -> str | None:
        """Return the log text if it changed since the last poll, else None."""
        revision = self._source.revision()
        if revision < 0 or revision == self._last_revision:
            return None
        self._last_revision = revision
        return self._source.read()

    def invalidate(self) -> None:
        """Force the next poll() to re-serve the log."""
        self._last_revision = None

    def clear(self) -> None:
        """Empty the log and resync, so the next poll() sees no change."""
        self._source.clear()
        self._last_revision = self._source.revision()
