"""Volume overlay stub for Windows."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QSlider

from infrastructure.windows.qt.base_overlay import BaseOverlay

logger = logging.getLogger(__name__)


class VolumeOverlay(BaseOverlay):
    """Stub Volume overlay - UI exists but doesn't control system volume."""

    def __init__(self, gamepad, volume_control, feedback, parent=None):
        self._gamepad = gamepad
        self._volume_control = volume_control
        self._feedback = feedback
        super().__init__(parent=parent)

    def _build_content(self, layout: QVBoxLayout) -> None:
        title = QLabel("Volume")
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 16px;")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(100)
        self._slider.setValue(50)
        self._slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                background: #3b4252;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                width: 20px;
                background: #81a1c1;
                border-radius: 10px;
            }
        """)
        layout.addWidget(self._slider)

        self._label = QLabel("50%")
        self._label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._label.setStyleSheet("font-size: 18px; padding: 8px;")
        layout.addWidget(self._label)

        self._slider.valueChanged.connect(
            lambda v: self._label.setText(f"{v}%")
        )

        logger.info("VolumeOverlay created - TODO: implement system volume control")

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass