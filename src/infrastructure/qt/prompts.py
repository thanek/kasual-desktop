"""Qt adapter for the `Prompts` port — localized user-facing message templates.

Owns the source strings and their translation context ("Desktop"), kept stable
so the existing locale entries (locale/kasual_*.ts) keep resolving after the
message logic moved off the Desktop widget into the application layer.
"""

from PyQt6.QtCore import QCoreApplication

from infrastructure.qt.ui import styles
from ports import Prompts


class QtPrompts(Prompts):
    """Implements `ports.Prompts` via Qt's translation system."""

    def close_confirm(self, name: str) -> str:
        # Truncate the (potentially long) app/window title for display — this is
        # presentation, kept out of the application layer.
        return QCoreApplication.translate(
            "Desktop", 'Are you sure you want to close\n"{0}"?'
        ).format(styles.truncate(name, 40))

    def launch_failed(self, error: str) -> str:
        return QCoreApplication.translate(
            "Desktop", "Failed to launch application:\n{0}"
        ).format(error)
