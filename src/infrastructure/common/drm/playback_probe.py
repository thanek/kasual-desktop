"""PlaybackProbe backed by Qt WebEngine's Widevine key-system access.

A wrong page size or libc makes the module refuse to load, and Netflix surfaces
that only as an opaque playback error.
"""

import logging
import sys
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QProcess, QTimer

from domain.drm.ports import PlaybackProbe, SystemFacts

logger = logging.getLogger(__name__)

_PROBE_SCRIPT = Path(__file__).with_name("eme_probe.py")
_TIMEOUT_MS = 45_000


class QtWebEnginePlaybackProbe(PlaybackProbe):
    """Starting Qt WebEngine and loading a CDM takes seconds, throughout which
    the caller's event loop has to keep running."""

    def __init__(self, facts: SystemFacts) -> None:
        self._facts = facts
        self._process: QProcess | None = None
        self._deadline: QTimer | None = None
        self._on_result: Callable[[bool], None] | None = None

    def verify(self, on_result: Callable[[bool], None]) -> None:
        self.cancel()
        cdm = self._facts.cdm_path()
        if cdm is None:
            on_result(False)
            return
        self._on_result = on_result
        self._process = QProcess()
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._failed)
        self._deadline = QTimer()
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self._timed_out)
        self._deadline.start(_TIMEOUT_MS)
        # The child imports PyQt6 from this interpreter: true for Kasual Desktop
        # on the system Python (the deb/rpm/arch packaging), false once frozen.
        self._process.start(sys.executable, [str(_PROBE_SCRIPT), cdm])

    def cancel(self) -> None:
        self._on_result = None
        process, self._process = self._process, None
        deadline, self._deadline = self._deadline, None
        if deadline is not None:
            deadline.stop()
        if process is not None:
            process.disconnect()
            process.kill()

    def _finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        if code != 0 and self._process is not None:
            logger.info("Widevine playback probe rejected the module: %s",
                        self._stderr(self._process))
        self._report(code == 0)

    def _failed(self, error: QProcess.ProcessError) -> None:
        logger.warning("Widevine playback probe failed to run: %s", error)
        self._report(False)

    def _timed_out(self) -> None:
        logger.warning("Widevine playback probe gave no answer in %d s",
                       _TIMEOUT_MS // 1000)
        self._report(False)

    def _report(self, plays: bool) -> None:
        on_result = self._on_result
        self.cancel()
        if on_result is not None:
            on_result(plays)

    @staticmethod
    def _stderr(process: QProcess) -> str:
        return bytes(process.readAllStandardError()).decode(
            "utf-8", "replace").strip()
