"""Horizontal, scrollable bar of application tiles (static + open-window)."""

import logging
import os
from collections.abc import Callable, Sequence
from typing import _ProtocolMeta  # type: ignore[attr-defined]

from PyQt6.QtCore import Qt, QPoint, QTimer, QEasingCurve, QPropertyAnimation, pyqtSignal
from PyQt6.QtGui import QCursor, QIcon
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QScrollArea, QApplication

from domain.catalog.live_catalog import LiveCatalog
from domain.catalog.target import AppTarget, Target, target_at_index
from domain.catalog.window import Window
from domain.catalog.window_rules import external_windows, is_app_running, resolve_recall_trigger
from domain.lifecycle.process_manager import ProcessManager
from infrastructure.common.qt.ui import styles
from domain.lifecycle.tile_bar_view import TileBarView
from domain.navigation.bar_views import TileFocusView, TileReorderView
from .app_tile import AppTile, TILE_H, TILE_SEL_H
from .window_icons import WindowIconResolver

logger = logging.getLogger(__name__)


class _Meta(type(QScrollArea), _ProtocolMeta):
    """Combined metaclass so a QWidget can declare it implements a Protocol port."""

_DYN_TILE_MAX_TITLE = 22   # Maximum length of a dynamic tile title
_SCROLL_ANIM_MS     = 220  # glide duration when centering the focused tile


class TileBar(QScrollArea, TileBarView, TileFocusView, TileReorderView, metaclass=_Meta):
    """Scrollable row of tiles: configured apps first, then open-window tiles.

    Implements `TileBarView` (app-lifecycle), `TileFocusView` (focus navigation) and
    `TileReorderView` (move mode).

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

    def __init__(self, apps: LiveCatalog, app_manager: ProcessManager,
                 parent_of: Callable[[int], int | None] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._apps          = apps
        self._app_manager   = app_manager
        self._icon_resolver = WindowIconResolver()
        # Parent-PID lookup for recall-trigger inheritance (a dynamic window
        # owned by a launcher inherits its trigger). Linux injects the /proc
        # reader; platforms without a process tree (Windows) pass a no-op.
        self._parent_of     = parent_of or (lambda _pid: None)

        self._tile_index = 0
        self._focused    = True   # tiles own focus at startup
        self._scroll_anim: QPropertyAnimation | None = None
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
        # Windows promoted to a static tile via *Pin to menu*: suppressed from the
        # dynamic section so a pinned, still-open window is not shown twice (once
        # as its new static tile, once as a leftover open-window tile).
        self._pinned_window_ids: set[str]                   = set()
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
        # First-seen order of dynamic window ids — stabilises the tile order
        # across refreshes. On Windows ``EnumWindows`` returns windows in Z-order
        # (top-most first), so activating a window would reshuffle the dynamic
        # tiles without this. KWin's ``windowList()`` is already stable
        # (creation order), so this is a no-op there. New windows append to the
        # end; disappeared windows drop out (their id won't recur — ids are
        # unique per window instance).
        self._dyn_order: list[str]                          = []

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
        for app in self._apps:
            tile = self._make_static_tile(app)
            self._tile_layout.addWidget(tile)
            self._tiles.append(tile)

        self.setWidget(container)
        self._render_tiles()

    def _make_static_tile(self, app) -> AppTile:
        """Build a configured-app tile, wired to resolve its own current position.

        Icon: prefer a qtawesome glyph (X-Kasual-Icon); otherwise fall back to the
        themed ``Icon`` name via QIcon.fromTheme (AppTile uses the QIcon when given
        and non-null, else the qtawesome name). Signals bind to the tile, not a
        fixed index: move mode reorders the static tiles, so each tile resolves its
        position on demand (``_static_index_of``) and a swap needs no reconnecting.
        """
        qta_name = app.icon or "fa5s.desktop"
        qicon = None
        if not app.icon and app.icon_theme:
            themed = QIcon.fromTheme(app.icon_theme)
            if not themed.isNull():
                qicon = themed
        if qicon is None and not app.icon:
            # No glyph/theme icon (e.g. a Windows .desktop whose command is a
            # .lnk/exe): fall back to the OS shell icon. No-op on Linux, where the
            # command is a shell name rather than a file path.
            from infrastructure.common.qt.icons import shell_icon
            qicon = shell_icon(app.command)
        tile = AppTile(name=app.name, icon_name=qta_name, color=app.color, qicon=qicon)
        tile.clicked.connect(lambda t=tile: self._activate_index(self._static_index_of(t)))
        tile.hovered.connect(lambda t=tile: self._on_tile_hovered(self._static_index_of(t)))
        tile.right_clicked.connect(lambda t=tile: self._on_tile_right_clicked(self._static_index_of(t)))
        return tile

    @property
    def last_windows(self) -> list[Window]:
        """The last window list from KWin (as domain Windows)."""
        return self._last_windows

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

    def current_is_app(self) -> bool:
        """True if the focused tile is a static app tile (not a dynamic window)."""
        return isinstance(self.current_context(), AppTarget)

    # ── Move mode (TileReorderView) ──────────────────────────────────────────

    def app_tile_count(self) -> int:
        return len(self._tiles)

    def current_app_index(self) -> int:
        return self._tile_index

    def swap_app_tiles(self, i: int, j: int) -> None:
        """Exchange the static app tiles at positions *i* and *j*, on screen and in
        the in-memory catalog, and keep the focus on the moved tile."""
        if not (0 <= i < len(self._tiles) and 0 <= j < len(self._tiles)):
            return
        # The catalog is shared (LiveCatalog), so this reorder is also seen by the
        # lifecycle/deferred-hide; the AppManager keys running processes by tile
        # position, so its tracking must move with the tiles too — otherwise a
        # later restore/close after a reorder would act on the wrong app.
        self._apps.swap(i, j)
        self._app_manager.swap_indices(i, j)
        self._tiles[i], self._tiles[j] = self._tiles[j], self._tiles[i]
        # Re-seat both widgets at their new layout positions (static tiles occupy
        # layout items 0..n-1, ahead of the separator and dynamic tiles).
        lo, hi = sorted((i, j))
        self._tile_layout.removeWidget(self._tiles[lo])
        self._tile_layout.removeWidget(self._tiles[hi])
        self._tile_layout.insertWidget(lo, self._tiles[lo])
        self._tile_layout.insertWidget(hi, self._tiles[hi])
        self._tile_index = j
        self._render_tiles()

    def set_move_mode(self, active: bool) -> None:
        tile = self.current_tile()
        if isinstance(tile, AppTile):
            tile.set_moving(active)

    # ── Colour (Tile Management Popover) ─────────────────────────────────────

    def current_app_color(self) -> str | None:
        """Colour of the focused app tile, or None if it is not an app tile."""
        if 0 <= self._tile_index < len(self._tiles):
            return self._apps[self._tile_index].color
        return None

    def set_app_color(self, index: int, color: str) -> None:
        """Recolour the static app tile at *index*, on screen and in the catalog."""
        if not (0 <= index < len(self._tiles)):
            return
        self._apps.recolour(index, color)
        self._tiles[index].set_color(color)

    # ── Pin to menu (Tile Management Popover) ────────────────────────────────

    def window_for(self, window_id: str) -> Window | None:
        """The open :class:`Window` behind a dynamic tile, or None if it is gone."""
        return next((w for w in self._last_windows if w.id == window_id), None)

    def pin_window(self, app, window_id: str) -> None:
        """Promote the open-window tile *window_id* to a persistent tile for *app*.

        Appends a static tile after the configured ones (the catalog is the shared
        LiveCatalog, so the lifecycle/deferred-hide see the new app too), suppresses
        the now-pinned window from the dynamic section, and focuses the new tile.
        Existing tile indices are unchanged — the app is appended at the end — so
        the AppManager's index-keyed process tracking stays valid."""
        self._apps.append(app)
        tile = self._make_static_tile(app)
        # The pinned window is open, so the new tile is running from the start —
        # mark it now rather than waiting for the next periodic status refresh.
        tile.set_running(True)
        # Static tiles occupy layout items 0..n-1, ahead of the separator + dynamic.
        self._tile_layout.insertWidget(len(self._tiles), tile)
        self._tiles.append(tile)
        self._pinned_window_ids.add(window_id)
        # Rebuild the dynamic section so the pinned window drops out of it.
        self._dyn_signature = None
        self.update_windows(self._last_windows)
        self._tile_index = len(self._tiles) - 1
        self._render_tiles()

    def unpin_app(self, index: int) -> None:
        """Remove the static app tile at *index* — the reverse of :meth:`pin_window`.

        The app leaves the shared catalog (so the lifecycle/deferred-hide stop
        seeing it) and the AppManager's slots shift to match. Any open window the
        app owned is no longer suppressed nor matched, so the dynamic rebuild brings
        it back as an open-window tile — an *unpinned running app* lands in the
        dynamic section, an unpinned idle one simply disappears."""
        if not (0 <= index < len(self._tiles)):
            return
        app = self._apps[index]
        # Stop suppressing this app's open windows so they return as dynamic tiles.
        self._pinned_window_ids -= {
            w.id for w in self._last_windows if w.matches_app(app)
        }
        tile = self._tiles.pop(index)
        self._tile_layout.removeWidget(tile)
        tile.deleteLater()
        self._apps.remove(index)
        self._app_manager.remove_index(index)
        # Rebuild the dynamic section so the freed window reappears there.
        self._dyn_signature = None
        self.update_windows(self._last_windows)
        self._clamp_index()
        self._render_tiles()

    def _static_index_of(self, tile: AppTile) -> int:
        """Current position of a static app *tile* (it shifts during move mode)."""
        return self._tiles.index(tile)

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
        self._animate_scroll_to(max(0, target))

    def _animate_scroll_to(self, target: int) -> None:
        """Glide the horizontal scrollbar to *target* instead of jumping."""
        bar = self.horizontalScrollBar()
        if self._scroll_anim is not None:
            self._scroll_anim.stop()
        anim = QPropertyAnimation(bar, b"value", self)
        anim.setStartValue(bar.value())
        anim.setEndValue(target)
        anim.setDuration(_SCROLL_ANIM_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._scroll_anim = anim

    def set_static_closing(self, idx: int) -> None:
        self._tiles[idx].set_closing()

    def is_closing(self, idx: int) -> bool:
        """True if the static app tile at *idx* is shutting down."""
        return idx < len(self._tiles) and self._tiles[idx].is_closing()

    def has_dynamic_window(self, win_id: str) -> bool:
        return any(wid == win_id for wid, _, _ in self._dynamic_tiles)

    # ── Status refresh ──────────────────────────────────────────────────────

    def is_tile_running(self, idx: int, windows: Sequence[Window]) -> bool:
        """True if the static tile at *idx* is running — delegated to domain."""
        return is_app_running(idx, self._apps, windows, self._app_manager.is_running)

    def refresh_status(self) -> None:
        for i, tile in enumerate(self._tiles):
            tile.set_running(self.is_tile_running(i, self._last_windows))

    # ── Dynamic tiles (currently open windows) ─────────────────────────────

    def update_windows(self, windows: list[Window]) -> None:
        """Rebuild the dynamic tile section from the refreshed window list.

        Filters out windows belonging to an application launched by AppManager —
        they are already represented by a static tile. Emits ``windows_changed``
        whenever the tile set is actually rebuilt (including down to empty) so the
        coordinator can re-check active state — e.g. reactivate the desktop when
        the last open window closes.
        """
        self._last_windows = windows

        # Which windows earn a dynamic tile — the "external window" rule lives in
        # the domain. The process-group check it needs (whether a window belongs
        # to a running app's group) is the infrastructure half: an os.getpgid read
        # against the launcher pids, supplied here as a callable.
        running_pids = set(self._app_manager.all_running_pids())

        def _owned_by_running_group(window: Window) -> bool:
            # os.getpgid is Unix-only (absent on Windows → AttributeError); the
            # process-group rule simply doesn't apply there, so fall through to
            # False and let matches_app / pinned-id filtering stand on its own.
            try:
                return bool(running_pids) and os.getpgid(window.pid) in running_pids
            except (OSError, AttributeError):
                return False

        extern_windows = external_windows(windows, self._apps, _owned_by_running_group)
        # A window pinned this session is now a static tile — keep it out of the
        # dynamic section even while its window is still open (its app identity may
        # not match the pinned tile, e.g. reverse-DNS app-ids, so filter by id).
        if self._pinned_window_ids:
            extern_windows = [w for w in extern_windows if w.id not in self._pinned_window_ids]

        # Stabilise the dynamic-tile order across refreshes (see _dyn_order).
        # Rebuild the first-seen order: keep known ids in their existing order,
        # then append newly-seen ids in the order they arrived in this refresh.
        seen = {w.id: w for w in extern_windows}
        ordered: list[Window] = [seen[wid] for wid in self._dyn_order if wid in seen]
        known = set(self._dyn_order)
        new_windows: list[Window] = [w for w in extern_windows if w.id not in known]
        self._dyn_order = [wid for wid in self._dyn_order if wid in seen] + [w.id for w in new_windows]
        extern_windows = ordered + new_windows

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
        AppManager and the injected parent-PID lookup.
        """
        pid_to_app = {
            self._app_manager.running_pid(i): self._apps[i]
            for i in self._app_manager.running_idxs()
            if self._app_manager.running_pid(i) is not None
        }
        return resolve_recall_trigger(pid, pid_to_app, self._parent_of)
