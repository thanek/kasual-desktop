"""INFO mode — file info card for unsupported file types."""

import datetime
import mimetypes
from pathlib import Path

import qtawesome as qta
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _mime_icon(mime: str) -> str:
    if not mime:
        return "fa5s.file"
    if mime.startswith("video/"):
        return "fa5s.film"
    if mime.startswith("audio/"):
        return "fa5s.headphones"
    if mime.startswith("text/"):
        return "fa5s.file-alt"
    if mime == "application/pdf":
        return "fa5s.file-pdf"
    if any(mime == m for m in (
        "application/zip", "application/x-tar", "application/gzip",
        "application/x-7z-compressed", "application/x-rar-compressed",
    )):
        return "fa5s.file-archive"
    return "fa5s.file"


class InfoMode(QWidget):
    def __init__(self, path: Path):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: black;")

        mime, _ = mimetypes.guess_type(str(path))
        stat = path.stat()
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.setSpacing(20)

        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(qta.icon(_mime_icon(mime or ""), color="#555").pixmap(80, 80))

        name_lbl = QLabel(path.name)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet("color: white; font-size: 22px; font-weight: bold;")
        name_lbl.setWordWrap(True)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #161616;
                border: 1px solid #2a2a2a;
                border-radius: 10px;
            }
        """)
        card.setFixedWidth(480)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 20, 28, 20)
        card_layout.setSpacing(10)

        for label, value in (
            (self.tr("Type:"), mime or self.tr("unknown")),
            (self.tr("Size:"), _human_size(stat.st_size)),
            (self.tr("Modified:"), mtime),
        ):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label)
            lbl.setFixedWidth(130)
            lbl.setStyleSheet("color: #555; font-size: 14px;")
            val = QLabel(value)
            val.setStyleSheet("color: #aaa; font-size: 14px;")
            val.setWordWrap(True)
            row_layout.addWidget(lbl)
            row_layout.addWidget(val, 1)
            card_layout.addWidget(row)

        hint_lbl = QLabel(self.tr("File type is not supported"))
        hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_lbl.setStyleSheet("color: #444; font-size: 13px; font-style: italic;")

        outer.addWidget(icon_lbl)
        outer.addWidget(name_lbl)
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(hint_lbl)

    def handle_key(self, key: int) -> bool:
        return False

    def set_listener(self, listener) -> None:
        pass

    def show_title(self, name: str) -> None:
        pass
