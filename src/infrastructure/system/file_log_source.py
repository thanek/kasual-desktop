"""Filesystem-backed LogSource — the I/O behind the domain LogProvider."""

import logging
import os

from domain.shared.log_provider import LogSource

logger = logging.getLogger(__name__)


class FileLogSource(LogSource):
    """A log file on disk: file size as the change token, best-effort reads.

    Failures (missing/unreadable file) are reported as "unavailable" (revision
    -1, empty read) rather than raised — a transient log read should never crash
    the viewer.
    """

    def __init__(self, path: str) -> None:
        self._path = path

    def name(self) -> str:
        return os.path.basename(self._path)

    def revision(self) -> int:
        try:
            return os.path.getsize(self._path)
        except OSError:
            return -1

    def read(self) -> str:
        try:
            with open(self._path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError as e:
            logger.warning("Could not read log file: %s", e)
            return ""

    def clear(self) -> None:
        try:
            open(self._path, "w").close()
        except OSError as e:
            logger.warning("Could not clear log file: %s", e)
