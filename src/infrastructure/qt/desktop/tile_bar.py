"""Horizontal, scrollable bar of application tiles (static + open-window)."""

import logging
import os

from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QIcon
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QScrollArea, QApplication

from domain.app import App
from domain.target import Target, target_at_index
from domain.window import Window, external_windows, resolve_recall_trigger
from infrastructure.system.app_manager import AppManager
from infrastructure.system.window_manager import to_window
from infrastructure.qt.ui import styles
from .app_tile import AppTile, TILE_H, TILE_SEL_H
from .window_icons import WindowIconResolver

logger = logging.getLogger(__name__)

_DYN_TILE_MAX_TITLE = 22   # Maximum length of a dynamic tile title


def _get_ppid(pid: int) -> int | None:
    """Return the parent PID of *pid* by reading /proc, or None on failure."""
    try:
        with open(f'/proc/{pid}/status') as f:
            for line in f:
                if line.startswith('PPid:'):
                    return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return None


class TileBar(QScrollArea):
    """Scrollable row of tiles: configured apps first, then open-window tiles.

    Navigation between the tile bar and the top bar lives in the Desktop
    coordinator; this widget only renders the highlight it is told to own via
    :meth:`set_focused` and reports user intent through its signals:

      * ``activated(dict)``       — a tile was chosen (app/window context dict)
      * ``windows_changed()``     — the dynamic-tile set was rebuilt
    """

    activated        = pyqtSignal(object)   # Target (AppTarget | WindowTarget)
    windows_changed  = pyqtSignal()
    tile_hovered     = pyqtSignal(int)
    tile_context_menu = pyqtSignal()

    def __init__(self, apps: list[App], app_manager: AppManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._apps          = apps
        self._app_manager   = app_manager
        self._icon_resolver = WindowIconResolver()

        self._tile_index = 0
        self._focused    = True   # tiles own focus at startup
        # Hover suppression armed when the Desktop (re)appears, so a tile sitting
        # under a stationary cursor doesn't grab selection via the synthetic
        # enterEvent Qt delivers when the window maps under the pointer.
        #
        # The anchor is latched on the FIRST hover (not at arm time): on Wayland
        # QCursor.pos() is stale while the window is hidden, but it is reliable
        # during an enterEvent. Subsequent hovers at the same point (e.g. the
        # tile bar scrolling under a parked cursor) stay ignored; a genuine move
        # to a different point lifts the block.
        self._hover_blocked = False
        self._hover_anchor: QPoint | None = None

        # Dynamic tiles: list of (window_id, title, AppTile)
        self._dynamic_tiles: list[tuple[str, str, AppTile]] = []
        self._dyn_separator: QWidget | None                 = None
        # window_id → pid for dynamic tiles (used for trigger inheritance)
        self._dynamic_pids:  dict[str, int]                 = {}
        # Last window list from KWin (as domain Windows) — used for the
        # window-presence running check in is_tile_running.
        self._last_windows:  list[Window]                   = []
        # Signature of the currently displayed dynamic tiles — lets a periodic
        # KWin refresh skip the teardown/rebuild when nothing visible changed,
        # so an in-progress tile marquee animation is not restarted.
        self._dyn_signature: tuple | None                   = None

        self.setFixedHeight(TILE_SEL_H + 100)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._tile_layout = QHBoxLayout(container)
        # Half-screen padding on each side so any tile can be scrolled to center.
        screen_half = QApplication.primaryScreen().size().width() // 2
        self._tile_layout.setContentsMargins(screen_half, 50, screen_half, 50)
        self._tile_layout.setSpacing(24)

        self._tiles: list[AppTile] = []
        for i, app in enumerate(self._apps):
            # Icon: prefer a qtawesome glyph (X-Kasual-Icon); otherwise fall back
            # to the themed `Icon` name via QIcon.fromTheme. AppTile uses the
            # QIcon when given (and non-null), else the qtawesome name.
            qta_name = app.icon or "fa5s.desktop"
            qicon = None
            if not app.icon and app.icon_theme:
                themed = QIcon.fromTheme(app.icon_theme)
                if not themed.isNull():
                    qicon = themed
            tile = AppTile(
                name=app.name,
                icon_name=qta_name,
                color=app.color,
                qicon=qicon,
            )
            tile.clicked.connect(lambda idx=i: self._activate_index(idx))
            tile.hovered.connect(lambda idx=i: self._on_tile_hovered(idx))
            tile.right_clicked.connect(lambda idx=i: self._on_tile_right_clicked(idx))
            self._tile_layout.addWidget(tile)
            self._tiles.append(tile)

        self.setWidget(container)
        self._render_tiles()

    # ── Navigation / focus ──────────────────────────────────────────────────

    def move(self, delta: int) -> bool:
        """Shift focus by *delta* within bounds. Returns True if it moved."""
        new = self._tile_index + delta
        if not (0 <= new <= self._total() - 1):
            return False
        self._tile_index = new
        self._render_tiles()
        return True

    def suppress_hover_until_move(self) -> None:
        """Ignore tile hovers until the mouse genuinely moves.

        Called when the Desktop becomes visible (e.g. after an app exits). The
        window maps under whatever stationary position the cursor was left at,
        and Qt delivers a synthetic enterEvent to the tile underneath — without
        this guard that tile would steal selection even though the user never
        moved the mouse onto it. The reference position is latched on the first
        hover (see __init__), since QCursor.pos() is unreliable here on Wayland.
        """
        self._hover_blocked = True
        self._hover_anchor  = None

    def set_focused(self, focused: bool, scroll: bool = True) -> None:
        """Whether the tile bar (vs the top bar) owns the focus highlight."""
        self._focused = focused
        self._render_tiles(scroll=scroll)

    def select_current(self) -> None:
        """Activate the focused tile (as if it were clicked)."""
        self._activate_index(self._tile_index)

    def current_context(self) -> Target | None:
        """Foreground Target for the focused tile, or None if out of range."""
        return self._context_for_index(self._tile_index)

    def current_tile(self) -> AppTile | None:
        tiles = self._all_tiles()
        return tiles[self._tile_index] if 0 <= self._tile_index < len(tiles) else None

    def center_current(self) -> None:
        if not self._focused:
            return
        tiles = self._all_tiles()
        if not (0 <= self._tile_index < len(tiles)):
            return
        tile = tiles[self._tile_index]
        vp_w = self.viewport().width()
        # tile.x() is relative to the container; center it in the viewport.
        target = tile.x() + tile.width() // 2 - vp_w // 2
        self.horizontalScrollBar().setValue(max(0, target))

    def set_static_closing(self, idx: int) -> None:
        self._tiles[idx].set_closing()

    def has_dynamic_window(self, win_id: str) -> bool:
        return any(wid == win_id for wid, _, _ in self._dynamic_tiles)

    # ── Status refresh ──────────────────────────────────────────────────────

    def is_tile_running(self, idx: int) -> bool:
        """True if the static tile at *idx* is running — either via AppManager
        (launched by Kasual) or via a visible KWin window (launched externally
        or after a self-relaunch that lost the process-group link)."""
        if self._app_manager.is_running(idx):
            return True
        if self._last_windows and idx < len(self._apps):
            app = self._apps[idx]
            return any(w.matches_app(app) for w in self._last_windows)
        return False

    def refresh_status(self) -> None:
        for i, tile in enumerate(self._tiles):
            tile.set_running(self.is_tile_running(i))

    # ── Dynamic tiles (currently open windows) ─────────────────────────────

    def update_windows(self, raw_windows: list[dict]) -> None:
        """Rebuild the dynamic tile section from the KWin window list.

        Filters out windows belonging to an application launched by AppManager —
        they are already represented by a static tile. Emits ``windows_changed``
        whenever the tile set is actually rebuilt (including down to empty) so the
        coordinator can re-check active state — e.g. reactivate the desktop when
        the last open window closes.
        """
        windows = [to_window(w) for w in raw_windows]
        self._last_windows = windows

        # Which windows earn a dynamic tile — the "external window" rule lives in
        # the domain. The process-group check it needs (whether a window belongs
        # to a running app's group) is the infrastructure half: an os.getpgid read
        # against the launcher pids, supplied here as a callable.
        running_pids = set(self._app_manager.all_running_pids())

        def _owned_by_running_group(window: Window) -> bool:
            try:
                return bool(running_pids) and os.getpgid(window.pid) in running_pids
            except OSError:
                return False

        extern_windows = external_windows(windows, self._apps, _owned_by_running_group)

        # The window list is refreshed periodically (every few seconds). When the
        # visible dynamic tiles are unchanged, skip the teardown/rebuild entirely —
        # recreating the AppTiles would restart any in-progress marquee animation.
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

        # Visual separator between static and dynamic tiles
        sep = QWidget()
        sep.setFixedSize(2, TILE_H - 24)
        sep.setStyleSheet("background: #3b4252;")
        self._tile_layout.addWidget(sep)
        self._dyn_separator = sep

        for w in extern_windows:
            full_title = w.title
            app_name   = self._icon_resolver.resolve_name(w.desktop_file, w.resource_class)
            if app_name and app_name != full_title:
                combined = f"{app_name} ({full_title})"
            else:
                combined = app_name or full_title
            display_title = styles.truncate(combined, _DYN_TILE_MAX_TITLE)
            app_icon = self._icon_resolver.resolve_icon(
                w.desktop_file, w.resource_class, w.pid,
            )
            tile = AppTile(
                name=display_title,
                icon_name='fa5s.window-maximize',
                color='#2e3440',
                qicon=app_icon,
                full_name=combined,
            )
            tile.set_running(True)   # window exists → application is running
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

    # ── Private helpers ─────────────────────────────────────────────────────

    def _total(self) -> int:
        return len(self._tiles) + len(self._dynamic_tiles)

    def _all_tiles(self) -> list[AppTile]:
        """Static tiles followed by dynamic (open-window) tiles, in display order."""
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
        n_static = len(self._tiles)
        # Ignore activation while a static app is shutting down — proc.poll() still
        # reports it as running, so a restore would hide the Desktop and try to
        # activate a window that's about to disappear.
        if idx < n_static and self._tiles[idx].is_closing():
            return
        ctx = self._context_for_index(idx)
        if ctx is not None:
            self.activated.emit(ctx)

    def _on_tile_hovered(self, idx: int) -> None:
        if self._hover_blocked:
            pos = QCursor.pos()
            if self._hover_anchor is None:
                # First hover after the Desktop appeared: the synthetic enter
                # under the parked cursor. Latch its (now-reliable) position and
                # ignore it.
                self._hover_anchor = pos
                return
            if pos == self._hover_anchor:
                # Same parked point (e.g. the bar scrolling under the cursor).
                return
            # The cursor genuinely moved → honour hovers again from now on.
            self._hover_blocked = False
            self._hover_anchor  = None
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
        """Resolve a tile index to a foreground Target, or None if out of range.

        The static-then-dynamic position→Target rule lives in the domain; this
        only supplies the open windows (rebuilt from the dynamic-tile state) and
        the pid→trigger resolver."""
        dyn_windows = [
            Window(id=wid, title=title, pid=self._dynamic_pids.get(wid, 0))
            for wid, title, _ in self._dynamic_tiles
        ]
        return target_at_index(idx, self._apps, dyn_windows, self._find_trigger_for_pid)

    def _find_trigger_for_pid(self, pid: int) -> str:
        """Recall trigger a dynamic-tile window owned by *pid* should inherit.

        The ownership rule (walk the parent chain to the owning app, default
        CLICK) lives in the domain; this only supplies the pid→app map from the
        AppManager and the /proc parent lookup.
        """
        pid_to_app = {
            self._app_manager.running_pid(i): self._apps[i]
            for i in self._app_manager.running_idxs()
            if self._app_manager.running_pid(i) is not None
        }
        return resolve_recall_trigger(pid, pid_to_app, _get_ppid)
