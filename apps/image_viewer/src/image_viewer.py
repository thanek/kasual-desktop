#!/usr/bin/env python3
"""
Image Viewer — Kasual Desktop fullscreen image viewer.
Gamepad: RIGHT_TRIGGER = zoom in, LEFT_TRIGGER = zoom out, right stick = pan,
         RB = next image, LB = prev image, B = reset zoom / exit.
Keyboard: + or = = zoom in, - = zoom out, Page Down/Up = next/prev, Escape = reset/exit.
"""

import mimetypes
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import QApplication, QMainWindow


_PAN_SPEED = 12.0   # pixels per timer tick (~60 fps)
_ZOOM_SPEED = 0.015  # zoom factor per tick per unit stick deflection


def _images_in_dir(path: Path) -> list[Path]:
    return sorted(
        p for p in path.parent.iterdir()
        if p.is_file() and (mimetypes.guess_type(str(p))[0] or "").startswith("image/")
    )


class ImageViewer(QMainWindow):
    _ZOOM_STEP = 1.2

    def __init__(self, path: str):
        super().__init__()
        self._listener = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.showFullScreen()

        resolved = Path(path).resolve()
        self._images = _images_in_dir(resolved)
        self._idx = self._images.index(resolved) if resolved in self._images else 0

        self._offset_x = 0.0
        self._offset_y = 0.0
        self._load(self._images[self._idx])

        self._pan_timer = QTimer(self)
        self._pan_timer.timeout.connect(self._apply_pan)
        self._pan_timer.start(16)

    def set_listener(self, listener) -> None:
        self._listener = listener

    # ------------------------------------------------------------------ image

    def _load(self, path: Path) -> None:
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
        self.update()

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

    def _navigate(self, delta: int) -> None:
        new_idx = self._idx + delta
        if 0 <= new_idx < len(self._images):
            self._idx = new_idx
            self._load(self._images[self._idx])

    # ------------------------------------------------------------------ zoom

    def _zoom_by(self, factor: float) -> None:
        self._offset_x *= factor
        self._offset_y *= factor
        self._zoom *= factor
        self._rebuild_scaled()
        self._clamp_offset()
        self.update()

    def _reset_zoom(self) -> None:
        self._zoom = self._initial_zoom
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._rebuild_scaled()
        self.update()

    def _rebuild_scaled(self) -> None:
        self._scaled = self._pixmap.scaled(
            int(self._pixmap.width() * self._zoom),
            int(self._pixmap.height() * self._zoom),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    # ------------------------------------------------------------------ pan

    def _apply_pan(self) -> None:
        if self._listener is None:
            return
        sx, sy = self._listener.stick
        ly = self._listener.left_y
        if sx != 0.0 or sy != 0.0:
            self._offset_x -= sx * _PAN_SPEED
            self._offset_y -= sy * _PAN_SPEED
            self._clamp_offset()
            self.update()
        if ly != 0.0:
            # up (ly < 0) → zoom in, down (ly > 0) → zoom out
            self._zoom_by(1.0 - ly * _ZOOM_SPEED)

    def _clamp_offset(self) -> None:
        max_x = max(0.0, (self._scaled.width() - self.width()) / 2)
        max_y = max(0.0, (self._scaled.height() - self.height()) / 2)
        self._offset_x = max(-max_x, min(max_x, self._offset_x))
        self._offset_y = max(-max_y, min(max_y, self._offset_y))

    # ------------------------------------------------------------------ Qt events

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._pixmap.isNull():
            return
        x = (self.width() - self._scaled.width()) // 2 + int(self._offset_x)
        y = (self.height() - self._scaled.height()) // 2 + int(self._offset_y)
        painter.drawPixmap(x, y, self._scaled)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if abs(self._zoom - self._initial_zoom) > 1e-6 or self._offset_x or self._offset_y:
                self._reset_zoom()
            else:
                self.close()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom_by(self._ZOOM_STEP)
        elif key == Qt.Key.Key_Minus:
            self._zoom_by(1.0 / self._ZOOM_STEP)
        elif key == Qt.Key.Key_PageDown:
            self._navigate(+1)
        elif key == Qt.Key.Key_PageUp:
            self._navigate(-1)
        elif key == Qt.Key.Key_R:
            self._rotate_cw()


def main():
    if len(sys.argv) < 2:
        print("Usage: image_viewer.py <image_path>", file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)
    window = ImageViewer(sys.argv[1])

    try:
        from gamepad import PadListener, find_pad
        pad = find_pad(["kasual-vpad"], timeout=5.0)
        listener = PadListener(pad, window=window)
        listener.start()
        window.set_listener(listener)
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
