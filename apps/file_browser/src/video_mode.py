"""VIDEO mode — fullscreen video playback."""

import json
import os
import threading
from pathlib import Path
from urllib.request import urlopen

_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "kasual"
_VIDEO_SETTINGS_FILE = _CACHE_DIR / "file_browser_video_settings.json"


def _load_video_settings() -> dict:
    try:
        return json.loads(_VIDEO_SETTINGS_FILE.read_text())
    except Exception:
        return {}


def _save_video_settings(settings: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _VIDEO_SETTINGS_FILE.write_text(json.dumps(settings))
    except Exception:
        pass

import qtawesome as qta
from PyQt6.QtCore import Qt, QRect, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
from PyQt6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView, QVBoxLayout, QWidget


_ACCENT = QColor(136, 192, 208)
_BAR_COLOR = QColor(0, 0, 0, 200)
_BAR_H = 90
_MARGIN = 64
_AUDIO_CIRCLE_COLOR = QColor(70, 70, 70)
_AUDIO_ICON_COLOR = QColor(25, 25, 25)
_TITLE_BAR_H = 58
_TITLE_BG = QColor(0, 0, 0, 170)
_TITLE_FG = QColor(236, 239, 244)


def _fmt_time(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


_TITLE_PAD_X = 28
_TITLE_PAD_Y = 12
_TITLE_RADIUS = 24
_CTRL_ICON_SIZE = 28
_CTRL_ICON_CLR = "#eceff4"
_ctrl_icon_cache: dict = {}


def _ctrl_icon(name: str):
    if name not in _ctrl_icon_cache:
        _ctrl_icon_cache[name] = qta.icon(name, color=_CTRL_ICON_CLR)
    return _ctrl_icon_cache[name]


def _paint_title(painter: QPainter, w: int, text: str) -> None:
    f = QFont()
    f.setPointSize(15)
    painter.setFont(f)
    fm = QFontMetrics(f)
    text_w = fm.horizontalAdvance(text)
    text_h = fm.height()
    box_w = text_w + 2 * _TITLE_PAD_X
    box_h = text_h + 2 * _TITLE_PAD_Y
    x = (w - box_w) // 2
    y = _TITLE_PAD_Y
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(_TITLE_BG)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(x, y, box_w, box_h, _TITLE_RADIUS, _TITLE_RADIUS)
    painter.setPen(_TITLE_FG)
    painter.drawText(QRect(x, y, box_w, box_h), Qt.AlignmentFlag.AlignCenter, text)


def _paint_controls(painter: QPainter, w: int, h: int,
                    player: QMediaPlayer, audio: QAudioOutput) -> None:
    muted = audio.isMuted()
    duration = player.duration()
    position = player.position()
    is_playing = player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    box_w = w // 2
    box_x = (w - box_w) // 2
    box_y = h - _BAR_H - _TITLE_PAD_Y

    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(_BAR_COLOR)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(box_x, box_y, box_w, _BAR_H, _TITLE_RADIUS, _TITLE_RADIUS)

    prog_x = box_x + _MARGIN
    prog_y = box_y + 14
    prog_w = box_w - 2 * _MARGIN
    painter.fillRect(QRect(prog_x, prog_y, prog_w, 5), QColor(255, 255, 255, 50))
    if duration > 0:
        filled = int(prog_w * position / duration)
        painter.fillRect(QRect(prog_x, prog_y, filled, 5), _ACCENT)

    f = QFont()
    f.setPointSize(14)
    painter.setFont(f)
    painter.setPen(QColor(236, 239, 244))
    painter.drawText(QRect(prog_x, prog_y + 12, prog_w, 32),
                     Qt.AlignmentFlag.AlignCenter,
                     f"{_fmt_time(position)}  /  {_fmt_time(duration)}")

    s = _CTRL_ICON_SIZE
    iy = box_y + (_BAR_H - s) // 2
    _ctrl_icon("fa5s.pause" if is_playing else "fa5s.play").paint(
        painter, QRect(box_x + (_MARGIN - s) // 2, iy, s, s))
    _ctrl_icon("fa5s.volume-mute" if muted else "fa5s.volume-up").paint(
        painter, QRect(box_x + box_w - _MARGIN + (_MARGIN - s) // 2, iy, s, s))


class _VideoView(QGraphicsView):
    def __init__(self, player: QMediaPlayer, audio: QAudioOutput, parent: QWidget,
                 is_audio: bool = False) -> None:
        super().__init__(parent)
        self._player = player
        self._audio = audio
        self._controls_visible = False
        self._title_text = ""
        self._title_visible = False
        self._is_audio = is_audio
        self._audio_pixmap: QPixmap | None = None
        if is_audio:
            # fa5s glyph U+F8CF (music-note, FA5 Pro); falls back to fa5s.music in free builds
            self._audio_icon = qta.icon("fa5s.music", color=_AUDIO_ICON_COLOR)

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

    def set_audio_pixmap(self, pix: QPixmap) -> None:
        self._audio_pixmap = pix
        self.viewport().update()

    def _fit(self) -> None:
        self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def _draw_audio_bg(self, painter: QPainter) -> None:
        vw = self.viewport().width()
        vh = self.viewport().height()
        r = min(vw, vh) * 9 // 32
        cx, cy = vw // 2, vh // 2

        if self._audio_pixmap and not self._audio_pixmap.isNull():
            scaled = self._audio_pixmap.scaled(
                r * 2, r * 2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(cx - scaled.width() // 2, cy - scaled.height() // 2, scaled)
        else:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(_AUDIO_CIRCLE_COLOR)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
            icon_size = r * 5 // 6
            self._audio_icon.paint(
                painter,
                QRect(cx - icon_size // 2, cy - icon_size // 2, icon_size, icon_size),
            )

    def drawForeground(self, painter: QPainter, rect) -> None:
        painter.save()
        painter.resetTransform()
        if self._is_audio:
            self._draw_audio_bg(painter)
        if self._title_visible and self._title_text:
            _paint_title(painter, self.viewport().width(), self._title_text)
        if self._controls_visible:
            _paint_controls(painter, self.viewport().width(), self.viewport().height(),
                            self._player, self._audio)
        painter.restore()


class VideoMode(QWidget):
    _thumbnail_ready = pyqtSignal(bytes)

    def __init__(self, source: 'Path | str', is_audio: bool = False,
                 thumbnail: 'Path | str | None' = None):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._audio = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        self._audio.setMuted(_load_video_settings().get("muted", False))

        self._view = _VideoView(self._player, self._audio, self, is_audio=is_audio)
        layout.addWidget(self._view)

        if isinstance(source, Path):
            qurl = QUrl.fromLocalFile(str(source.resolve()))
        else:
            qurl = QUrl(source)
        self._player.setSource(qurl)
        self._player.play()

        self._title = ""
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(3000)
        self._hide_timer.timeout.connect(self._hide_controls)

        self._title_timer = QTimer(self)
        self._title_timer.setSingleShot(True)
        self._title_timer.setInterval(3000)
        self._title_timer.timeout.connect(self._hide_title)

        self._player.positionChanged.connect(
            lambda _: self._view.viewport().update() if self._view._controls_visible else None
        )
        self._player.mediaStatusChanged.connect(self._on_media_status)

        if is_audio and thumbnail is not None:
            self._load_thumbnail(thumbnail)

    def _load_thumbnail(self, thumbnail: 'Path | str') -> None:
        if isinstance(thumbnail, Path):
            pix = QPixmap(str(thumbnail))
            if not pix.isNull():
                self._view.set_audio_pixmap(pix)
        elif isinstance(thumbnail, str) and thumbnail:
            self._thumbnail_ready.connect(self._on_thumbnail_data)
            threading.Thread(
                target=self._fetch_thumbnail,
                args=(thumbnail,),
                daemon=True,
            ).start()

    def _fetch_thumbnail(self, url: str) -> None:
        try:
            with urlopen(url, timeout=5) as resp:
                data = resp.read()
        except Exception:
            data = b""
        self._thumbnail_ready.emit(data)

    def _on_thumbnail_data(self, data: bytes) -> None:
        if not data:
            return
        pix = QPixmap()
        if pix.loadFromData(data) and not pix.isNull():
            self._view.set_audio_pixmap(pix)

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
        if key == Qt.Key.Key_H:
            self._toggle_mute()
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

    def _restart_hide_timer_if_playing(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._hide_timer.start()

    def _toggle_pause(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._show_controls()
            self._hide_timer.stop()
            self.show_title("")
        else:
            self._player.play()
            self._show_controls()
            self._restart_hide_timer_if_playing()

    def _toggle_mute(self) -> None:
        self._audio.setMuted(not self._audio.isMuted())
        _save_video_settings({"muted": self._audio.isMuted()})
        self._show_controls()
        self._restart_hide_timer_if_playing()

    def _seek(self, delta_ms: int) -> None:
        pos = max(0, min(self._player.position() + delta_ms, self._player.duration()))
        self._player.setPosition(pos)
        self._show_controls()
        self._restart_hide_timer_if_playing()

    def show_title(self, name: str) -> None:
        if name:
            self._title = name
        self._view._title_text = self._title
        self._view._title_visible = True
        self._view.viewport().update()
        self._title_timer.start()

    def _hide_title(self) -> None:
        self._view._title_visible = False
        self._view.viewport().update()

    def _show_controls(self) -> None:
        self._view._controls_visible = True
        self._view.viewport().update()

    def _hide_controls(self) -> None:
        self._hide_timer.stop()
        self._view._controls_visible = False
        self._view.viewport().update()

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._player.pause()
            self._show_controls()
            self._hide_timer.stop()
