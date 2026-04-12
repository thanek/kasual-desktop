import logging
import os
import subprocess
from collections.abc import Callable

import qtawesome as qta
from PyQt6.QtCore import Qt, QCoreApplication, QLocale, QTimer, QSize, QEvent
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QHBoxLayout, QVBoxLayout,
    QScrollArea, QLabel,
    QApplication,
)

from audio import sound_player
from input.gamepad_watcher import GamepadWatcher
from overlays.base_overlay import BaseOverlay
from overlays.confirm_dialog import ConfirmDialog
from overlays.info_dialog import InfoDialog
from overlays.volume_overlay import VolumeOverlay
from system.app_manager import AppManager
from system.system_actions import SYSTEM_ACTION_SPECS
from system.window_manager import KWinWindowManager
from ui import styles
from .app_tile import AppTile, TILE_H
from .wallpaper import load_kde_wallpaper
from .window_icons import resolve_window_name, resolve_window_icon

logger = logging.getLogger(__name__)


TOPBAR_ACTIONS = [
    {"icon": "fa5s.volume-up", "color": "#3b4252", "type": "volume"},
    {"icon": "fa5s.window-minimize", "color": "#d580ff", "type": "hide_desktop"},
    {"icon": "fa5s.moon", "color": "#4c566a", "type": "sleep"},
    {"icon": "fa5s.redo-alt", "color": "#5e81ac", "type": "restart"},
    {"icon": "fa5s.power-off", "color": "#bf616a", "type": "shutdown"},
]

_DYN_TILE_MAX_TITLE = 22   # Maximum length of a dynamic tile title


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

        # Dynamic tiles: list of (window_id, title, AppTile)
        self._dynamic_tiles:  list[tuple[str, str, AppTile]] = []
        self._dyn_separator:  QWidget | None                 = None
        # Currently active dynamic window (set after clicking a tile outside apps.yml)
        self._dyn_active:     tuple[str, str] | None         = None  # (win_id, title)

        self.setWindowTitle("Kasual")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(self._build_topbar())
        main.addStretch(1)
        main.addWidget(self._build_tile_bar())

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_tile_status)
        self._status_timer.start(500)

        self._wallpaper: 'QPixmap | None' = load_kde_wallpaper()

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
        self._dyn_active = None
        self._gamepad.push_handler(self._handle_pad)
        self._wm.refresh_now()
        self.showFullScreen()
        self._restore_overlays()
        self.activateWindow()

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

    @property
    def active_dynamic_window(self) -> tuple[str, str] | None:
        """Returns (win_id, title) of the active dynamic window, or None."""
        return self._dyn_active

    def restore_dynamic_window(self) -> None:
        """Return to the active dynamic window (activate it in KWin)."""
        if self._dyn_active:
            self._wm.activate_window(self._dyn_active[0])

    def request_close_dynamic_window(self) -> None:
        """Show the close dialog for the active dynamic window."""
        if self._dyn_active:
            win_id, title = self._dyn_active
            self._request_close_kwin_window(win_id, title)

    def restore_app(self) -> None:
        """Return to the running application — hide Desktop and release gamepad to the app."""
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()

    def request_close_running_app(self) -> None:
        """Show the confirmation dialog for closing the running application."""
        running = self._app_manager.running_idx()
        if running is None:
            return
        name = self._apps[running]["name"]
        self._show_confirm(
            question=self.tr('Are you sure you want to close\n"{0}"?').format(name),
            on_confirmed=self._app_manager.terminate,
        )

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
        BTNS_TOTAL  = len(TOPBAR_ACTIONS) * BTN_SIZE + (len(TOPBAR_ACTIONS) - 1) * BTN_SPACING

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
        for i, action in enumerate(TOPBAR_ACTIONS):
            btn = QPushButton()
            btn.setFixedSize(BTN_SIZE, BTN_SIZE)
            btn.setIcon(qta.icon(action["icon"], color="white"))
            btn.setIconSize(QSize(24, 24))
            btn.setStyleSheet(styles.topbar_normal(action["color"]))
            btn.clicked.connect(lambda _, idx=i: self._topbar_action(idx))
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
        scroll.setFixedHeight(TILE_H + 40)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._tile_layout = QHBoxLayout(container)
        self._tile_layout.setContentsMargins(40, 20, 40, 20)
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

        self._tile_layout.addStretch()
        scroll.setWidget(container)
        self._scroll = scroll

        self._update_focus()
        return scroll

    # ── Dynamic tiles (currently open windows) ─────────────────────────────

    def _rebuild_dynamic_tiles(self, windows: list[dict]) -> None:
        """Rebuilds the dynamic tile section based on the list from KWin.

        Filters out windows belonging to the application launched by AppManager —
        they are already represented by a static tile.
        """
        # Remove old dynamic tiles and separator
        for _, _, tile in self._dynamic_tiles:
            self._tile_layout.removeWidget(tile)
            tile.deleteLater()
        self._dynamic_tiles.clear()

        if self._dyn_separator is not None:
            self._tile_layout.removeWidget(self._dyn_separator)
            self._dyn_separator.deleteLater()
            self._dyn_separator = None

        # Exclude windows belonging to the process group of the running application.
        # start_new_session=True → child's pgid == its pid, so all
        # child processes (e.g. browser launched by a script) share
        # the same pgid and are also filtered out.
        running_pid = self._app_manager.running_pid()

        def _in_running_group(pid: int) -> bool:
            if running_pid is None or pid == 0:
                return False
            try:
                return os.getpgid(pid) == running_pid
            except OSError:
                return False

        extern_windows = [w for w in windows if not _in_running_group(w.get('pid', 0))]

        if not extern_windows:
            self._clamp_tile_index()
            self._update_focus()
            return

        # Visual separator between static and dynamic tiles
        sep = QWidget()
        sep.setFixedSize(2, TILE_H - 24)
        sep.setStyleSheet("background: #3b4252;")
        insert_pos = self._tile_layout.count() - 1
        self._tile_layout.insertWidget(insert_pos, sep)
        self._dyn_separator = sep

        for w in extern_windows:
            full_title = w['title']
            app_name   = resolve_window_name(
                w.get('desktopFile', ''), w.get('resourceClass', '')
            )
            if app_name and app_name != full_title:
                combined = f"{app_name} ({full_title})"
            else:
                combined = app_name or full_title
            display_title = (combined[:_DYN_TILE_MAX_TITLE - 1] + '…'
                             if len(combined) > _DYN_TILE_MAX_TITLE else combined)
            app_icon = resolve_window_icon(
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
            self._tile_layout.insertWidget(self._tile_layout.count() - 1, tile)
            self._dynamic_tiles.append((win_id, full_title, tile))

        self._clamp_tile_index()
        self._update_focus()
        logger.debug('Dynamic tiles: %d', len(self._dynamic_tiles))

        # If the active dynamic window disappeared (closed by the application itself) → Desktop
        if self._dyn_active is not None:
            active_ids = {wid for wid, _, _ in self._dynamic_tiles}
            if self._dyn_active[0] not in active_ids:
                self._dyn_active = None
                if not self.isVisible():
                    self._gamepad.push_handler(self._handle_pad)
                    self.showFullScreen()
                    self.activateWindow()

    def _on_dynamic_tile_clicked(self, window_id: str) -> None:
        title = next((t for wid, t, _ in self._dynamic_tiles if wid == window_id), window_id)
        self._dyn_active = (window_id, title)
        self._wm.activate_window(window_id)
        sound_player.play("select")
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()

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
                btn.setStyleSheet(styles.topbar_normal(TOPBAR_ACTIONS[i]["color"]))

        if in_tiles:
            all_tiles: list[AppTile] = self._tiles + [t for _, _, t in self._dynamic_tiles]
            if 0 <= self._tile_index < len(all_tiles):
                self._scroll.ensureWidgetVisible(all_tiles[self._tile_index])

    def _refresh_tile_status(self) -> None:
        running = self._app_manager.running_idx()
        for i, tile in enumerate(self._tiles):
            tile.set_running(i == running)

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
                self._close_focused_tile()

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
                self._topbar_action(self._topbar_index)

    # ── Tile actions ───────────────────────────────────────────────────────

    def _on_tile_clicked(self, idx: int) -> None:
        n_static = len(self._tiles)

        if idx < n_static:
            # Static tile (configured application)
            running = self._app_manager.running_idx()
            if running == idx:
                logger.info("Restoring application %d", idx)
                sound_player.play("select")
                self.restore_app()
            elif running is not None:
                logger.info("Another application (%d) is already running – ignoring", running)
            else:
                logger.info("Launching application %d", idx)
                sound_player.play("select")
                self._gamepad.pop_handler(self._handle_pad)
                self._app_manager.launch(idx, self._apps[idx])
                # self.hide()

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
        )

    def _on_app_finished(self, idx: int) -> None:
        logger.info("Application %d finished – returning to desktop", idx)
        if self._confirm_dialog is not None:
            logger.warning("Dialog window still active after app ending – forcing to close")
            self._confirm_dialog.force_close()
            self._confirm_dialog = None
        self._refresh_tile_status()
        self._wm.refresh_now()
        self._gamepad.push_handler(self._handle_pad)
        self.showFullScreen()
        self.activateWindow()

    # ── Closing an application ─────────────────────────────────────────────

    def _close_focused_tile(self) -> None:
        """Close the application represented by the currently focused tile."""
        idx = self._tile_index
        n_static = len(self._tiles)

        if idx < n_static:
            # Static tile: close only if this particular application is running
            if self._app_manager.running_idx() == idx:
                self.request_close_running_app()
        else:
            # Dynamic tile (KDE window)
            dyn_idx = idx - n_static
            if dyn_idx < len(self._dynamic_tiles):
                win_id, title, _ = self._dynamic_tiles[dyn_idx]
                self._request_close_kwin_window(win_id, title)

    def _request_close_kwin_window(self, win_id: str, title: str) -> None:
        display = title if len(title) <= 40 else title[:39] + '…'
        self._show_confirm(
            question=self.tr('Are you sure you want to close\n"{0}"?').format(display),
            on_confirmed=lambda: self._do_close_kwin_window(win_id),
            on_cancelled=self._restore_desktop_view,
        )

    def _do_close_kwin_window(self, win_id: str) -> None:
        self._dyn_active = None
        self._wm.close_window(win_id)
        QTimer.singleShot(1000, self._wm.refresh_now)
        self._restore_desktop_view()

    def _restore_desktop_view(self) -> None:
        self._gamepad.push_handler(self._handle_pad)
        self.showFullScreen()
        self.activateWindow()

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
        )

    # ── Top bar actions ────────────────────────────────────────────────────

    def _topbar_action(self, idx: int) -> None:
        action_type = TOPBAR_ACTIONS[idx]["type"]
        if action_type == "volume":
            overlay = VolumeOverlay(self._gamepad)
            self._volume_overlay = overlay
            overlay.closed.connect(self._on_volume_closed)
            return
        if action_type not in SYSTEM_ACTION_SPECS:
            return
        question_src, cmd = SYSTEM_ACTION_SPECS[action_type]
        question = QCoreApplication.translate("Kasual", question_src)
        on_confirmed = (
            (lambda: self.hide()) if cmd is None
            else (lambda c=cmd: subprocess.Popen(c))
        )
        self._show_confirm(question=question, on_confirmed=on_confirmed)

    def _on_volume_closed(self) -> None:
        self._volume_overlay = None
        self._focus_mode = "topbar"
        self._update_focus()
