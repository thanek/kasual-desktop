import logging
import os
from collections.abc import Callable

import qtawesome as qta
from PyQt6.QtCore import Qt, QLocale, QTimer, QSize, QEvent
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QHBoxLayout, QVBoxLayout,
    QScrollArea, QLabel,
    QApplication,
)

from audio import sound_player
from input.gamepad_watcher import GamepadWatcher, BTN_MODE_CLICK, BTN_MODE_HOLD_1S
from overlays.base_overlay import BaseOverlay
from overlays.confirm_dialog import ConfirmDialog
from overlays.info_dialog import InfoDialog
from overlays.tile_popover import TilePopoverMenu
from overlays.volume_overlay import VolumeOverlay
from system.app_manager import AppManager
from system.system_actions import ACTIONS, ActionDeps, ActionRunner
from system.window_manager import KWinWindowManager
from ui import styles
from .app_tile import AppTile, TILE_H, TILE_SEL_H
from .wallpaper import KdeWallpaperLoader
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


class Desktop(QWidget):
    """Main environment window — always fullscreen."""

    def __init__(
        self,
        apps: list[dict],
        gamepad: GamepadWatcher,
        window_manager: KWinWindowManager,
    ):
        super().__init__()
        self._apps        = apps
        self._gamepad     = gamepad
        self._wm          = window_manager
        self._app_manager = AppManager(self)
        self._focus_mode     = "tiles"   # "tiles" | "topbar"
        self._tile_index     = 0
        self._topbar_index   = 0
        self._confirm_dialog = None
        self._volume_overlay = None
        self._is_paused      = False
        # Reference-counted "minimal mode" — when >0, topbar and tile bar are
        # hidden so the only thing showing through an overlay's translucent
        # background is the wallpaper.
        self._overlay_depth  = 0

        # Dynamic tiles: list of (window_id, title, AppTile)
        self._dynamic_tiles:  list[tuple[str, str, AppTile]] = []
        self._dyn_separator:  QWidget | None                 = None
        # window_id → pid for dynamic tiles (used for trigger inheritance)
        self._dynamic_pids:   dict[str, int]                 = {}
        # Last window list from KWin — used for window-presence running checks
        self._last_windows:   list[dict]                     = []
        # Currently active app/window — what BTN_MODE context menu will target
        # {'type': 'app', 'id': idx, 'name': ...} or {'type': 'dyn', 'id': win_id, 'name': ...}
        # dyn contexts also carry 'trigger' (BTN_MODE_CLICK / BTN_MODE_HOLD_1S)
        self._active_context: dict | None                    = None

        self.setWindowTitle("Kasual Desktop")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        self._topbar = self._build_topbar()
        main.addWidget(self._topbar)
        main.addStretch(1)
        main.addWidget(self._build_tile_bar())
        main.addStretch(1)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_tile_status)
        self._status_timer.start(500)

        self._wallpaper: 'QPixmap | None' = KdeWallpaperLoader().load()
        self._icon_resolver = WindowIconResolver()

        self._action_runner = ActionRunner(
            ActionDeps(desktop=self),
            lambda q, cb: self._show_confirm(question=q, on_confirmed=cb),
        )

        self._app_manager.app_finished.connect(self._on_app_finished)
        self._app_manager.app_launch_failed.connect(self._on_app_launch_failed)
        self._wm.windows_updated.connect(self._rebuild_dynamic_tiles)

        QApplication.instance().installEventFilter(self)

        # Desktop is not shown at startup — we wait for the connected_changed(True) signal

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def app_manager(self) -> AppManager:
        return self._app_manager

    def show_desktop(self) -> None:
        """Show the desktop without interrupting the running application."""
        self._active_context = None
        self._gamepad.push_handler(self._handle_pad)
        self._wm.refresh_now()
        self.showFullScreen()
        self._restore_overlays()
        self.activateWindow()

    def enter_overlay_mode(self) -> None:
        """Hide topbar and tile bar so an overlay shows only the wallpaper."""
        self._overlay_depth += 1
        if self._overlay_depth == 1:
            self._topbar.hide()
            self._scroll.hide()

    def exit_overlay_mode(self) -> None:
        """Restore topbar and tile bar when the last overlay closes."""
        self._overlay_depth = max(0, self._overlay_depth - 1)
        if self._overlay_depth == 0:
            self._topbar.show()
            self._scroll.show()

    @property
    def _active_overlays(self) -> list[BaseOverlay]:
        """Active overlays (those that can be paused/resumed)."""
        return [o for o in (self._volume_overlay, self._confirm_dialog) if o is not None]

    def pause(self) -> None:
        """Hide the Desktop without disconnecting the gamepad (minimize to tray)."""
        sound_player.play("exit")
        self._is_paused = True
        for overlay in self._active_overlays:
            overlay.pause()
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()

    def resume(self) -> None:
        """Restore the Desktop after reconnecting the gamepad — without resetting state."""
        self._gamepad.push_handler(self._handle_pad)
        sound_player.play("start")
        self.showFullScreen()
        self._restore_overlays()
        self.activateWindow()

    def _restore_overlays(self) -> None:
        """Restore overlays hidden by pause(). No-op if we were not paused."""
        if not self._is_paused:
            return
        self._is_paused = False
        for overlay in self._active_overlays:
            overlay.resume()

    def current_app(self) -> dict | None:
        """Returns the currently active app/window context, or None if on desktop."""
        return self._active_context

    def restore_app(self, app) -> None:
        sound_player.play("select")
        if app['type'] == 'app':
            idx = app['id']
            trigger = self._apps[idx].get("recall_menu_trigger", BTN_MODE_CLICK)
            self._gamepad.set_app_btn_mode_trigger(trigger)
            self._arrange_windows(self._app_manager.running_pid(idx))
        else:
            self._gamepad.set_app_btn_mode_trigger(app.get('trigger', BTN_MODE_CLICK))
            self._wm.activate_window(app['id'])
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()

    def request_close_app(self, app) -> None:
        display = styles.truncate(app['name'], 40)

        def _confirmed() -> None:
            self._restore_desktop_view()
            if app['type'] == 'app':
                self._tiles[app['id']].set_closing()
                self._app_manager.terminate(app['id'])
            else:
                self._active_context = None
                self._wm.close_window(app['id'])
                QTimer.singleShot(1000, self._wm.refresh_now)

        self._show_confirm(
            question=self.tr('Are you sure you want to close\n"{0}"?').format(display),
            on_confirmed=_confirmed,
            on_cancelled=self._restore_desktop_view,
        )


    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._center_focused_tile)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, '_scroll'):
            QTimer.singleShot(0, self._center_focused_tile)

    def paintEvent(self, _) -> None:
        painter = QPainter(self)
        if self._wallpaper and not self._wallpaper.isNull():
            scaled = self._wallpaper.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width()  - scaled.width())  // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.fillRect(self.rect(), QColor("#0b140e"))

    # ── Top bar ────────────────────────────────────────────────────────────

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(80)
        bar.setStyleSheet("background-color: rgba(15, 17, 25, 210);")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(0)

        BTN_SIZE    = 56
        BTN_SPACING = 14
        BTNS_TOTAL  = len(ACTIONS) * BTN_SIZE + (len(ACTIONS) - 1) * BTN_SPACING

        spacer = QWidget()
        spacer.setFixedWidth(BTNS_TOTAL)
        spacer.setStyleSheet("background: transparent;")
        layout.addWidget(spacer)

        layout.addStretch(1)

        lbl_style = "font-size: 26px; color: white; background: transparent;"
        self._date_lbl = QLabel()
        self._date_lbl.setStyleSheet(lbl_style)
        layout.addWidget(self._date_lbl)

        layout.addSpacing(18)

        def clock_part(w: int) -> QLabel:
            l = QLabel()
            l.setStyleSheet(lbl_style)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setFixedWidth(w)
            return l

        def sep() -> QLabel:
            l = QLabel(":")
            l.setStyleSheet(lbl_style)
            return l

        self._lbl_h = clock_part(38)
        self._lbl_m = clock_part(38)
        self._lbl_s = clock_part(38)
        for w in (self._lbl_h, sep(), self._lbl_m, sep(), self._lbl_s):
            layout.addWidget(w)

        layout.addStretch(1)

        self._topbar_buttons: list[QPushButton] = []
        btn_area = QWidget()
        btn_area.setFixedWidth(BTNS_TOTAL)
        btn_area.setStyleSheet("background: transparent;")
        btn_layout = QHBoxLayout(btn_area)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(BTN_SPACING)
        for i, (action_type, action) in enumerate(ACTIONS.items()):
            btn = QPushButton()
            btn.setFixedSize(BTN_SIZE, BTN_SIZE)
            btn.setIcon(qta.icon(action["icon"], color="white"))
            btn.setIconSize(QSize(24, 24))
            btn.setStyleSheet(styles.topbar_normal(action["color"]))
            btn.clicked.connect(lambda _, t=action_type: self._topbar_action(t))
            btn_layout.addWidget(btn)
            self._topbar_buttons.append(btn)
        layout.addWidget(btn_area)

        self._update_clock()
        clock_timer = QTimer(self)
        clock_timer.timeout.connect(self._update_clock)
        clock_timer.start(1000)

        return bar

    def _update_clock(self) -> None:
        from datetime import datetime
        now    = datetime.now()
        locale = QLocale.system()
        # QLocale numbers days 1=Monday … 7=Sunday, datetime.weekday() 0…6
        day   = locale.dayName(now.weekday() + 1, QLocale.FormatType.LongFormat)
        month = locale.monthName(now.month, QLocale.FormatType.ShortFormat)
        self._date_lbl.setText(f"{day}  {now.day:02d} {month}. {now.year}")
        self._lbl_h.setText(now.strftime("%H"))
        self._lbl_m.setText(now.strftime("%M"))
        self._lbl_s.setText(now.strftime("%S"))

    # ── Tile area ──────────────────────────────────────────────────────────

    def _build_tile_bar(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setFixedHeight(TILE_SEL_H + 40)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._tile_layout = QHBoxLayout(container)
        # Half-screen padding on each side so any tile can be scrolled to center.
        screen_half = QApplication.primaryScreen().size().width() // 2
        self._tile_layout.setContentsMargins(screen_half, 20, screen_half, 20)
        self._tile_layout.setSpacing(30)

        self._tiles: list[AppTile] = []
        for i, app in enumerate(self._apps):
            tile = AppTile(
                name=app["name"],
                icon_name=app.get("icon", "fa5s.desktop"),
                color=app.get("color", "#2e3440"),
            )
            tile.clicked.connect(lambda idx=i: self._on_tile_clicked(idx))
            self._tile_layout.addWidget(tile)
            self._tiles.append(tile)

        scroll.setWidget(container)
        self._scroll = scroll

        self._update_focus()
        return scroll

    # ── Dynamic tiles (currently open windows) ─────────────────────────────

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

    def _check_active_dyn_gone(self) -> None:
        """If the active dynamic window disappeared (closed by the app) → show desktop."""
        if self._active_context is not None and self._active_context.get('type') == 'dyn':
            active_ids = {wid for wid, _, _ in self._dynamic_tiles}
            if self._active_context['id'] not in active_ids:
                self._active_context = None
                if not self.isVisible():
                    self._gamepad.push_handler(self._handle_pad)
                    self.showFullScreen()
                    self.activateWindow()

    def _find_trigger_for_pid(self, pid: int) -> str:
        """Return the recall_menu_trigger of the static app that owns *pid*.

        Walks the ppid chain upward looking for any PID tracked by AppManager.
        Needed so that games launched by Steam inherit Steam's BTN_MODE_HOLD_1S
        rather than using the dynamic-tile default (BTN_MODE_CLICK).
        """
        if pid == 0:
            return BTN_MODE_CLICK
        pid_to_idx = {
            self._app_manager.running_pid(i): i
            for i in self._app_manager.running_idxs()
            if self._app_manager.running_pid(i) is not None
        }
        visited: set[int] = set()
        current = pid
        while current > 1 and current not in visited:
            visited.add(current)
            if current in pid_to_idx:
                idx = pid_to_idx[current]
                return self._apps[idx].get('recall_menu_trigger', BTN_MODE_CLICK)
            ppid = _get_ppid(current)
            if ppid is None:
                break
            current = ppid
        return BTN_MODE_CLICK

    def _rebuild_dynamic_tiles(self, windows: list[dict]) -> None:
        """Rebuilds the dynamic tile section based on the list from KWin.

        Filters out windows belonging to the application launched by AppManager —
        they are already represented by a static tile.
        """
        self._clear_dynamic_tiles()
        self._last_windows = windows

        # Exclude windows belonging to any of our static applications.
        # Two complementary checks — each handles cases the other misses:
        #   1. pgid match: works for apps (Heroic, Firefox) that stay in the
        #      same process group as the launcher.
        #   2. resourceClass/desktopFile match: works for apps (Steam) that
        #      self-relaunch in a new process group, losing the pgid link.
        #      Uses all *defined* apps so filtering survives a Steam restart.
        running_pids  = set(self._app_manager.all_running_pids())
        defined_cmds  = {os.path.basename(a['command']).lower() for a in self._apps}

        def _is_managed_window(w: dict) -> bool:
            pid = w.get('pid', 0)
            if pid == 0:
                return False
            try:
                if running_pids and os.getpgid(pid) in running_pids:
                    return True
            except OSError:
                pass
            rc = w.get('resourceClass', '').lower()
            df = os.path.splitext(w.get('desktopFile', '').lower())[0]
            return rc in defined_cmds or df in defined_cmds

        extern_windows = [w for w in windows if not _is_managed_window(w)]

        if not extern_windows:
            self._clamp_tile_index()
            self._update_focus()
            return

        # Visual separator between static and dynamic tiles
        sep = QWidget()
        sep.setFixedSize(2, TILE_H - 24)
        sep.setStyleSheet("background: #3b4252;")
        self._tile_layout.addWidget(sep)
        self._dyn_separator = sep

        for w in extern_windows:
            full_title = w['title']
            app_name   = self._icon_resolver.resolve_name(
                w.get('desktopFile', ''), w.get('resourceClass', '')
            )
            if app_name and app_name != full_title:
                combined = f"{app_name} ({full_title})"
            else:
                combined = app_name or full_title
            display_title = styles.truncate(combined, _DYN_TILE_MAX_TITLE)
            app_icon = self._icon_resolver.resolve_icon(
                w.get('desktopFile', ''),
                w.get('resourceClass', ''),
            )
            tile = AppTile(
                name=display_title,
                icon_name='fa5s.window-maximize',
                color='#2e3440',
                qicon=app_icon,
            )
            tile.set_running(True)   # window exists → application is running
            win_id = w['id']
            tile.clicked.connect(lambda wid=win_id: self._on_dynamic_tile_clicked(wid))
            self._tile_layout.addWidget(tile)
            self._dynamic_tiles.append((win_id, full_title, tile))
            self._dynamic_pids[win_id] = w.get('pid', 0)

        self._clamp_tile_index()
        self._update_focus()
        logger.debug('Dynamic tiles: %d', len(self._dynamic_tiles))
        self._check_active_dyn_gone()

    def _on_dynamic_tile_clicked(self, window_id: str) -> None:
        title   = next((t for wid, t, _ in self._dynamic_tiles if wid == window_id), window_id)
        pid     = self._dynamic_pids.get(window_id, 0)
        trigger = self._find_trigger_for_pid(pid)
        self._active_context = {'type': 'dyn', 'id': window_id, 'name': title, 'trigger': trigger}
        self.restore_app(self._active_context)

    # ── Focus and style ────────────────────────────────────────────────────

    def _total_tiles(self) -> int:
        return len(self._tiles) + len(self._dynamic_tiles)

    def _clamp_tile_index(self) -> None:
        total = self._total_tiles()
        if total == 0:
            self._tile_index = 0
        elif self._tile_index >= total:
            self._tile_index = total - 1

    def _update_focus(self) -> None:
        in_tiles  = self._focus_mode == "tiles"
        n_static  = len(self._tiles)

        for i, tile in enumerate(self._tiles):
            tile.set_selected(in_tiles and i == self._tile_index)

        for i, (_, _, tile) in enumerate(self._dynamic_tiles):
            tile.set_selected(in_tiles and (n_static + i) == self._tile_index)

        for i, btn in enumerate(self._topbar_buttons):
            if self._focus_mode == "topbar" and i == self._topbar_index:
                btn.setStyleSheet(styles.topbar_selected())
            else:
                btn.setStyleSheet(styles.topbar_normal(list(ACTIONS.values())[i]["color"]))

        if in_tiles:
            QTimer.singleShot(0, self._center_focused_tile)

    def _center_focused_tile(self) -> None:
        if self._focus_mode != "tiles":
            return
        all_tiles: list[AppTile] = self._tiles + [t for _, _, t in self._dynamic_tiles]
        if not (0 <= self._tile_index < len(all_tiles)):
            return
        tile = all_tiles[self._tile_index]
        vp_w = self._scroll.viewport().width()
        # tile.x() is relative to the container; center it in the viewport.
        target = tile.x() + tile.width() // 2 - vp_w // 2
        self._scroll.horizontalScrollBar().setValue(max(0, target))

    def _refresh_tile_status(self) -> None:
        for i, tile in enumerate(self._tiles):
            is_running = self._app_manager.is_running(i)
            if not is_running and self._last_windows:
                # AppManager may have lost track after a self-relaunch (e.g. Steam
                # updates itself and restarts in a new process group). Keep the
                # tile marked as running as long as a matching window is visible.
                cmd = os.path.basename(self._apps[i]['command']).lower()
                is_running = any(
                    w.get('resourceClass', '').lower() == cmd or
                    os.path.splitext(w.get('desktopFile', '').lower())[0] == cmd
                    for w in self._last_windows
                )
            tile.set_running(is_running)

    # ── Gamepad handler ────────────────────────────────────────────────────

    _KEY_MAP = {
        Qt.Key.Key_Left:   "left",
        Qt.Key.Key_Right:  "right",
        Qt.Key.Key_Up:     "up",
        Qt.Key.Key_Down:   "down",
        Qt.Key.Key_Return: "select",
        Qt.Key.Key_Enter:  "select",
        Qt.Key.Key_Escape: "cancel",
        Qt.Key.Key_Q:      "close",
    }

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.KeyPress or not self.isActiveWindow():
            return False
        mapped = self._KEY_MAP.get(event.key())
        if mapped:
            self._gamepad.inject(mapped)
            return True
        return False

    def _handle_pad(self, event: str) -> None:
        if self._focus_mode == "tiles":
            max_idx = self._total_tiles() - 1
            if event == "left" and self._tile_index > 0:
                self._tile_index -= 1
                self._update_focus()
                sound_player.play("cursor")
            elif event == "right" and self._tile_index < max_idx:
                self._tile_index += 1
                self._update_focus()
                sound_player.play("cursor")
            elif event == "up" and self._topbar_buttons:
                self._focus_mode = "topbar"
                self._topbar_index = 0
                self._update_focus()
                sound_player.play("cursor")
            elif event == "select":
                self._on_tile_clicked(self._tile_index)
            elif event == "close":
                self._show_tile_popover()

        elif self._focus_mode == "topbar":
            if event == "left":
                self._topbar_index = (self._topbar_index - 1) % len(self._topbar_buttons)
                self._update_focus()
                sound_player.play("cursor")
            elif event == "right":
                self._topbar_index = (self._topbar_index + 1) % len(self._topbar_buttons)
                self._update_focus()
                sound_player.play("cursor")
            elif event in ("down", "cancel"):
                self._focus_mode = "tiles"
                self._update_focus()
                sound_player.play("cursor")
            elif event == "select":
                self._topbar_buttons[self._topbar_index].click()

    # ── Tile actions ───────────────────────────────────────────────────────

    def _on_tile_clicked(self, idx: int) -> None:
        n_static = len(self._tiles)

        if idx < n_static:
            # Static tile (configured application).
            # Ignore clicks while the app is shutting down — proc.poll() still
            # reports it as running, so restore_app would hide Desktop and try
            # to activate a window that's about to disappear, leaving the
            # screen blank with an empty gamepad handler stack.
            if self._tiles[idx].is_closing():
                return
            self._active_context = {'type': 'app', 'id': idx, 'name': self._apps[idx]['name']}
            if self._app_manager.is_running(idx):
                logger.info("Restoring application %d", idx)
                self.restore_app(self._active_context)
            else:
                logger.info("Launching application %d", idx)
                sound_player.play("select")
                # Minimize other already-running apps to prevent virtual pad interference
                self._arrange_windows()
                trigger = self._apps[idx].get("recall_menu_trigger", BTN_MODE_CLICK)
                self._gamepad.set_app_btn_mode_trigger(trigger)
                self._gamepad.pop_handler(self._handle_pad)
                self._app_manager.launch(idx, self._apps[idx])

        else:
            # Dynamic tile (currently open window)
            dyn_idx = idx - n_static
            if dyn_idx < len(self._dynamic_tiles):
                win_id, _, _ = self._dynamic_tiles[dyn_idx]
                self._on_dynamic_tile_clicked(win_id)

    def _on_app_launch_failed(self, idx: int, error: str) -> None:
        logger.warning("Application %d failed to launch: %s", idx, error)
        self._gamepad.push_handler(self._handle_pad)
        InfoDialog(
            message=self.tr("Failed to launch application:\n{0}").format(error),
            on_confirmed=lambda: None,
            gamepad=self._gamepad,
            parent=self,
        )

    def _on_app_finished(self, idx: int) -> None:
        logger.info("Application %d finished – returning to desktop", idx)
        self._close_active_dialog()
        self._refresh_tile_status()
        self._wm.refresh_now()
        # Clear active context if it was this app
        if (self._active_context is not None
                and self._active_context.get('type') == 'app'
                and self._active_context.get('id') == idx):
            self._active_context = None
        if not self.isVisible():
            # App exited on its own (crash / self-close) — show desktop now
            self._gamepad.push_handler(self._handle_pad)
            self.showFullScreen()
            self.activateWindow()
        # Some apps (notably Steam) re-enumerate the gamepad on exit,
        # leaving our evdev fd pointing at a dead device with no error.
        # Delay long enough for the kernel to surface the replacement.
        QTimer.singleShot(1000, self._gamepad.refresh)

    # ── Closing an application ─────────────────────────────────────────────

    def _show_tile_popover(self) -> None:
        """Show a context popover above the focused tile."""
        idx = self._tile_index
        n_static = len(self._tiles)
        options: list[tuple[str, object]] = []

        if idx < n_static:
            if self._app_manager.is_running(idx):
                options.append((self.tr("Restore"), lambda: self._on_tile_clicked(idx)))
                options.append((self.tr("Close"),   self._close_focused_tile))
            else:
                options.append((self.tr("Launch"),  lambda: self._on_tile_clicked(idx)))
        else:
            dyn_idx = idx - n_static
            if dyn_idx >= len(self._dynamic_tiles):
                return
            win_id, _, _ = self._dynamic_tiles[dyn_idx]
            options.append((self.tr("Restore"), lambda: self._on_tile_clicked(idx)))
            options.append((self.tr("Close"),   self._close_focused_tile))

        all_tiles: list[AppTile] = self._tiles + [t for _, _, t in self._dynamic_tiles]
        popover = TilePopoverMenu(
            options=options,
            gamepad=self._gamepad,
            parent=self,
        )
        popover.show_above(all_tiles[idx])

    def _close_focused_tile(self) -> None:
        """Close the application represented by the currently focused tile."""
        idx = self._tile_index
        n_static = len(self._tiles)

        if idx < n_static:
            app = {
                'type': 'app',
                'id': idx,
                'name': self._apps[idx]['name']
            }
        else:
            dyn_idx = idx - n_static
            win_id, title, _ = self._dynamic_tiles[dyn_idx]

            app = {
                'type': 'dyn',
                'id': win_id,
                'name': title
            }

        self.request_close_app(app)

    def _restore_desktop_view(self) -> None:
        self._gamepad.push_handler(self._handle_pad)
        self.showFullScreen()
        self.activateWindow()
        # Wayland focus-stealing prevention can ignore Qt's activateWindow
        # when another app (still dying) holds focus. Force Desktop to the
        # top of the stack via KWin scripting.
        self._wm.raise_windows_for_pid_exact(os.getpid())

    def _arrange_windows(self, activate_pid: int | None = None) -> None:
        """Activate windows for activate_pid and minimize all other running apps."""
        all_pids = set(self._app_manager.all_running_pids())
        if activate_pid:
            self._wm.activate_windows_for_pids({activate_pid})
        other_pids = all_pids - ({activate_pid} if activate_pid else set())
        if other_pids:
            self._wm.minimize_windows_for_pids(other_pids)

    def _close_active_dialog(self) -> None:
        if self._confirm_dialog is not None:
            logger.warning("Dialog window still active after app ending – forcing to close")
            self._confirm_dialog.force_close()
            self._confirm_dialog = None

    # ── Confirmation dialogs ───────────────────────────────────────────────

    def _show_confirm(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None] | None = None,
    ) -> None:
        """Creates a ConfirmDialog and manages the lifecycle of self._confirm_dialog.

        If a dialog is already open — ignores the call. The on_confirmed
        and on_cancelled callbacks are automatically wrapped to clear
        self._confirm_dialog before passing control.
        """
        if self._confirm_dialog is not None:
            return

        def _wrap(cb: Callable[[], None] | None) -> Callable[[], None]:
            def _inner() -> None:
                self._confirm_dialog = None
                if cb:
                    cb()
            return _inner

        self._confirm_dialog = ConfirmDialog(
            question=question,
            on_confirmed=_wrap(on_confirmed),
            on_cancelled=_wrap(on_cancelled),
            gamepad=self._gamepad,
            parent=self,
        )

    # ── Top bar actions ────────────────────────────────────────────────────

    def _topbar_action(self, action_type: str) -> None:
        self._action_runner.run(action_type)

    def _open_volume_overlay(self) -> None:
        overlay = VolumeOverlay(self._gamepad, parent=self)
        self._volume_overlay = overlay
        overlay.closed.connect(self._on_volume_closed)

    def _on_volume_closed(self) -> None:
        self._volume_overlay = None
        self._focus_mode = "topbar"
        self._update_focus()
