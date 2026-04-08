import logging
import math
import subprocess

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QHBoxLayout, QVBoxLayout,
    QScrollArea, QLabel, QGraphicsDropShadowEffect, QToolButton,
    QApplication, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent, pyqtSignal
from PyQt6.QtGui import QPainter, QRadialGradient, QColor, QIcon, QKeyEvent

import qtawesome as qta

from gamepad_watcher import GamepadWatcher
from app_manager import AppManager
from confirm_dialog import ConfirmDialog
from volume_overlay import VolumeOverlay
from styles import Styles

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
    {"icon": "fa5s.volume-up",  "color": "#3b4252", "type": "volume"},
    {"icon": "fa5s.moon",       "color": "#4c566a", "type": "sleep"},
    {"icon": "fa5s.redo-alt",   "color": "#5e81ac", "type": "restart"},
    {"icon": "fa5s.power-off",  "color": "#bf616a", "type": "shutdown"},
]

TILE_W = 180
TILE_H = 200


class AppTile(QWidget):
    """Kafel pojedynczej aplikacji."""

    clicked = pyqtSignal()

    def __init__(self, name: str, icon_name: str, color: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(TILE_W, TILE_H)
        self._color = color

        self._btn = QToolButton(self)
        self._btn.setFixedSize(TILE_W, TILE_H)
        self._btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._btn.setIconSize(QSize(72, 72))
        try:
            self._btn.setIcon(qta.icon(icon_name, color="white"))
        except Exception:
            self._btn.setIcon(qta.icon("fa5s.desktop", color="white"))
        self._btn.setText(name)
        self._btn.setStyleSheet(Styles.tile_normal(color))
        self._btn.clicked.connect(self.clicked)

        self._dot = QLabel(self)
        self._dot.setFixedSize(14, 14)
        self._dot.setStyleSheet(
            "background-color: #a3be8c; border-radius: 7px; border: 2px solid #0b140e;"
        )
        self._dot.move(TILE_W - 22, 8)
        self._dot.hide()

        shadow = QGraphicsDropShadowEffect(self._btn)
        shadow.setOffset(4, 6)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setBlurRadius(18)
        self._btn.setGraphicsEffect(shadow)

    def set_selected(self, selected: bool) -> None:
        if selected:
            self._btn.setStyleSheet(Styles.tile_selected())
            effect = QGraphicsDropShadowEffect(self._btn)
            effect.setOffset(0, 0)
            effect.setColor(QColor("#88c0d0"))
            effect.setBlurRadius(36)
            self._btn.setGraphicsEffect(effect)
        else:
            self._btn.setStyleSheet(Styles.tile_normal(self._color))
            shadow = QGraphicsDropShadowEffect(self._btn)
            shadow.setOffset(4, 6)
            shadow.setColor(QColor(0, 0, 0, 160))
            shadow.setBlurRadius(18)
            self._btn.setGraphicsEffect(shadow)

    def set_running(self, running: bool) -> None:
        self._dot.setVisible(running)


class Desktop(QWidget):
    """Główne okno środowiska – zawsze pełnoekranowe."""

    def __init__(self, apps: list[dict], gamepad: GamepadWatcher):
        super().__init__()
        self._apps        = apps
        self._gamepad     = gamepad
        self._app_manager = AppManager(self)
        self._focus_mode     = "tiles"   # "tiles" | "topbar"
        self._tile_index     = 0
        self._topbar_index   = 0
        self._confirm_dialog = None

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

        self._bg_offset = 0.0
        self._bg_timer = QTimer(self)
        self._bg_timer.timeout.connect(self._tick_bg)
        self._bg_timer.start(33)

        self._app_manager.app_finished.connect(self._on_app_finished)

        QApplication.instance().installEventFilter(self)

        self._gamepad.push_handler(self._handle_pad)
        self.showFullScreen()

    # ── Publiczne API (dla main.py / HomeOverlay) ──────────────────────────

    @property
    def app_manager(self) -> AppManager:
        return self._app_manager

    def restore_app(self) -> None:
        """Wróć do działającej aplikacji – ukryj Desktop, oddaj pada aplikacji."""
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()

    def request_close_running_app(self) -> None:
        """Pokaż dialog potwierdzenia zamknięcia działającej aplikacji."""
        if self._confirm_dialog is not None:
            return  # dialog już otwarty
        running = self._app_manager.running_idx()
        if running is None:
            return
        name = self._apps[running]["name"]
        self._confirm_dialog = ConfirmDialog(
            question=f'Czy na pewno chcesz zamknąć aplikację\n"{name}"?',
            on_confirmed=self._do_close_app,
            on_cancelled=self._on_close_cancelled,
            gamepad=self._gamepad,
        )

    # ── Animacja tła ───────────────────────────────────────────────────────

    def _tick_bg(self) -> None:
        self._bg_offset += 0.0007
        self.update()

    def paintEvent(self, _) -> None:
        painter = QPainter(self)
        w, h = self.width(), self.height()
        t = self._bg_offset

        painter.fillRect(self.rect(), QColor("#0b140e"))

        cx1 = w * (0.25 + 0.18 * math.sin(t * 0.7))
        cy1 = h * (0.45 + 0.12 * math.cos(t * 0.5))
        g1 = QRadialGradient(cx1, cy1, w * 0.55)
        c1 = QColor("#0d5f70"); c1.setAlpha(100)
        g1.setColorAt(0.0, c1); g1.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), g1)

        cx2 = w * (0.75 + 0.15 * math.cos(t * 0.4))
        cy2 = h * (0.5  + 0.18 * math.sin(t * 0.6))
        g2 = QRadialGradient(cx2, cy2, w * 0.45)
        c2 = QColor("#40106a"); c2.setAlpha(85)
        g2.setColorAt(0.0, c2); g2.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), g2)

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
            btn.setStyleSheet(Styles.topbar_normal(action["color"]))
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

    # ── Fokus i styl ───────────────────────────────────────────────────────

    def _update_focus(self) -> None:
        for i, tile in enumerate(self._tiles):
            tile.set_selected(
                i == self._tile_index and self._focus_mode == "tiles"
            )
        for i, btn in enumerate(self._topbar_buttons):
            if self._focus_mode == "topbar" and i == self._topbar_index:
                btn.setStyleSheet(Styles.topbar_selected())
            else:
                btn.setStyleSheet(Styles.topbar_normal(TOPBAR_ACTIONS[i]["color"]))

        if self._tiles and self._focus_mode == "tiles":
            self._scroll.ensureWidgetVisible(self._tiles[self._tile_index])

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
            if event == "left" and self._tile_index > 0:
                self._tile_index -= 1
                self._update_focus()
            elif event == "right" and self._tile_index < len(self._tiles) - 1:
                self._tile_index += 1
                self._update_focus()
            elif event == "up" and self._topbar_buttons:
                self._focus_mode = "topbar"
                self._topbar_index = 0
                self._update_focus()
            elif event == "select":
                self._on_tile_clicked(self._tile_index)
            elif event == "close":
                if self._app_manager.is_running():
                    self.request_close_running_app()

        elif self._focus_mode == "topbar":
            if event == "left":
                self._topbar_index = (self._topbar_index - 1) % len(self._topbar_buttons)
                self._update_focus()
            elif event == "right":
                self._topbar_index = (self._topbar_index + 1) % len(self._topbar_buttons)
                self._update_focus()
            elif event in ("down", "cancel"):
                self._focus_mode = "tiles"
                self._update_focus()
            elif event == "select":
                self._topbar_action(self._topbar_index)

    # ── Akcje kafli ────────────────────────────────────────────────────────

    def _on_tile_clicked(self, idx: int) -> None:
        running = self._app_manager.running_idx()
        if running == idx:
            logger.info("Przywracam aplikację %d", idx)
            self.restore_app()
        elif running is not None:
            logger.info("Inna aplikacja (%d) już działa – ignoruję", running)
        else:
            logger.info("Uruchamiam aplikację %d", idx)
            self._gamepad.pop_handler(self._handle_pad)
            self._app_manager.launch(idx, self._apps[idx])
            self.hide()

    def _on_app_finished(self, idx: int) -> None:
        logger.info("Aplikacja %d zakończona – wracam do pulpitu", idx)
        if self._confirm_dialog is not None:
            logger.warning("Dialog nadal aktywny po zakończeniu aplikacji – wymuszam zamknięcie")
            self._confirm_dialog.force_close()
            self._confirm_dialog = None
        self._refresh_tile_status()
        self._gamepad.push_handler(self._handle_pad)
        self.showFullScreen()
        self.activateWindow()

    # ── Zamknięcie aplikacji ───────────────────────────────────────────────

    def _on_close_cancelled(self) -> None:
        self._confirm_dialog = None

    def _do_close_app(self) -> None:
        self._confirm_dialog = None
        self._app_manager.terminate()

    # ── Akcje paska górnego ────────────────────────────────────────────────

    def _topbar_action(self, idx: int) -> None:
        action_type = TOPBAR_ACTIONS[idx]["type"]
        if action_type == "volume":
            # VolumeOverlay pcha swój handler na stos – Desktop zostaje pod spodem
            overlay = VolumeOverlay(self._gamepad)
            overlay.closed.connect(self._on_volume_closed)
        elif action_type == "sleep":
            subprocess.Popen(["systemctl", "suspend"])
        elif action_type == "restart":
            subprocess.Popen(["systemctl", "reboot"])
        elif action_type == "shutdown":
            subprocess.Popen(["systemctl", "poweroff"])

    def _on_volume_closed(self) -> None:
        self._focus_mode = "topbar"
        self._update_focus()
