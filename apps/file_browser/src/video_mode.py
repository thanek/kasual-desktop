"""VIDEO mode — fullscreen video playback."""

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QPainter, QPalette
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class VideoMode(QWidget):
    def __init__(self, path: Path):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._video = QVideoWidget(self)
        # Black background before first frame and in letterbox areas
        palette = self._video.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0))
        self._video.setPalette(palette)
        self._video.setAutoFillBackground(True)
        layout.addWidget(self._video)

        self._audio = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video)
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self._player.play()

    def paintEvent(self, event) -> None:
        # Ensure the container widget is always opaque black.
        # Prevents old ImageMode content from bleeding through during initialisation.
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

    def handle_key(self, key: int) -> bool:
        return False

    def set_listener(self, listener) -> None:
        pass

    def stop(self) -> None:
        self._player.stop()
