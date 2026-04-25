"""VIDEO mode — fullscreen video playback."""

from pathlib import Path

from PyQt6.QtCore import Qt, QRect, QTimer, QUrl
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
from PyQt6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView, QVBoxLayout, QWidget


_ACCENT = QColor(136, 192, 208)
_BAR_COLOR = QColor(0, 0, 0, 200)
_BAR_H = 90
_MARGIN = 64


def _fmt_time(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _paint_controls(painter: QPainter, w: int, h: int, player: QMediaPlayer) -> None:
    duration = player.duration()
    position = player.position()
    is_playing = player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    bar_y = h - _BAR_H
    painter.fillRect(QRect(0, bar_y, w, _BAR_H), _BAR_COLOR)

    prog_y = bar_y + 14
    prog_w = w - 2 * _MARGIN
    painter.fillRect(QRect(_MARGIN, prog_y, prog_w, 5), QColor(255, 255, 255, 50))
    if duration > 0:
        filled = int(prog_w * position / duration)
        painter.fillRect(QRect(_MARGIN, prog_y, filled, 5), _ACCENT)

    f = QFont()
    f.setPointSize(14)
    painter.setFont(f)
    painter.setPen(QColor(236, 239, 244))
    painter.drawText(QRect(_MARGIN, prog_y + 12, prog_w, 32),
                     Qt.AlignmentFlag.AlignCenter,
                     f"{_fmt_time(position)}  /  {_fmt_time(duration)}")

    f2 = QFont()
    f2.setPointSize(22)
    painter.setFont(f2)
    painter.drawText(QRect(0, bar_y, _MARGIN, _BAR_H),
                     Qt.AlignmentFlag.AlignCenter,
                     "⏸" if is_playing else "▶")


class _VideoView(QGraphicsView):
    def __init__(self, player: QMediaPlayer, parent: QWidget) -> None:
        super().__init__(parent)
        self._player = player
        self._controls_visible = False

        scene = QGraphicsScene(self)
        self.setScene(scene)

        self._item = QGraphicsVideoItem()
        scene.addItem(self._item)
        player.setVideoOutput(self._item)

        self.setBackgroundBrush(QColor(0, 0, 0))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._item.nativeSizeChanged.connect(lambda _: self._fit())

    def _fit(self) -> None:
        self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def drawForeground(self, painter: QPainter, rect) -> None:
        if not self._controls_visible:
            return
        painter.save()
        painter.resetTransform()
        _paint_controls(painter, self.viewport().width(), self.viewport().height(), self._player)
        painter.restore()


class VideoMode(QWidget):
    def __init__(self, source: 'Path | str'):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._audio = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)

        self._view = _VideoView(self._player, self)
        layout.addWidget(self._view)

        if isinstance(source, Path):
            qurl = QUrl.fromLocalFile(str(source.resolve()))
        else:
            qurl = QUrl(source)
        self._player.setSource(qurl)
        self._player.play()

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(3000)
        self._hide_timer.timeout.connect(self._hide_controls)

        self._player.positionChanged.connect(
            lambda _: self._view.viewport().update() if self._view._controls_visible else None
        )
        self._player.mediaStatusChanged.connect(self._on_media_status)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

    def handle_key(self, key: int) -> bool:
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._toggle_pause()
            return True
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Minus):
            self._seek(-5000)
            return True
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Equal, Qt.Key.Key_Plus):
            self._seek(+5000)
            return True
        if key == Qt.Key.Key_Escape:
            if self._view._controls_visible:
                self._hide_controls()
                return True
            return False
        return False

    def set_listener(self, listener) -> None:
        pass

    def stop(self) -> None:
        self._player.stop()

    def _toggle_pause(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._show_controls()
            self._hide_timer.stop()
        else:
            self._player.play()
            self._show_controls()
            self._hide_timer.start()

    def _seek(self, delta_ms: int) -> None:
        pos = max(0, min(self._player.position() + delta_ms, self._player.duration()))
        self._player.setPosition(pos)
        self._show_controls()
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._hide_timer.start()

    def _show_controls(self) -> None:
        self._view._controls_visible = True
        self._view.viewport().update()

    def _hide_controls(self) -> None:
        self._hide_timer.stop()
        self._view._controls_visible = False
        self._view.viewport().update()

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._show_controls()
            self._hide_timer.stop()
