from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QLockFile

logger = logging.getLogger(__name__)


class SingleInstanceGuard:
    """Ensures only one application instance runs at a time.

    Uses a ``QLockFile``; ``staleLockTime=0`` detects a stale lock by checking
    whether the recorded PID is still alive. The OS releases the underlying
    ``flock``/``LockFileEx`` when the owning process terminates, so orphaned
    files won't block a restart.
    """

    def __init__(self, lock_dir: str | Path) -> None:
        self._lock = QLockFile(str(Path(lock_dir) / "kasual.lock"))
        self._lock.setStaleLockTime(0)

    def try_lock(self) -> bool:
        if self._lock.tryLock():
            return True
        logger.warning("Another instance is already running (%s) — exiting",
                       self._holder())
        return False

    def _holder(self) -> str:
        """Whoever owns the lock, as far as Qt will say.

        ``getLockInfo`` answers ``(ok, pid, hostname, appname)`` — hostname before
        appname, and a success flag ahead of all three, which it clears when it
        cannot read the lock file at all.
        """
        ok, pid, hostname, appname = self._lock.getLockInfo()
        return f"PID {pid}, {appname}@{hostname}" if ok else "details unavailable"

    def release(self) -> None:
        self._lock.unlock()
