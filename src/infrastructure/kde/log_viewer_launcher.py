"""Opens the log viewer in its own process — an ordinary xdg-toplevel window.

The viewer cannot share the main process: under the global
``QT_WAYLAND_SHELL_INTEGRATION=layer-shell`` every window becomes a layer-shell
surface (no move/resize/close). Spawning a child process with that variable
stripped from its environment gives the viewer normal xdg-shell behaviour — the
same trick ``AppManager.launch`` uses so launched apps aren't layer surfaces.
"""

import logging
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class LogViewerLauncher:
    """Launches (and on shutdown closes) the standalone log-viewer process.

    Single-instance: while a viewer process is alive, ``open()`` is a no-op, so
    repeated "Logs" clicks don't pile up windows.
    """

    def __init__(
        self,
        log_file: str,
        entry: Path,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
    ) -> None:
        self._log_file = log_file
        self._entry    = entry
        self._popen    = popen
        self._proc: subprocess.Popen | None = None

    def open(self) -> None:
        """Show the log viewer, unless one is already open."""
        if self._proc is not None and self._proc.poll() is None:
            return  # already open — one window is enough

        # Strip the layer-shell integration so the child is a normal xdg window;
        # keep the rest (QT_QPA_PLATFORM=wayland, PYTHONNOUSERSITE, …).
        env = os.environ.copy()
        env.pop("QT_WAYLAND_SHELL_INTEGRATION", None)
        logger.info("Opening log viewer: %s", self._log_file)
        self._proc = self._popen(
            [sys.executable, str(self._entry), self._log_file], env=env
        )

    def close(self) -> None:
        """Terminate the viewer process if it is still running (KD is quitting)."""
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
