"""Standalone entry point for the Kasual log viewer — run in its OWN process.

The main app runs under ``QT_WAYLAND_SHELL_INTEGRATION=layer-shell`` (set in
kasual.sh), which turns every top-level window in that process into a layer-shell
surface — including the log viewer, which then has no xdg decorations and cannot
be moved, resized or closed. Running the viewer as a separate process *without*
that env var gives it the ordinary xdg-shell integration, i.e. a normal toplevel
window. ``LogViewerLauncher`` spawns this module with the variable stripped.

Usage: ``python3 src/log_viewer_main.py <log-file>`` (cwd-independent — Python
puts this file's dir, ``src/``, on sys.path, so the imports below resolve).
"""

import os
import sys
from pathlib import Path

# Native Wayland, but deliberately NOT QT_WAYLAND_SHELL_INTEGRATION=layer-shell:
# leaving it unset gives a normal xdg-toplevel (movable / resizable / closable).
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")

from PyQt6.QtWidgets import QApplication

from domain.shared.log_provider import LogProvider
from infrastructure.common.qt.i18n import install_translations
from infrastructure.common.qt.ui.log_viewer import LogViewer
from infrastructure.common.log.file_log_source import FileLogSource

_DEFAULT_LOG = Path.home() / ".local" / "cache" / "kasual" / "kasual.log"


def main() -> None:
    log_file = sys.argv[1] if len(sys.argv) > 1 else str(_DEFAULT_LOG)

    app = QApplication(sys.argv)
    app.setApplicationName("Kasual Desktop – Logs")
    install_translations(app, str(Path(__file__).parent.parent / "locale"))

    viewer = LogViewer(LogProvider(FileLogSource(log_file)))
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
