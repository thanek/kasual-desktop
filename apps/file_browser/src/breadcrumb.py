from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolButton


class BreadcrumbBar(QWidget):
    """Breadcrumb with clickable elements"""

    def __init__(
        self,
        navigate_cb: Callable[[Path], None],
        accent: str = "#88c0d0",
        muted: str = "#4c566a",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._navigate_cb = navigate_cb
        self._accent = accent
        self._muted = muted
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._layout = layout

    def set_path(self, path: Path) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        parts: list[Path] = []
        p = path
        while True:
            parts.insert(0, p)
            parent = p.parent
            if parent == p:
                break
            p = parent

        for i, part in enumerate(parts):
            name = part.name or "/"
            is_last = (i == len(parts) - 1)

            btn = QToolButton()
            btn.setText(name)
            btn.setStyleSheet(f"""
                QToolButton {{
                    color: {"#eceff4" if is_last else "#7a8a9e"};
                    background: transparent;
                    border: none;
                    font-size: 14px;
                    padding: 0 3px;
                    font-weight: {"600" if is_last else "normal"};
                }}
                QToolButton:hover {{ color: {self._accent}; }}
            """)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, pp=part: self._navigate_cb(pp))
            self._layout.addWidget(btn)

            if not is_last:
                sep = QLabel(" › ")
                sep.setStyleSheet(
                    f"color: {self._muted}; font-size: 13px; background: transparent;"
                )
                self._layout.addWidget(sep)

        self._layout.addStretch()

    def set_label(self, text: str) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #eceff4; background: transparent;"
            "font-size: 14px; font-weight: 600; padding: 0 3px;"
        )
        self._layout.addWidget(lbl)
        self._layout.addStretch()
