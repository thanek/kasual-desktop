from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QLockFile

logger = logging.getLogger(__name__)


class SingleInstanceGuard:
    """Ensures only one application instance runs at a time.

    Uses a ``QLockFile`` placed in the given directory. Works on both
    Linux and Windows.  Stale locks (from a crash) are detected by
    checking whether the recorded PID is still alive (``staleLockTime=0``).
    The OS kernel releases the underlying ``flock``/``LockFileEx`` when the
    owning process terminates, so orphaned files won't block a restart.
    """

    def __init__(self, lock_dir: str | Path) -> None:
        self._lock = QLockFile(str(Path(lock_dir) / "kasual.lock"))
        self._lock.setStaleLockTime(0)

    def try_lock(self) -> bool:
        if self._lock.tryLock():
            return True

        pid, appname, hostname = self._lock.getLockInfo()
        logger.warning(
            "Another instance is already running (PID %d, %s@%s) — exiting",
            pid, appname, hostname,
        )
        return False

    def release(self) -> None:
        self._lock.unlock()
