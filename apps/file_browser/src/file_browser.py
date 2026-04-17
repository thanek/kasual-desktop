#!/usr/bin/env python3
"""
File Browser —  Kasual Deskrop file browsing app
Gamepad navigation: D-pad = moving in different directions, A = confirm/enter, B = cancel,
Y = Home folder, X = folder up, L1 = back, R1 = forward.
"""

import datetime
import mimetypes
import os
import subprocess
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QCoreApplication, QLocale, QTranslator, QT_TRANSLATE_NOOP
from PyQt6.QtGui import QKeyEvent, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QListView, QLabel, QToolButton, QScrollArea,
    QSizePolicy,
)
import qtawesome as qta

import sound_player
from breadcrumb import BreadcrumbBar
from gamepad import find_pad, PadListener
from info_dialog import InfoDialog
from thumbnails import Thumbnailer, find_thumbnail, is_image

# ── Stałe ─────────────────────────────────────────────────────────────────────

VIRTUAL_DEVICE_NAME = "kasual-vpad"
PHYSICAL_DEVICE_NAME = "8BitDo Ultimate Wireless / Pro 2 Wired Controller"

HOME = Path.home()


def _xdg_dir(key: str) -> Path:
    cfg = Path.home() / ".config" / "user-dirs.dirs"
    try:
        for line in cfg.read_text().splitlines():
            if line.startswith(key + "="):
                value = line.split("=", 1)[1].strip().strip('"')
                return Path(value.replace("$HOME", str(Path.home())))
    except OSError:
        pass
    return Path.home()


BOOKMARKS = [
    (QT_TRANSLATE_NOOP("FileBrowser", "Home"), "fa5s.home", HOME),
    (QT_TRANSLATE_NOOP("FileBrowser", "Desktop"), "fa5s.desktop", _xdg_dir("XDG_DESKTOP_DIR")),
    (QT_TRANSLATE_NOOP("FileBrowser", "Documents"), "fa5s.file-alt", _xdg_dir("XDG_DOCUMENTS_DIR")),
    (QT_TRANSLATE_NOOP("FileBrowser", "Music"), "fa5s.music", _xdg_dir("XDG_MUSIC_DIR")),
    (QT_TRANSLATE_NOOP("FileBrowser", "Pictures"), "fa5s.image", _xdg_dir("XDG_PICTURES_DIR")),
    (QT_TRANSLATE_NOOP("FileBrowser", "Videos"), "fa5s.film", _xdg_dir("XDG_VIDEOS_DIR")),
    (QT_TRANSLATE_NOOP("FileBrowser", "Downloads"), "fa5s.download", _xdg_dir("XDG_DOWNLOAD_DIR")),
]

# Color palette (Nord-like, consistent with Kasual)
BG = "#0b140e"
BAR_BG = "rgba(15, 17, 25, 220)"
SIDEBAR_BG = "rgba(20, 26, 40, 200)"
TEXT = "#eceff4"
MUTED = "#4c566a"
ACCENT = "#88c0d0"
FOLDER_CLR = "#ebcb8b"
FILE_CLR = "#81a1c1"


# ── Main window ───────────────────────────────────────────────────────────────

class FileBrowserWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.tr("File Browser"))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Navigation state
        self._history: list[Path] = []
        self._future: list[Path] = []
        self._current: Path = HOME

        # Focus mode: "topbar" | "sidebar" | "main"
        self._focus = "main"
        self._topbar_idx = 0
        self._sidebar_idx = 0
        self._main_idx = 0
        self._icon_mode = True

        # Thumbnails: URI → number of row in the current listing
        self._pending_thumbs: dict[str, int] = {}
        self._thumbnailer = Thumbnailer(self)
        self._thumbnailer.ready.connect(self._on_thumbnails_ready)

        central = QWidget()
        central.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self._build_sidebar())
        content.addWidget(self._build_main(), stretch=1)
        root.addLayout(content, stretch=1)
        root.addWidget(self._build_statusbar())

        self._apply_icon_mode()
        self._navigate(HOME, add_to_history=False)
        self._update_focus()
        self.setFocus()

    # ── Top bar ───────────────────────────────────────────────────────────

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(58)
        bar.setStyleSheet(f"background-color: {BAR_BG};")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)

        self._topbar_buttons: list[QToolButton] = []
        defs = [
            ("fa5s.home", self.tr("Home (Y)"), self.go_home),
            ("fa5s.arrow-left", self.tr("Back (L1)"), self.go_back),
            ("fa5s.arrow-right", self.tr("Forward (R1)"), self.go_forward),
            ("fa5s.level-up-alt", self.tr("Up (X)"), self.go_up),
        ]
        for icon_name, tooltip, callback in defs:
            btn = QToolButton()
            btn.setFixedSize(44, 44)
            btn.setIcon(qta.icon(icon_name, color="white"))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip(tooltip)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(callback)
            layout.addWidget(btn)
            self._topbar_buttons.append(btn)

        layout.addSpacing(8)

        self._breadcrumb = BreadcrumbBar(self._navigate, accent=ACCENT, muted=MUTED)
        scroll_area = QScrollArea()
        scroll_area.setWidget(self._breadcrumb)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedHeight(44)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        layout.addWidget(scroll_area, stretch=1)

        layout.addSpacing(8)

        self._view_btn = QToolButton()
        self._view_btn.setFixedSize(44, 44)
        self._view_btn.setIconSize(QSize(18, 18))
        self._view_btn.setToolTip(self.tr("Toggle view (list/icons)"))
        self._view_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._view_btn.clicked.connect(self._toggle_view_mode)
        layout.addWidget(self._view_btn)
        self._topbar_buttons.append(self._view_btn)
        self._refresh_view_btn_icon()

        self._refresh_topbar_style()
        return bar

    def _refresh_topbar_style(self) -> None:
        for i, btn in enumerate(self._topbar_buttons):
            selected = (self._focus == "topbar" and i == self._topbar_idx)
            if selected:
                btn.setStyleSheet(f"""
                    QToolButton {{ background: {ACCENT}; border-radius: 8px; }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QToolButton {{
                        background: rgba(255,255,255,18);
                        border-radius: 8px;
                    }}
                    QToolButton:hover {{ background: rgba(255,255,255,35); }}
                    QToolButton:disabled {{ background: rgba(255,255,255,8); opacity: 0.4; }}
                """)

    # ── Sidebar ──────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(215)
        panel.setStyleSheet(
            f"background-color: {SIDEBAR_BG};"
            "border-right: 1px solid rgba(255,255,255,12);"
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(2)

        self._sidebar_buttons: list[QToolButton] = []
        for name, icon_name, path in BOOKMARKS:
            btn = QToolButton()
            btn.setText("  " + QCoreApplication.translate("FileBrowser", name))
            btn.setIcon(qta.icon(icon_name, color=ACCENT))
            btn.setIconSize(QSize(16, 16))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(40)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, p=path: self._navigate(p))
            layout.addWidget(btn)
            self._sidebar_buttons.append(btn)

        layout.addStretch()
        self._refresh_sidebar_style()
        return panel

    def _refresh_sidebar_style(self) -> None:
        for i, (_, _, path) in enumerate(BOOKMARKS):
            btn = self._sidebar_buttons[i]
            focused = (self._focus == "sidebar" and i == self._sidebar_idx)
            active = (self._current == path)
            if focused:
                btn.setStyleSheet(f"""
                    QToolButton {{
                        background: {ACCENT};
                        color: #1e2535;
                        border-radius: 6px;
                        text-align: left;
                        font-size: 13px;
                        padding: 0 8px;
                        font-weight: 600;
                    }}
                """)
            elif active:
                btn.setStyleSheet(f"""
                    QToolButton {{
                        background: rgba(136, 192, 208, 35);
                        color: {ACCENT};
                        border-radius: 6px;
                        text-align: left;
                        font-size: 13px;
                        padding: 0 8px;
                        font-weight: 600;
                    }}
                    QToolButton:hover {{ background: rgba(136, 192, 208, 55); }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QToolButton {{
                        background: transparent;
                        color: {TEXT};
                        border-radius: 6px;
                        text-align: left;
                        font-size: 13px;
                        padding: 0 8px;
                    }}
                    QToolButton:hover {{ background: rgba(255,255,255,10); }}
                """)

    # ── File list ──────────────────────────────────────────────────────────

    def _build_main(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 0)
        layout.setSpacing(0)

        self._file_list = QListWidget()
        self._file_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._file_list.setResizeMode(QListView.ResizeMode.Adjust)
        self._file_list.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self._file_list)
        return container

    def _stylesheet_icon(self) -> str:
        return f"""
            QListWidget {{
                background: transparent; border: none; outline: 0;
                color: {TEXT}; font-size: 15px;
            }}
            QListWidget::item {{
                padding: 6px; border-radius: 10px; margin: 4px;
            }}
            QListWidget::item:selected {{ background: {ACCENT}; color: #1e2535; }}
            QListWidget::item:selected:!active {{
                background: rgba(136, 192, 208, 60); color: {TEXT};
            }}
            QListWidget::item:hover:!selected {{ background: rgba(255,255,255,8); }}
        """

    def _stylesheet_list(self) -> str:
        return f"""
            QListWidget {{
                background: transparent; border: none; outline: 0;
                color: {TEXT}; font-size: 20px;
            }}
            QListWidget::item {{
                padding: 14px 16px; border-radius: 8px; margin-bottom: 2px;
            }}
            QListWidget::item:selected {{ background: {ACCENT}; color: #1e2535; }}
            QListWidget::item:selected:!active {{
                background: rgba(136, 192, 208, 60); color: {TEXT};
            }}
            QListWidget::item:hover:!selected {{ background: rgba(255,255,255,8); }}
        """

    def _refresh_view_btn_icon(self) -> None:
        icon_name = "fa5s.list" if self._icon_mode else "fa5s.th-large"
        self._view_btn.setIcon(qta.icon(icon_name, color="white"))

    def _apply_icon_mode(self) -> None:
        self._file_list.setViewMode(QListView.ViewMode.IconMode)
        self._file_list.setIconSize(QSize(128, 128))
        self._file_list.setGridSize(QSize(280, 240))
        self._file_list.setWrapping(True)
        self._file_list.setWordWrap(True)
        self._file_list.setUniformItemSizes(True)
        self._file_list.setStyleSheet(self._stylesheet_icon())

    def _apply_list_mode(self) -> None:
        self._file_list.setViewMode(QListView.ViewMode.ListMode)
        self._file_list.setIconSize(QSize(40, 40))
        self._file_list.setGridSize(QSize())
        self._file_list.setWrapping(False)
        self._file_list.setWordWrap(False)
        self._file_list.setUniformItemSizes(False)
        self._file_list.setStyleSheet(self._stylesheet_list())

    def _toggle_view_mode(self) -> None:
        self._icon_mode = not self._icon_mode
        if self._icon_mode:
            self._apply_icon_mode()
        else:
            self._apply_list_mode()
        self._refresh_view_btn_icon()

    # ── Bottom status bar ───────────────────────────────────────────────────

    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(40)
        bar.setStyleSheet(
            f"background-color: {BAR_BG};"
            "border-top: 1px solid rgba(255,255,255,10);"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; background: transparent;"
        )
        layout.addWidget(self._status_lbl)
        layout.addStretch()

        return bar

    # ── Navigation ─────────────────────────────────────────────────────────────

    def _navigate(self, path: Path, add_to_history: bool = True) -> None:
        if not path.exists() or not path.is_dir():
            return
        if not os.access(path, os.R_OK | os.X_OK):
            InfoDialog.show_message(
                self.tr("You don't have permission to open:\n{path}").format(path=path),
                self,
            )
            return
        if add_to_history and path != self._current:
            self._history.append(self._current)
            self._future.clear()
        self._current = path
        self._refresh_listing()
        self._breadcrumb.set_path(path)
        self._refresh_nav_button_state()
        self._refresh_sidebar_style()

    def _refresh_listing(self) -> None:
        self._file_list.clear()
        try:
            entries = sorted(
                [en for en in self._current.iterdir() if not en.name.startswith(".")],
                key=lambda en: (not en.is_dir(), en.name.lower()),
            )
        except PermissionError:
            self._status_lbl.setText(self.tr("Cannot read this directory"))
            return

        self._pending_thumbs.clear()
        needs_thumb: list[tuple[str, str, int]] = []  # (uri, mime, row)

        for row, entry in enumerate(entries):
            if entry.is_dir():
                icon = qta.icon("fa5s.folder", color=FOLDER_CLR)
            elif is_image(entry):
                thumb = find_thumbnail(entry)
                if thumb:
                    icon = QIcon(QPixmap(str(thumb)))
                else:
                    icon = qta.icon("fa5s.file-image", color=FILE_CLR)
                    mime, _ = mimetypes.guess_type(str(entry))
                    needs_thumb.append((entry.as_uri(), mime or "image/jpeg", row))
            else:
                icon = qta.icon("fa5s.file-alt", color=FILE_CLR)

            item = QListWidgetItem(icon, entry.name)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self._file_list.addItem(item)

        if needs_thumb and self._thumbnailer.available:
            uris = [u for u, _, _ in needs_thumb]
            mimes = [m for _, m, _ in needs_thumb]
            self._pending_thumbs = {u: r for u, _, r in needs_thumb}
            self._thumbnailer.request(uris, mimes)

        self._main_idx = 0
        if self._file_list.count() > 0:
            self._file_list.setCurrentRow(0)
        self._update_statusbar()

    def _on_thumbnails_ready(self, uris: list) -> None:
        for uri in uris:
            row = self._pending_thumbs.pop(uri, None)
            if row is None:
                continue
            item = self._file_list.item(row)
            if item is None:
                continue
            path: Path = item.data(Qt.ItemDataRole.UserRole)
            if path is None:
                continue
            thumb = find_thumbnail(path)
            if thumb:
                item.setIcon(QIcon(QPixmap(str(thumb))))

    def _refresh_nav_button_state(self) -> None:
        self._topbar_buttons[1].setEnabled(bool(self._history))
        self._topbar_buttons[2].setEnabled(bool(self._future))
        self._topbar_buttons[3].setEnabled(self._current != Path("/"))

    def go_home(self) -> None:
        self._navigate(HOME)

    def go_back(self) -> None:
        if self._history:
            self._future.append(self._current)
            self._navigate(self._history.pop(), add_to_history=False)

    def go_forward(self) -> None:
        if self._future:
            self._history.append(self._current)
            self._navigate(self._future.pop(), add_to_history=False)

    def go_up(self) -> None:
        parent = self._current.parent
        if parent != self._current:
            self._navigate(parent)

    def _activate_current_item(self) -> None:
        item = self._file_list.currentItem()
        if item is None:
            return
        path: Path = item.data(Qt.ItemDataRole.UserRole)
        if path.is_dir():
            self._navigate(path)
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _on_selection_changed(self, row: int) -> None:
        self._main_idx = max(0, row)
        self._update_statusbar()

    def _icon_cols(self) -> int:
        viewport_w = self._file_list.viewport().width()
        col_w = self._file_list.gridSize().width()
        return max(1, viewport_w // col_w)

    def _update_statusbar(self) -> None:
        item = self._file_list.currentItem()
        if item is None:
            msg = self.tr("Empty directory") if self._file_list.count() == 0 else ""
            self._status_lbl.setText(msg)
            return

        path: Path = item.data(Qt.ItemDataRole.UserRole)
        if path is None:
            return

        try:
            st = path.stat()
            if path.is_dir():
                self._status_lbl.setText(
                    self.tr("Folder  ·  {name}").format(name=path.name)
                )
            else:
                mime, _ = mimetypes.guess_type(str(path))
                type_str = mime or self.tr("unknown type")
                size_str = self._fmt_size(st.st_size)
                mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y  %H:%M")
                self._status_lbl.setText(
                    self.tr("File  ·  {name} ({type})  ·  {size}  ·  Modified: {mtime}").format(
                        name=path.name, type=type_str, size=size_str, mtime=mtime,
                    )
                )
        except OSError:
            self._status_lbl.setText(path.name)

    @staticmethod
    def _fmt_size(size: float) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    # ── Focus ─────────────────────────────────────────────────────────────────

    def _update_focus(self) -> None:
        self._refresh_topbar_style()
        self._refresh_sidebar_style()

        if self._focus == "main":
            if self._file_list.count() > 0:
                self._file_list.setCurrentRow(
                    min(self._main_idx, self._file_list.count() - 1)
                )
        else:
            self._file_list.clearSelection()

    # ── Keyboard support (UInput → PyQt6) ──────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()

        if self._focus == "topbar":
            if key == Qt.Key.Key_Left:
                self._topbar_idx = (self._topbar_idx - 1) % len(self._topbar_buttons)
                self._update_focus()
                sound_player.play("cursor")
            elif key == Qt.Key.Key_Right:
                self._topbar_idx = (self._topbar_idx + 1) % len(self._topbar_buttons)
                self._update_focus()
                sound_player.play("cursor")
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._topbar_buttons[self._topbar_idx].click()
                sound_player.play("select")
            elif key in (Qt.Key.Key_Down, Qt.Key.Key_Escape):
                self._focus = "main"
                self._update_focus()
                sound_player.play("cursor")

        elif self._focus == "sidebar":
            if key == Qt.Key.Key_Up:
                if self._sidebar_idx > 0:
                    self._sidebar_idx -= 1
                    self._update_focus()
                    _, _, path = BOOKMARKS[self._sidebar_idx]
                    self._navigate(path)
                    sound_player.play("cursor")
                else:
                    self._focus = "topbar"
                    self._topbar_idx = 0
                    self._update_focus()
                    sound_player.play("cursor")
            elif key == Qt.Key.Key_Down:
                if self._sidebar_idx < len(self._sidebar_buttons) - 1:
                    self._sidebar_idx += 1
                    self._update_focus()
                    _, _, path = BOOKMARKS[self._sidebar_idx]
                    self._navigate(path)
                    sound_player.play("cursor")
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._focus = "main"
                self._update_focus()
                sound_player.play("cursor")
            elif key == Qt.Key.Key_Right:
                self._focus = "main"
                self._update_focus()
                sound_player.play("cursor")
            elif key in (Qt.Key.Key_Escape, Qt.Key.Key_U):
                self.go_up()
                sound_player.play("select")
            elif key == Qt.Key.Key_H:
                self.go_home()
                sound_player.play("select")
            elif key == Qt.Key.Key_Backspace:
                self.go_back()
                sound_player.play("select")
            elif key == Qt.Key.Key_F:
                self.go_forward()
                sound_player.play("select")

        elif self._focus == "main":
            step = self._icon_cols() if self._icon_mode else 1
            if key == Qt.Key.Key_Up:
                if self._main_idx >= step:
                    self._main_idx -= step
                    self._file_list.setCurrentRow(self._main_idx)
                    sound_player.play("cursor")
                elif not self._icon_mode:
                    self._focus = "topbar"
                    self._topbar_idx = 0
                    self._update_focus()
                    sound_player.play("cursor")
            elif key == Qt.Key.Key_Down:
                if self._main_idx + step < self._file_list.count():
                    self._main_idx += step
                    self._file_list.setCurrentRow(self._main_idx)
                    sound_player.play("cursor")
            elif key == Qt.Key.Key_Left:
                if self._icon_mode and self._main_idx > 0:
                    self._main_idx -= 1
                    self._file_list.setCurrentRow(self._main_idx)
                    sound_player.play("cursor")
                else:
                    self._focus = "sidebar"
                    self._update_focus()
                    sound_player.play("cursor")
            elif key == Qt.Key.Key_Right:
                if self._icon_mode and self._main_idx < self._file_list.count() - 1:
                    self._main_idx += 1
                    self._file_list.setCurrentRow(self._main_idx)
                    sound_player.play("cursor")
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._activate_current_item()
                sound_player.play("select")
            elif key in (Qt.Key.Key_Escape, Qt.Key.Key_U):
                self.go_up()
                sound_player.play("select")
            elif key == Qt.Key.Key_H:
                self.go_home()
                sound_player.play("select")
            elif key == Qt.Key.Key_Backspace:
                self.go_back()
                sound_player.play("select")
            elif key == Qt.Key.Key_F:
                self.go_forward()
                sound_player.play("select")

        super().keyPressEvent(event)


# ── Entrypoint ─────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    sound_player.init()

    locale_dir = str(Path(__file__).parent.parent / "locale")
    translator = QTranslator(app)
    if translator.load(QLocale.system(), "file_browser", "_", locale_dir, ".qm"):
        app.installTranslator(translator)

    window = FileBrowserWindow()
    window.showFullScreen()

    def _start_pad():
        try:
            pad = find_pad([VIRTUAL_DEVICE_NAME, PHYSICAL_DEVICE_NAME])
            PadListener(pad, window=window).start()
        except RuntimeError as exc:
            print(f"Warning: gamepad not found — {exc}", file=sys.stderr)

    threading.Thread(target=_start_pad, daemon=True).start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
