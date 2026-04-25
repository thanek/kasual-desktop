"""IMAGE mode — fullscreen image display with zoom, pan and rotation."""

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import QApplication, QWidget


_PAN_SPEED = 12.0
_ZOOM_SPEED = 0.015


class ImageMode(QWidget):
    _ZOOM_STEP = 1.2

    def __init__(self, path: Path):
        super().__init__()
        self._listener = None
        self._load_pixmap(path)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_listener(self, listener) -> None:
        self._listener = listener

    def handle_key(self, key: int) -> bool:
        if key == Qt.Key.Key_Escape:
            if self._is_zoomed():
                self._reset_view()
                return True
            return False
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom_by(self._ZOOM_STEP)
            return True
        if key == Qt.Key.Key_Minus:
            self._zoom_by(1.0 / self._ZOOM_STEP)
            return True
        if key == Qt.Key.Key_R:
            self._rotate_cw()
            return True
        return False

    # ------------------------------------------------------------------ image

    def _load_pixmap(self, path: Path) -> None:
        self._pixmap = QPixmap(str(path))
        screen = QApplication.primaryScreen().size()
        w, h = self._pixmap.width(), self._pixmap.height()
        if w > screen.width() or h > screen.height():
            self._zoom = min(screen.width() / w, screen.height() / h)
        else:
            self._zoom = 1.0
        self._initial_zoom = self._zoom
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._rebuild_scaled()

    def _rotate_cw(self) -> None:
        self._pixmap = self._pixmap.transformed(QTransform().rotate(90))
        screen = QApplication.primaryScreen().size()
        w, h = self._pixmap.width(), self._pixmap.height()
        if w > screen.width() or h > screen.height():
            self._zoom = min(screen.width() / w, screen.height() / h)
        else:
            self._zoom = 1.0
        self._initial_zoom = self._zoom
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._rebuild_scaled()
        self.update()

    # ------------------------------------------------------------------ zoom / pan

    def _is_zoomed(self) -> bool:
        return abs(self._zoom - self._initial_zoom) > 1e-6 or bool(self._offset_x) or bool(self._offset_y)

    def _reset_view(self) -> None:
        self._zoom = self._initial_zoom
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._rebuild_scaled()
        self.update()

    def _zoom_by(self, factor: float) -> None:
        self._offset_x *= factor
        self._offset_y *= factor
        self._zoom *= factor
        self._rebuild_scaled()
        self._clamp_offset()
        self.update()

    def _rebuild_scaled(self) -> None:
        self._scaled = self._pixmap.scaled(
            int(self._pixmap.width() * self._zoom),
            int(self._pixmap.height() * self._zoom),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _clamp_offset(self) -> None:
        max_x = max(0.0, (self._scaled.width() - self.width()) / 2)
        max_y = max(0.0, (self._scaled.height() - self.height()) / 2)
        self._offset_x = max(-max_x, min(max_x, self._offset_x))
        self._offset_y = max(-max_y, min(max_y, self._offset_y))

    def _tick(self) -> None:
        if self._listener is None:
            return
        sx, sy = self._listener.stick
        ly = self._listener.left_y
        changed = False
        if sx != 0.0 or sy != 0.0:
            self._offset_x -= sx * _PAN_SPEED
            self._offset_y -= sy * _PAN_SPEED
            self._clamp_offset()
            changed = True
        if ly != 0.0:
            self._zoom_by(1.0 - ly * _ZOOM_SPEED)
            changed = True
        if changed:
            self.update()

    # ------------------------------------------------------------------ paint

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._pixmap.isNull():
            return
        x = (self.width() - self._scaled.width()) // 2 + int(self._offset_x)
        y = (self.height() - self._scaled.height()) // 2 + int(self._offset_y)
        painter.drawPixmap(x, y, self._scaled)
