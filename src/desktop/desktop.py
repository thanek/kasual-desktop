import logging
import os
import subprocess
from collections.abc import Callable

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QHBoxLayout, QVBoxLayout,
    QScrollArea, QLabel,
    QApplication,
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QKeyEvent

import qtawesome as qta

from input.gamepad_watcher import GamepadWatcher
from system.app_manager import AppManager
from overlays.base_overlay import BaseOverlay
from overlays.confirm_dialog import ConfirmDialog
from overlays.volume_overlay import VolumeOverlay
from system.window_manager import KWinWindowManager
from ui import styles
from system.system_actions import SYSTEM_ACTION_SPECS
from .wallpaper import load_kde_wallpaper
from .window_icons import resolve_window_name, resolve_window_icon
from .app_tile import AppTile, TILE_W, TILE_H
from audio import sound_player

logger = logging.getLogger(__name__)


DAYS_PL = [
    "Poniedziałek", "Wtorek", "Środa", "Czwartek",
    "Piątek", "Sobota", "Niedziela",
]
MONTHS_PL = [
    "sty", "lut", "mar", "kwi", "maj", "cze",
    "lip", "sie", "wrz", "paź", "lis", "gru",
]

TOPBAR_ACTIONS = [
    {"icon": "fa5s.volume-up", "color": "#3b4252", "type": "volume"},
    {"icon": "fa5s.window-minimize", "color": "#d580ff", "type": "hide_desktop"},
    {"icon": "fa5s.moon", "color": "#4c566a", "type": "sleep"},
    {"icon": "fa5s.redo-alt", "color": "#5e81ac", "type": "restart"},
    {"icon": "fa5s.power-off", "color": "#bf616a", "type": "shutdown"},
]

_DYN_TILE_MAX_TITLE = 22   # Maksymalna długość tytułu dynamicznego kafla


class Desktop(QWidget):
    """Główne okno środowiska – zawsze pełnoekranowe."""

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

        # Dynamiczne kafle: lista (window_id, title, AppTile)
        self._dynamic_tiles:  list[tuple[str, str, AppTile]] = []
        self._dyn_separator:  QWidget | None                 = None
        # Aktualnie aktywne okno dynamiczne (ustawione po kliknięciu kafla spoza apps.yml)
        self._dyn_active:     tuple[str, str] | None         = None  # (win_id, title)

        self.setWindowTitle("Console Desktop")
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
        self._wm.windows_updated.connect(self._rebuild_dynamic_tiles)

        QApplication.instance().installEventFilter(self)

        # Nie pokazujemy Desktop przy starcie — czekamy na sygnał connected_changed(True)

    # ── Publiczne API ──────────────────────────────────────────────────────

    @property
    def app_manager(self) -> AppManager:
        return self._app_manager

    def show_desktop(self) -> None:
        """Pokaż pulpit nie przerywając działającej aplikacji."""
        self._dyn_active = None
        self._gamepad.push_handler(self._handle_pad)
        self._wm.refresh_now()
        self.showFullScreen()
        self._restore_overlays()
        self.activateWindow()

    @property
    def _active_overlays(self) -> list[BaseOverlay]:
        """Aktywne overlaye (te które mogą być pauzowane/wznawiane)."""
        return [o for o in (self._volume_overlay, self._confirm_dialog) if o is not None]

    def pause(self) -> None:
        """Ukryj Desktop bez odłączania pada (minimalizacja do tray)."""
        sound_player.play("exit")
        self._is_paused = True
        for overlay in self._active_overlays:
            overlay.pause()
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()

    def resume(self) -> None:
        """Przywróć Desktop po ponownym podłączeniu pada — bez resetowania stanu."""
        self._gamepad.push_handler(self._handle_pad)
        sound_player.play("start")
        self.showFullScreen()
        self._restore_overlays()
        self.activateWindow()

    def _restore_overlays(self) -> None:
        """Przywróć overlaye ukryte przez pause(). Noop jeśli nie byliśmy spauzowani."""
        if not self._is_paused:
            return
        self._is_paused = False
        for overlay in self._active_overlays:
            overlay.resume()

    @property
    def active_dynamic_window(self) -> tuple[str, str] | None:
        """Zwraca (win_id, title) aktywnego okna dynamicznego lub None."""
        return self._dyn_active

    def restore_dynamic_window(self) -> None:
        """Wróć do aktywnego okna dynamicznego (aktywuj je w KWin)."""
        if self._dyn_active:
            self._wm.activate_window(self._dyn_active[0])

    def request_close_dynamic_window(self) -> None:
        """Pokaż dialog zamknięcia aktywnego okna dynamicznego."""
        if self._dyn_active:
            win_id, title = self._dyn_active
            self._request_close_kwin_window(win_id, title)

    def restore_app(self) -> None:
        """Wróć do działającej aplikacji – ukryj Desktop, oddaj pada aplikacji."""
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()

    def request_close_running_app(self) -> None:
        """Pokaż dialog potwierdzenia zamknięcia działającej aplikacji."""
        running = self._app_manager.running_idx()
        if running is None:
            return
        name = self._apps[running]["name"]
        self._show_confirm(
            question=f'Czy na pewno chcesz zamknąć aplikację\n"{name}"?',
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
        now = datetime.now()
        self._date_lbl.setText(
            f"{DAYS_PL[now.weekday()]}  {now.day:02d} {MONTHS_PL[now.month - 1]}. {now.year}"
        )
        self._lbl_h.setText(now.strftime("%H"))
        self._lbl_m.setText(now.strftime("%M"))
        self._lbl_s.setText(now.strftime("%S"))

    # ── Obszar kafli ───────────────────────────────────────────────────────

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

    # ── Dynamiczne kafle (aktualnie otwarte okna) ──────────────────────────

    def _rebuild_dynamic_tiles(self, windows: list[dict]) -> None:
        """Przebudowuje sekcję dynamicznych kafli na podstawie listy z KWin.

        Filtruje okna należące do aplikacji uruchomionej przez AppManager —
        są już reprezentowane przez kafel statyczny.
        """
        # Usuń stare dynamiczne kafle i separator
        for _, _, tile in self._dynamic_tiles:
            self._tile_layout.removeWidget(tile)
            tile.deleteLater()
        self._dynamic_tiles.clear()

        if self._dyn_separator is not None:
            self._tile_layout.removeWidget(self._dyn_separator)
            self._dyn_separator.deleteLater()
            self._dyn_separator = None

        # Wyklucz okna należące do grupy procesów uruchomionej aplikacji.
        # start_new_session=True → pgid dziecka == jego pid, więc wszystkie
        # procesy potomne (np. przeglądarka uruchomiona przez skrypt) mają
        # ten sam pgid i też są filtrowane.
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

        # Separator wizualny między kaflamai statycznymi a dynamicznymi
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
            tile.set_running(True)   # okno istnieje → aplikacja działa
            win_id = w['id']
            tile.clicked.connect(lambda wid=win_id: self._on_dynamic_tile_clicked(wid))
            self._tile_layout.insertWidget(self._tile_layout.count() - 1, tile)
            self._dynamic_tiles.append((win_id, full_title, tile))

        self._clamp_tile_index()
        self._update_focus()
        logger.debug('Dynamiczne kafle: %d', len(self._dynamic_tiles))

        # Jeśli aktywne okno dynamiczne znikło (zamknięte przez samą aplikację) → Pulpit
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

    # ── Fokus i styl ───────────────────────────────────────────────────────

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

    # ── Handler pada ───────────────────────────────────────────────────────

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

    # ── Akcje kafli ────────────────────────────────────────────────────────

    def _on_tile_clicked(self, idx: int) -> None:
        n_static = len(self._tiles)

        if idx < n_static:
            # Kafel statyczny (skonfigurowana aplikacja)
            running = self._app_manager.running_idx()
            if running == idx:
                logger.info("Przywracam aplikację %d", idx)
                sound_player.play("select")
                self.restore_app()
            elif running is not None:
                logger.info("Inna aplikacja (%d) już działa – ignoruję", running)
            else:
                logger.info("Uruchamiam aplikację %d", idx)
                sound_player.play("select")
                self._gamepad.pop_handler(self._handle_pad)
                self._app_manager.launch(idx, self._apps[idx])
                # self.hide()

        else:
            # Kafel dynamiczny (aktualnie otwarte okno)
            dyn_idx = idx - n_static
            if dyn_idx < len(self._dynamic_tiles):
                win_id, _, _ = self._dynamic_tiles[dyn_idx]
                self._on_dynamic_tile_clicked(win_id)

    def _on_app_finished(self, idx: int) -> None:
        logger.info("Aplikacja %d zakończona – wracam do pulpitu", idx)
        if self._confirm_dialog is not None:
            logger.warning("Dialog nadal aktywny po zakończeniu aplikacji – wymuszam zamknięcie")
            self._confirm_dialog.force_close()
            self._confirm_dialog = None
        self._refresh_tile_status()
        self._wm.refresh_now()
        self._gamepad.push_handler(self._handle_pad)
        self.showFullScreen()
        self.activateWindow()

    # ── Zamknięcie aplikacji ───────────────────────────────────────────────

    def _close_focused_tile(self) -> None:
        """Zamknij aplikację reprezentowaną przez aktualnie fokusowany kafel."""
        idx = self._tile_index
        n_static = len(self._tiles)

        if idx < n_static:
            # Kafel statyczny: zamknij tylko gdy to właśnie ta aplikacja działa
            if self._app_manager.running_idx() == idx:
                self.request_close_running_app()
        else:
            # Kafel dynamiczny (okno KDE)
            dyn_idx = idx - n_static
            if dyn_idx < len(self._dynamic_tiles):
                win_id, title, _ = self._dynamic_tiles[dyn_idx]
                self._request_close_kwin_window(win_id, title)

    def _request_close_kwin_window(self, win_id: str, title: str) -> None:
        display = title if len(title) <= 40 else title[:39] + '…'
        self._show_confirm(
            question=f'Czy na pewno chcesz zamknąć\n"{display}"?',
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

    # ── Dialogi potwierdzenia ──────────────────────────────────────────────

    def _show_confirm(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None] | None = None,
    ) -> None:
        """Tworzy ConfirmDialog i zarządza cyklem życia self._confirm_dialog.

        Jeśli dialog jest już otwarty — ignoruje wywołanie. Callbacki
        on_confirmed i on_cancelled są automatycznie opakowywane tak, by
        wyczyścić self._confirm_dialog przed przekazaniem sterowania.
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

    # ── Akcje paska górnego ────────────────────────────────────────────────

    def _topbar_action(self, idx: int) -> None:
        action_type = TOPBAR_ACTIONS[idx]["type"]
        if action_type == "volume":
            overlay = VolumeOverlay(self._gamepad)
            self._volume_overlay = overlay
            overlay.closed.connect(self._on_volume_closed)
            return
        if action_type not in SYSTEM_ACTION_SPECS:
            return
        question, cmd = SYSTEM_ACTION_SPECS[action_type]
        on_confirmed = (
            (lambda: self.hide()) if cmd is None
            else (lambda c=cmd: subprocess.Popen(c))
        )
        self._show_confirm(question=question, on_confirmed=on_confirmed)

    def _on_volume_closed(self) -> None:
        self._volume_overlay = None
        self._focus_mode = "topbar"
        self._update_focus()
