import configparser
import logging
import os
import subprocess
from functools import lru_cache
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QHBoxLayout, QVBoxLayout,
    QScrollArea, QLabel, QGraphicsDropShadowEffect, QToolButton,
    QApplication, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QIcon, QKeyEvent

import qtawesome as qta

from gamepad_watcher import GamepadWatcher
from app_manager import AppManager
from confirm_dialog import ConfirmDialog
from volume_overlay import VolumeOverlay
from window_manager import KWinWindowManager
from styles import Styles

logger = logging.getLogger(__name__)


def _wallpaper_package_image(directory: str) -> str | None:
    """
    Szuka najlepszego obrazu w paczce tapety KDE (katalog contents/images/).
    Zwraca ścieżkę do pliku o największej rozdzielczości lub None.
    """
    images_dir = os.path.join(directory, 'contents', 'images')
    if not os.path.isdir(images_dir):
        return None

    best: tuple[int, str] = (0, '')
    for fname in os.listdir(images_dir):
        fpath = os.path.join(images_dir, fname)
        if not os.path.isfile(fpath):
            continue
        # Nazwy plików mają format WxH.ext — parsuj rozdzielczość
        name = os.path.splitext(fname)[0]
        if 'x' in name:
            try:
                w, h = name.split('x', 1)
                pixels = int(w) * int(h)
                if pixels > best[0]:
                    best = (pixels, fpath)
            except ValueError:
                pass
        elif best[0] == 0:
            best = (1, fpath)   # fallback: jakikolwiek plik

    return best[1] or None


def _load_kde_wallpaper() -> 'QPixmap | None':
    """
    Czyta ścieżkę tapety z plasma-org.kde.plasma.desktop-appletsrc
    i zwraca QPixmap lub None gdy nie udało się znaleźć pliku.

    Obsługuje zarówno bezpośrednie ścieżki do pliku jak i paczki tapety
    KDE (katalog z contents/images/WxH.ext).
    """
    from PyQt6.QtGui import QPixmap

    cfg_path = Path.home() / '.config' / 'plasma-org.kde.plasma.desktop-appletsrc'
    if not cfg_path.exists():
        logger.warning('Nie znaleziono pliku konfiguracji Plasma: %s', cfg_path)
        return None

    cp = configparser.RawConfigParser()
    cp.read(str(cfg_path), encoding='utf-8')

    for section in cp.sections():
        if '][Wallpaper][' not in section:
            continue
        raw = cp.get(section, 'Image', fallback=None)
        if not raw:
            continue

        # Usuń opcjonalne cudzysłowy i prefiks file://
        raw = raw.strip("'\"")
        path = raw[7:] if raw.startswith('file://') else raw

        # Paczka tapety (katalog) → znajdź najlepszy obraz w contents/images/
        if os.path.isdir(path):
            resolved = _wallpaper_package_image(path)
            if resolved:
                path = resolved
            else:
                logger.debug('Brak obrazów w paczce: %s', path)
                continue

        if not os.path.isfile(path):
            logger.debug('Pomijam (nie plik): %s', path)
            continue

        px = QPixmap(path)
        if px.isNull():
            logger.debug('Nie udało się wczytać: %s', path)
            continue

        logger.info('Tapeta KDE: %s', path)
        return px

    logger.warning('Nie znaleziono żadnej tapety w konfiguracji Plasma')
    return None


# ── Rozwiązywanie ikon aplikacji ───────────────────────────────────────────────

def _xdg_app_dirs() -> list[str]:
    home   = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
    system = os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':')
    extra  = [
        '/var/lib/flatpak/exports/share',
        os.path.expanduser('~/.local/share/flatpak/exports/share'),
    ]
    return [os.path.join(d, 'applications') for d in [home] + system + extra]


def _icon_name_from_desktop(path: str) -> str | None:
    try:
        cp = configparser.RawConfigParser()
        cp.read(path, encoding='utf-8')
        return cp.get('Desktop Entry', 'Icon', fallback=None)
    except Exception:
        return None


@lru_cache(maxsize=128)
def _resolve_window_name(desktop_file: str, resource_class: str) -> str | None:
    """Zwraca oficjalną nazwę aplikacji (Name=) z pliku .desktop lub None."""
    candidates: list[str] = []
    if desktop_file:
        candidates.append(desktop_file if desktop_file.endswith('.desktop')
                          else desktop_file + '.desktop')
    if resource_class and resource_class != desktop_file:
        candidates.append(resource_class + '.desktop')

    for apps_dir in _xdg_app_dirs():
        for name in candidates:
            path = os.path.join(apps_dir, name)
            if os.path.isfile(path):
                try:
                    cp = configparser.RawConfigParser()
                    cp.read(path, encoding='utf-8')
                    result = cp.get('Desktop Entry', 'Name', fallback=None)
                    if result:
                        return result
                except Exception:
                    pass
    return None


@lru_cache(maxsize=128)
def _resolve_window_icon(desktop_file: str, resource_class: str):
    """Zwraca QIcon dla okna KWin lub None. Wynik jest cache'owany."""
    from PyQt6.QtGui import QIcon

    # Kandydaci na nazwy pliku .desktop (bez rozszerzenia → dodajemy)
    candidates: list[str] = []
    if desktop_file:
        candidates.append(desktop_file if desktop_file.endswith('.desktop')
                          else desktop_file + '.desktop')
    if resource_class and resource_class != desktop_file:
        candidates.append(resource_class + '.desktop')

    icon_name: str | None = None
    for apps_dir in _xdg_app_dirs():
        for name in candidates:
            path = os.path.join(apps_dir, name)
            if os.path.isfile(path):
                icon_name = _icon_name_from_desktop(path)
                if icon_name:
                    break
        if icon_name:
            break

    # Fallback: spróbuj klasy zasobu jako nazwy ikony motywu
    if not icon_name:
        icon_name = resource_class or desktop_file

    if not icon_name:
        return None

    # Absolutna ścieżka do pliku?
    if os.path.isabs(icon_name):
        icon = QIcon(icon_name)
        return icon if not icon.isNull() else None

    icon = QIcon.fromTheme(icon_name)
    return icon if not icon.isNull() else None


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

_DYN_TILE_MAX_TITLE = 22   # Maksymalna długość tytułu dynamicznego kafla


class AppTile(QWidget):
    """Kafel pojedynczej aplikacji."""

    clicked = pyqtSignal()

    def __init__(self, name: str, icon_name: str, color: str, qicon=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(TILE_W, TILE_H)
        self._color = color

        self._btn = QToolButton(self)
        self._btn.setFixedSize(TILE_W, TILE_H)
        self._btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._btn.setIconSize(QSize(72, 72))
        if qicon is not None and not qicon.isNull():
            self._btn.setIcon(qicon)
        else:
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

        self._wallpaper: 'QPixmap | None' = _load_kde_wallpaper()

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
        self.activateWindow()

    def pause(self) -> None:
        """Ukryj Desktop bez odłączania pada (minimalizacja do tray)."""
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()

    def resume(self) -> None:
        """Przywróć Desktop po ponownym podłączeniu pada — bez resetowania stanu."""
        self._gamepad.push_handler(self._handle_pad)
        self.showFullScreen()
        self.activateWindow()

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
        if self._confirm_dialog is not None:
            return
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
            app_name   = _resolve_window_name(
                w.get('desktopFile', ''), w.get('resourceClass', '')
            )
            if app_name and app_name != full_title:
                combined = f"{app_name} ({full_title})"
            else:
                combined = app_name or full_title
            display_title = (combined[:_DYN_TILE_MAX_TITLE - 1] + '…'
                             if len(combined) > _DYN_TILE_MAX_TITLE else combined)
            app_icon = _resolve_window_icon(
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
                btn.setStyleSheet(Styles.topbar_selected())
            else:
                btn.setStyleSheet(Styles.topbar_normal(TOPBAR_ACTIONS[i]["color"]))

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
            elif event == "right" and self._tile_index < max_idx:
                self._tile_index += 1
                self._update_focus()
            elif event == "up" and self._topbar_buttons:
                self._focus_mode = "topbar"
                self._topbar_index = 0
                self._update_focus()
            elif event == "select":
                self._on_tile_clicked(self._tile_index)
            elif event == "close":
                self._close_focused_tile()

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
        n_static = len(self._tiles)

        if idx < n_static:
            # Kafel statyczny (skonfigurowana aplikacja)
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
        if self._confirm_dialog is not None:
            return
        display = title if len(title) <= 40 else title[:39] + '…'
        self._confirm_dialog = ConfirmDialog(
            question=f'Czy na pewno chcesz zamknąć\n"{display}"?',
            on_confirmed=lambda: self._do_close_kwin_window(win_id),
            on_cancelled=self._on_kwin_close_cancelled,
            gamepad=self._gamepad,
        )

    def _do_close_kwin_window(self, win_id: str) -> None:
        self._confirm_dialog = None
        self._dyn_active = None
        self._wm.close_window(win_id)
        QTimer.singleShot(1000, self._wm.refresh_now)
        self._gamepad.push_handler(self._handle_pad)
        self.showFullScreen()
        self.activateWindow()

    def _on_kwin_close_cancelled(self) -> None:
        self._confirm_dialog = None
        self._gamepad.push_handler(self._handle_pad)
        self.showFullScreen()
        self.activateWindow()

    def _on_close_cancelled(self) -> None:
        self._confirm_dialog = None

    def _do_close_app(self) -> None:
        self._confirm_dialog = None
        self._app_manager.terminate()

    # ── Akcje paska górnego ────────────────────────────────────────────────

    def _topbar_action(self, idx: int) -> None:
        action_type = TOPBAR_ACTIONS[idx]["type"]
        if action_type == "volume":
            overlay = VolumeOverlay(self._gamepad)
            overlay.closed.connect(self._on_volume_closed)
        elif action_type == "sleep":
            self._ask_system_action("Czy na pewno chcesz uśpić system?", ["systemctl", "suspend"])
        elif action_type == "restart":
            self._ask_system_action("Czy na pewno chcesz zrestartować komputer?", ["systemctl", "reboot"])
        elif action_type == "shutdown":
            self._ask_system_action("Czy na pewno chcesz wyłączyć komputer?", ["systemctl", "poweroff"])

    def _ask_system_action(self, question: str, cmd: list[str]) -> None:
        if self._confirm_dialog is not None:
            return
        self._confirm_dialog = ConfirmDialog(
            question=question,
            on_confirmed=lambda: self._do_system_action(cmd),
            on_cancelled=self._on_close_cancelled,
            gamepad=self._gamepad,
        )

    def _do_system_action(self, cmd: list[str]) -> None:
        self._confirm_dialog = None
        subprocess.Popen(cmd)

    def _on_volume_closed(self) -> None:
        self._focus_mode = "topbar"
        self._update_focus()
