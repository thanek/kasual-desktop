"""Qt adapter for the `Prompts` port — localized user-facing message templates.

Owns the source strings and their translation context ("Desktop"), kept stable
so the existing locale entries (locale/kasual_*.ts) keep resolving after the
message logic moved off the Desktop widget into the application layer.
"""

from PyQt6.QtCore import QCoreApplication


class QtPrompts:
    """Implements `ports.Prompts` via Qt's translation system."""

    def close_confirm(self, name: str) -> str:
        return QCoreApplication.translate(
            "Desktop", 'Are you sure you want to close\n"{0}"?'
        ).format(name)

    def launch_failed(self, error: str) -> str:
        return QCoreApplication.translate(
            "Desktop", "Failed to launch application:\n{0}"
        ).format(error)
