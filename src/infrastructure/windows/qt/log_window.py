"""In-process log viewer — Windows counterpart of the Linux ``LogViewerLauncher``.

On Wayland the main Kasual app runs under ``QT_WAYLAND_SHELL_INTEGRATION=layer-shell``,
which captures *every* top-level in its process as a layer-shell surface: no xdg
decorations, no move/resize/close. So Linux spawns the viewer in its OWN process
(stripping that env var) — see ``infrastructure/system/log_viewer_launcher.py``.

On Windows there is no layer-shell integration, so no such constraint: any
top-level QWidget is an ordinary window the user can move, resize and close. We
can therefore reuse the shared ``LogViewer`` widget *in the same process*, paying
only the tiny cost of keeping one QWidget around.

The lifecycle mirrors the Linux launcher's API (``open`` / ``close``) so the
composition root stays parallel: ``open`` is idempotent (a click on the tray
"Logs" entry while the viewer is already visible just raises it — never spawn
duplicates), and ``close`` runs at quit so we don't leak on shutdown.
"""

import logging

from domain.shared.log_provider import LogProvider
from infrastructure.qt.ui.log_viewer import LogViewer
from infrastructure.system.file_log_source import FileLogSource

logger = logging.getLogger(__name__)


class LogWindow:
    """Single-instance in-process log viewer presented from the tray.

    Lazily builds the viewer on first ``open()``; subsequent calls re-show and
    front the same instance instead of piling windows, exactly like
    ``LogViewerLauncher.open`` does across the process boundary on Linux.
    """

    def __init__(self, log_file: str) -> None:
        self._log_file = log_file
        self._viewer: LogViewer | None = None

    def open(self) -> None:
        """Show the log viewer (reusing the existing instance if there is one)."""
        if self._viewer is None:
            logger.info("Opening log viewer: %s", self._log_file)
            self._viewer = LogViewer(LogProvider(FileLogSource(self._log_file)))
        self._viewer.show()
        self._viewer.raise_()
        self._viewer.activateWindow()

    def close(self) -> None:
        """Tear the viewer down on app shutdown (mirror of Linux launcher.close)."""
        if self._viewer is not None:
            self._viewer.close()
            self._viewer.deleteLater()
            self._viewer = None