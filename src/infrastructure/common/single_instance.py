from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QLockFile

from domain.notifications.notifier import DesktopNotifier
from domain.shared.i18n import translate

logger = logging.getLogger(__name__)


class SingleInstanceGuard:
    """Ensures only one application instance runs at a time.

    Uses a ``QLockFile``; ``staleLockTime=0`` detects a stale lock by checking
    whether the recorded PID is still alive. The OS releases the underlying
    ``flock``/``LockFileEx`` when the owning process terminates, so orphaned
    files won't block a restart.

    A refused start has no UI of its own, so the optional ``notifier`` says why
    on the desktop of the instance that won.
    """

    def __init__(
        self, lock_dir: str | Path, notifier: DesktopNotifier | None = None,
    ) -> None:
        self._lock = QLockFile(str(Path(lock_dir) / "kasual.lock"))
        self._lock.setStaleLockTime(0)
        self._notifier = notifier

    def try_lock(self) -> bool:
        if self._lock.tryLock():
            return True

        if self._lock.error() != QLockFile.LockError.LockFailedError:
            logger.error(
                "Cannot acquire the single-instance lock %s (%s) — exiting",
                self._lock.fileName(), self._lock.error().name,
            )
            return False

        readable, pid, hostname, appname = self._lock.getLockInfo()
        if readable:
            logger.warning(
                "Another instance is already running (PID %d, %s@%s) — exiting",
                pid, appname, hostname,
            )
        else:
            logger.warning("Another instance is already running — exiting")
        self._announce_conflict(pid if readable else None)
        return False

    def _announce_conflict(self, pid: int | None) -> None:
        if self._notifier is None:
            return
        body = (
            translate("Kasual Desktop", "Another instance is already running in the background (PID {0}).")
            .format(pid) if pid else
            translate("Kasual Desktop", "Another instance is already running in the background.")
        )
        self._notifier.notify(
            translate("Kasual Desktop", "Kasual Desktop did not start"), body,
        )

    def release(self) -> None:
        self._lock.unlock()
