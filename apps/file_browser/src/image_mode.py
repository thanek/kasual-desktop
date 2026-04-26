"""IMAGE mode — fullscreen image display with zoom, pan and rotation."""

import threading
from pathlib import Path
from urllib.request import urlopen

from PyQt6.QtCore import Qt, QBuffer, QIODeviceBase, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImageReader, QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import QApplication, QWidget


_PAN_SPEED = 12.0
_ZOOM_SPEED = 0.015
_TITLE_BG = QColor(0, 0, 0, 170)
_TITLE_FG = QColor(236, 239, 244)
_TITLE_PAD_X = 28
_TITLE_PAD_Y = 12
_TITLE_RADIUS = 24


class ImageMode(QWidget):
    _ZOOM_STEP = 1.2
    _image_ready = pyqtSignal(bytes)

    def __init__(self, source: 'Path | str'):
        super().__init__()
        self._listener = None
        self._loading = False

        if isinstance(source, Path):
            self._load_pixmap(source)
        else:
            self._pixmap = QPixmap()
            self._scaled = QPixmap()
            self._zoom = 1.0
            self._initial_zoom = 1.0
            self._offset_x = 0.0
            self._offset_y = 0.0
            self._loading = True
            self._image_ready.connect(self._on_image_data)
            threading.Thread(target=self._fetch_url, args=(source,), daemon=True).start()

        self._title_text = ""
        self._title_visible = False
        self._title_timer = QTimer(self)
        self._title_timer.setSingleShot(True)
        self._title_timer.setInterval(3000)
        self._title_timer.timeout.connect(self._hide_title)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _fetch_url(self, url: str) -> None:
        try:
            with urlopen(url, timeout=15) as resp:
                data = resp.read()
            self._image_ready.emit(data)
        except Exception:
            self._image_ready.emit(b"")

    def _on_image_data(self, data: bytes) -> None:
        self._loading = False
        if data:
            buf = QBuffer()
            buf.setData(data)
            buf.open(QIODeviceBase.OpenModeFlag.ReadOnly)
            reader = QImageReader(buf)
            reader.setAutoTransform(True)
            pix = QPixmap.fromImage(reader.read())
            if not pix.isNull():
                self._pixmap = pix
                screen = QApplication.primaryScreen().size()
                w, h = pix.width(), pix.height()
                if w > screen.width() or h > screen.height():
                    self._zoom = min(screen.width() / w, screen.height() / h)
                else:
                    self._zoom = 1.0
                self._initial_zoom = self._zoom
                self._offset_x = 0.0
                self._offset_y = 0.0
                self._rebuild_scaled()
        self.update()

    def show_title(self, name: str) -> None:
        if name:
            self._title_text = name
        self._title_visible = True
        self.update()
        self._title_timer.start()

    def _hide_title(self) -> None:
        self._title_visible = False
        self.update()

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
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        self._pixmap = QPixmap.fromImage(reader.read())
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
        if self._pixmap.isNull():
            self._scaled = QPixmap()
            return
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
        if self._listener is None or self._loading:
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
        if self._loading:
            painter.setPen(QColor(100, 100, 100))
            f = QFont()
            f.setPointSize(20)
            painter.setFont(f)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "…")
            return
        if self._pixmap.isNull():
            return
        x = (self.width() - self._scaled.width()) // 2 + int(self._offset_x)
        y = (self.height() - self._scaled.height()) // 2 + int(self._offset_y)
        painter.drawPixmap(x, y, self._scaled)
        if self._title_visible and self._title_text:
            f = QFont()
            f.setPointSize(15)
            painter.setFont(f)
            fm = QFontMetrics(f)
            text_w = fm.horizontalAdvance(self._title_text)
            text_h = fm.height()
            box_w = text_w + 2 * _TITLE_PAD_X
            box_h = text_h + 2 * _TITLE_PAD_Y
            x = (self.width() - box_w) // 2
            y = _TITLE_PAD_Y
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(_TITLE_BG)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, y, box_w, box_h, _TITLE_RADIUS, _TITLE_RADIUS)
            painter.setPen(_TITLE_FG)
            painter.drawText(QRect(x, y, box_w, box_h), Qt.AlignmentFlag.AlignCenter,
                             self._title_text)
