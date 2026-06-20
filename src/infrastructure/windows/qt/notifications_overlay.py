"""Notifications overlay stub for Windows."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout

from infrastructure.windows.qt.base_overlay import BaseOverlay

logger = logging.getLogger(__name__)


class NotificationsOverlay(BaseOverlay):
    """Stub Notifications overlay - UI exists but doesn't show real notifications."""

    def __init__(self, gamepad, notifications, feedback, parent=None):
        self._gamepad = gamepad
        self._notifications = notifications
        self._feedback = feedback
        super().__init__(parent=parent)

    def _build_content(self, layout: QVBoxLayout) -> None:
        title = QLabel("Notifications")
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 16px;")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)

        self._count = QLabel("0 unread")
        self._count.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._count.setStyleSheet("font-size: 18px; padding: 8px;")
        layout.addWidget(self._count)

        info = QLabel("Notification monitoring\nnot yet implemented")
        info.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        info.setStyleSheet("font-size: 14px; color: #888; padding: 8px;")
        layout.addWidget(info)

        logger.info("NotificationsOverlay created - TODO: implement notification monitoring")

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass