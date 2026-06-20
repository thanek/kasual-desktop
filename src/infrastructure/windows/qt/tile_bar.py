"""Horizontal scrollable tile bar for Windows - static apps + dynamic windows."""

import logging
import os
from typing import Callable

from PyQt6.QtCore import Qt, QTimer, QEasingCurve, QPropertyAnimation, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QScrollArea, QApplication

from domain.catalog.live_catalog import LiveCatalog
from domain.catalog.target import AppTarget, Target, target_at_index
from domain.catalog.window import Window
from domain.catalog.window_rules import external_windows
from domain.lifecycle.process_manager import ProcessManager

from .app_tile import WindowsAppTile

logger = logging.getLogger(__name__)

TILE_H        = 200
TILE_SEL_H    = 240
SCROLL_ANIM_MS = 220

_DYN_TILE_MAX_TITLE = 22


class WindowsTileBar(QScrollArea):
    """Scrollable row of tiles: configured apps first, then open-window tiles."""

    activated         = pyqtSignal(object)
    windows_changed   = pyqtSignal()
    tile_hovered      = pyqtSignal(int)
    tile_context_menu = pyqtSignal()

    def __init__(self, apps: LiveCatalog, app_manager: ProcessManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._apps = apps
        self._app_manager = app_manager
        self._icon_resolver = _WindowsIconResolver()

        self._tile_index = 0
        self._focused = True
        self._scroll_anim: QPropertyAnimation | None = None
        self._hover_blocked = False
        self._hover_anchor: QCursor.pos() | None = None

        self._dynamic_tiles: list[tuple[str, str, WindowsAppTile]] = []
        self._pinned_window_ids: set[str] = set()
        self._dyn_separator: QWidget | None = None
        self._dynamic_pids: dict[str, int] = {}
        self._last_windows: list[Window] = []
        self._dyn_signature: tuple | None = None

        self.setFixedHeight(TILE_SEL_H + 100)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._tile_layout = QHBoxLayout(container)
        screen_half = QApplication.primaryScreen().size().width() // 2
        self._tile_layout.setContentsMargins(screen_half, 50, screen_half, 50)
        self._tile_layout.setSpacing(24)

        self._tiles: list[WindowsAppTile] = []
        for app in self._apps:
            tile = self._make_static_tile(app)
            self._tile_layout.addWidget(tile)
            self._tiles.append(tile)

        self.setWidget(container)
        self._render_tiles()

    def _make_static_tile(self, app) -> WindowsAppTile:
        icon_name = app.icon or "fa5s.desktop"
        qicon = None
        if not app.icon and hasattr(app, 'icon_theme') and app.icon_theme:
            pass
        tile = WindowsAppTile(
            name=app.name,
            icon_name=icon_name,
            color=app.color or "#2e3440",
            qicon=qicon,
        )
        idx = self._apps.index(app)
        tile.clicked.connect(lambda i=idx: self._activate_index(i))
        tile.hovered.connect(lambda i=idx: self._on_tile_hovered(i))
        tile.right_clicked.connect(lambda i=idx: self._on_tile_right_clicked(i))
        return tile

    @property
    def last_windows(self) -> list[Window]:
        return self._last_windows

    def move(self, delta: int) -> bool:
        new = self._tile_index + delta
        if not (0 <= new <= self._total() - 1):
            return False
        self._tile_index = new
        self._render_tiles()
        return True

    def suppress_hover_until_move(self) -> None:
        self._hover_blocked = True
        self._hover_anchor = None

    def set_focused(self, focused: bool, scroll: bool = True) -> None:
        self._focused = focused
        self._render_tiles(scroll=scroll)

    def select_current(self) -> None:
        self._activate_index(self._tile_index)

    def current_context(self) -> Target | None:
        return self._context_for_index(self._tile_index)

    def current_tile(self) -> WindowsAppTile | None:
        tiles = self._all_tiles()
        return tiles[self._tile_index] if 0 <= self._tile_index < len(tiles) else None

    def current_is_app(self) -> bool:
        return isinstance(self.current_context(), AppTarget)

    def current_app_index(self) -> int:
        return self._tile_index

    def swap_app_tiles(self, i: int, j: int) -> None:
        if not (0 <= i < len(self._tiles) and 0 <= j < len(self._tiles)):
            return
        self._apps.swap(i, j)
        self._app_manager.swap_indices(i, j)
        self._tiles[i], self._tiles[j] = self._tiles[j], self._tiles[i]
        lo, hi = sorted((i, j))
        self._tile_layout.removeWidget(self._tiles[lo])
        self._tile_layout.removeWidget(self._tiles[hi])
        self._tile_layout.insertWidget(lo, self._tiles[lo])
        self._tile_layout.insertWidget(hi, self._tiles[hi])
        self._tile_index = j
        self._render_tiles()

    def set_move_mode(self, active: bool) -> None:
        tile = self.current_tile()
        if isinstance(tile, WindowsAppTile):
            tile.set_moving(active)

    def current_app_color(self) -> str | None:
        if 0 <= self._tile_index < len(self._tiles):
            return self._apps[self._tile_index].color
        return None

    def set_app_color(self, index: int, color: str) -> None:
        if not (0 <= index < len(self._tiles)):
            return
        self._apps.recolour(index, color)
        self._tiles[index].set_color(color)

    def pin_window(self, app, window_id: str) -> None:
        self._apps.append(app)
        tile = self._make_static_tile(app)
        tile.set_running(True)
        self._tile_layout.insertWidget(len(self._tiles), tile)
        self._tiles.append(tile)
        self._pinned_window_ids.add(window_id)
        self._dyn_signature = None
        self.update_windows(self._last_windows)
        self._tile_index = len(self._tiles) - 1
        self._render_tiles()

    def unpin_app(self, index: int) -> None:
        if not (0 <= index < len(self._tiles)):
            return
        app = self._apps[index]
        self._pinned_window_ids -= {
            w.id for w in self._last_windows if w.matches_app(app)
        }
        tile = self._tiles.pop(index)
        self._tile_layout.removeWidget(tile)
        tile.deleteLater()
        self._apps.remove(index)
        self._app_manager.remove_index(index)
        self._dyn_signature = None
        self.update_windows(self._last_windows)
        self._clamp_index()
        self._render_tiles()

    def _static_index_of(self, tile: WindowsAppTile) -> int:
        return self._tiles.index(tile)

    def center_current(self) -> None:
        if not self._focused:
            return
        tiles = self._all_tiles()
        if not (0 <= self._tile_index < len(tiles)):
            return
        tile = tiles[self._tile_index]
        vp_w = self.viewport().width()
        target = tile.x() + tile.width() // 2 - vp_w // 2
        self._animate_scroll_to(max(0, target))

    def _animate_scroll_to(self, target: int) -> None:
        bar = self.horizontalScrollBar()
        if self._scroll_anim is not None:
            self._scroll_anim.stop()
        anim = QPropertyAnimation(bar, b"value", self)
        anim.setStartValue(bar.value())
        anim.setEndValue(target)
        anim.setDuration(SCROLL_ANIM_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._scroll_anim = anim

    def set_static_closing(self, idx: int) -> None:
        if idx < len(self._tiles):
            self._tiles[idx].set_closing()

    def is_closing(self, idx: int) -> bool:
        return idx < len(self._tiles) and self._tiles[idx].is_closing()

    def has_dynamic_window(self, win_id: str) -> bool:
        return any(wid == win_id for wid, _, _ in self._dynamic_tiles)

    def is_tile_running(self, idx: int, windows: list[Window]) -> bool:
        if 0 <= idx < len(self._tiles):
            app = self._apps[idx]
            for w in windows:
                if w.matches_app(app):
                    return True
        return False

    def refresh_status(self) -> None:
        for i, tile in enumerate(self._tiles):
            tile.set_running(self.is_tile_running(i, self._last_windows))

    def update_windows(self, windows: list[Window]) -> None:
        self._last_windows = windows

        running_pids = set(self._app_manager.all_running_pids())

        def owned_by_running_group(window: Window) -> bool:
            try:
                return bool(running_pids) and os.getpgid(window.pid) in running_pids
            except OSError:
                return False

        extern_windows = external_windows(windows, self._apps, owned_by_running_group)

        if self._pinned_window_ids:
            extern_windows = [w for w in extern_windows if w.id not in self._pinned_window_ids]

        signature = tuple(
            (w.id, w.title, w.desktop_file, w.resource_class) for w in extern_windows
        )
        if signature == self._dyn_signature:
            return
        self._dyn_signature = signature

        self._clear_dynamic_tiles()

        if not extern_windows:
            self._clamp_index()
            self._render_tiles()
            self.windows_changed.emit()
            return

        sep = QWidget()
        sep.setFixedSize(2, TILE_H - 24)
        sep.setStyleSheet("background: #3b4252;")
        self._tile_layout.addWidget(sep)
        self._dyn_separator = sep

        for w in extern_windows:
            full_title = w.title
            app_name = self._icon_resolver.resolve_name(w.desktop_file, w.resource_class)
            combined = f"{app_name} ({full_title})" if app_name and app_name != full_title else app_name or full_title
            display_title = combined[:_DYN_TILE_MAX_TITLE] + "..." if len(combined) > _DYN_TILE_MAX_TITLE else combined
            app_icon = self._icon_resolver.resolve_icon(w.desktop_file, w.resource_class, w.pid)
            tile = WindowsAppTile(
                name=display_title,
                icon_name='fa5s.window-maximize',
                color='#2e3440',
                qicon=app_icon,
                full_name=combined,
            )
            tile.set_running(True)
            win_id = w.id
            abs_idx = len(self._tiles) + len(self._dynamic_tiles)
            tile.clicked.connect(lambda wid=win_id: self._on_dynamic_clicked(wid))
            tile.hovered.connect(lambda i=abs_idx: self._on_tile_hovered(i))
            tile.right_clicked.connect(lambda i=abs_idx: self._on_tile_right_clicked(i))
            self._tile_layout.addWidget(tile)
            self._dynamic_tiles.append((win_id, full_title, tile))
            self._dynamic_pids[win_id] = w.pid

        self._clamp_index()
        self._render_tiles()
        logger.debug('Dynamic tiles: %d', len(self._dynamic_tiles))
        self.windows_changed.emit()

    def _total(self) -> int:
        return len(self._tiles) + len(self._dynamic_tiles)

    def _all_tiles(self) -> list[WindowsAppTile]:
        return self._tiles + [t for _, _, t in self._dynamic_tiles]

    def _clamp_index(self) -> None:
        total = self._total()
        if total == 0:
            self._tile_index = 0
        elif self._tile_index >= total:
            self._tile_index = total - 1

    def _render_tiles(self, scroll: bool = True) -> None:
        n_static = len(self._tiles)
        for i, tile in enumerate(self._tiles):
            tile.set_selected(self._focused and i == self._tile_index)
        for i, (_, _, tile) in enumerate(self._dynamic_tiles):
            tile.set_selected(self._focused and (n_static + i) == self._tile_index)
        if self._focused and scroll:
            QTimer.singleShot(0, self.center_current)

    def _clear_dynamic_tiles(self) -> None:
        for _, _, tile in self._dynamic_tiles:
            self._tile_layout.removeWidget(tile)
            tile.deleteLater()
        self._dynamic_tiles.clear()
        self._dynamic_pids.clear()
        if self._dyn_separator is not None:
            self._tile_layout.removeWidget(self._dyn_separator)
            self._dyn_separator.deleteLater()
            self._dyn_separator = None

    def _activate_index(self, idx: int) -> None:
        ctx = self._context_for_index(idx)
        if ctx is not None:
            self.activated.emit(ctx)

    def _on_tile_hovered(self, idx: int) -> None:
        if self._hover_blocked:
            pos = QCursor.pos()
            if self._hover_anchor is None:
                self._hover_anchor = pos
                return
            if pos == self._hover_anchor:
                return
            self._hover_blocked = False
            self._hover_anchor = None
        changed = self._tile_index != idx or not self._focused
        self._tile_index = idx
        self._render_tiles(scroll=False)
        QTimer.singleShot(0, self._ensure_tile_visible)
        if changed:
            self.tile_hovered.emit(idx)

    def _ensure_tile_visible(self) -> None:
        tiles = self._all_tiles()
        if 0 <= self._tile_index < len(tiles):
            self.ensureWidgetVisible(tiles[self._tile_index], xMargin=60, yMargin=0)

    def _on_tile_right_clicked(self, idx: int) -> None:
        self._tile_index = idx
        self._render_tiles(scroll=False)
        self.tile_context_menu.emit()

    def _on_dynamic_clicked(self, win_id: str) -> None:
        n_static = len(self._tiles)
        for j, (wid, _, _) in enumerate(self._dynamic_tiles):
            if wid == win_id:
                self._activate_index(n_static + j)
                return

    def _context_for_index(self, idx: int) -> Target | None:
        dyn_windows = [
            Window(id=wid, title=title, pid=self._dynamic_pids.get(wid, 0))
            for wid, title, _ in self._dynamic_tiles
        ]
        return target_at_index(idx, self._apps, dyn_windows, self._find_trigger_for_pid)

    def _find_trigger_for_pid(self, pid: int) -> str:
        pid_to_app = {
            self._app_manager.running_pid(i): self._apps[i]
            for i in self._app_manager.running_idxs()
            if self._app_manager.running_pid(i) is not None
        }
        return "CLICK"


class _WindowsIconResolver:
    """Stub icon resolver for Windows."""

    def resolve_name(self, desktop_file: str | None, resource_class: str | None) -> str | None:
        if desktop_file:
            name = os.path.splitext(os.path.basename(desktop_file))[0]
            return name.replace('-', ' ').replace('_', ' ').title()
        if resource_class:
            return resource_class
        return None

    def resolve_icon(self, desktop_file: str | None, resource_class: str | None, pid: int):
        return None