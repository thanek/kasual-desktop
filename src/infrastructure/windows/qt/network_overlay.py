"""Network overlay stub for Windows."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout

from infrastructure.windows.qt.base_overlay import BaseOverlay

logger = logging.getLogger(__name__)


class NetworkOverlay(BaseOverlay):
    """Stub Network overlay - UI exists but doesn't show real network status."""

    def __init__(self, gamepad, network_status, network_control, feedback, parent=None):
        self._gamepad = gamepad
        self._network_status = network_status
        self._network_control = network_control
        self._feedback = feedback
        super().__init__(parent=parent)

    def _build_content(self, layout: QVBoxLayout) -> None:
        title = QLabel("Network")
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 16px;")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)

        self._status = QLabel("Connected (TODO: real status)")
        self._status.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._status.setStyleSheet("font-size: 18px; padding: 8px; color: #a3be8c;")
        layout.addWidget(self._status)

        info = QLabel("Network status monitoring\nnot yet implemented")
        info.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        info.setStyleSheet("font-size: 14px; color: #888; padding: 8px;")
        layout.addWidget(info)

        logger.info("NetworkOverlay created - TODO: implement network monitoring")

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass