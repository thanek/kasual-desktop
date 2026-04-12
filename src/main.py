import logging
import sys
from pathlib import Path

import yaml
import qtawesome as qta
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QTimer

from gamepad_watcher import GamepadWatcher
from desktop import Desktop
from home_overlay import HomeOverlay
from log_viewer import LogViewer
from window_manager import KWinWindowManager
import sound_player

logger = logging.getLogger(__name__)


def _setup_logging() -> Path:
    log_dir  = Path.home() / ".local" / "share" / "console-desktop"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "console-desktop.log"

    fmt = logging.Formatter(
        "%(asctime)s  [%(name)-22s]  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)

    logging.basicConfig(level=logging.INFO, handlers=[stream_handler, file_handler])
    return log_file


def _load_apps() -> list[dict]:
    cfg_path = Path(__file__).parent.parent / "apps.yml"
    with open(cfg_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("apps", [])


def _make_tray_icon(connected: bool) -> QIcon:
    if connected:
        return qta.icon("fa5s.gamepad", color="#88c0d0")
    return qta.icon("fa5s.gamepad", color="#555555")


def main() -> None:
    log_file = _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Uruchamiam Console Desktop")

    apps = _load_apps()
    logger.info("Załadowano %d aplikacji", len(apps))

    app = QApplication(sys.argv)
    app.setApplicationName("Console Desktop")
    app.setQuitOnLastWindowClosed(False)

    gamepad = GamepadWatcher()
    wm      = KWinWindowManager()
    desktop = Desktop(apps=apps, gamepad=gamepad, window_manager=wm)
    overlay = HomeOverlay(gamepad=gamepad, on_hide_desktop=desktop.pause)

    # Odświeżaj listę okien co 3 sekundy
    wm.start_periodic_refresh(3000)

    # ── BTN_MODE → pokaż overlay z kontekstem ──────────────────────────────

    def _on_btn_mode() -> None:
        running_idx = desktop.app_manager.running_idx()
        dyn         = desktop.active_dynamic_window

        if running_idx is None and dyn is None:
            # Jesteśmy na Pulpicie → menu systemowe
            overlay.show_overlay(on_cancel=desktop.show_desktop)
            return

        # Jakaś aplikacja jest aktywna → menu kontekstowe
        if running_idx is not None:
            title    = apps[running_idx]["name"]
            close_cb = desktop.request_close_running_app
            cancel_cb = desktop.restore_dynamic_window   # no-op gdy brak dyn_active
        else:
            _, title  = dyn
            close_cb  = desktop.request_close_dynamic_window
            cancel_cb = desktop.restore_dynamic_window

        label = title if len(title) <= 22 else title[:21] + '…'
        extra = [
            {
                "label":    f"  Powrót do {label}",
                "icon":     "fa5s.times",
                "callback": cancel_cb,
            },
            {
                "label":    f"  Zamknij {label}",
                "icon":     "fa5s.times-circle",
                "callback": close_cb,
            },
            {
                "label": "  Powrót do Pulpitu",
                "icon": "fa5s.home",
                "callback": desktop.show_desktop,
            },
        ]
        overlay.show_overlay(extra_items=extra)

    gamepad.btn_mode_pressed.connect(_on_btn_mode)

    # ── Pad podłączony / odłączony ─────────────────────────────────────────

    def _on_connected_changed(connected: bool) -> None:
        tray.setIcon(_make_tray_icon(connected=connected))
        if connected:
            desktop.resume()
        else:
            overlay.hide_overlay()
            desktop.hide()

    gamepad.connected_changed.connect(_on_connected_changed)

    # ── Tray icon ──────────────────────────────────────────────────────────

    tray = QSystemTrayIcon(_make_tray_icon(connected=False))
    tray.setToolTip("Console Desktop")

    log_viewer = LogViewer(str(log_file))

    def _show_from_tray() -> None:
        sound_player.play("start")
        desktop.show_desktop()

    tray_menu = QMenu()
    show_action = tray_menu.addAction("Pokaż pulpit")
    show_action.triggered.connect(_show_from_tray)
    logs_action = tray_menu.addAction("Logi")
    logs_action.triggered.connect(log_viewer.show)
    tray_menu.addSeparator()
    quit_action = tray_menu.addAction("Zamknij")
    quit_action.triggered.connect(app.quit)

    tray.setContextMenu(tray_menu)
    tray.activated.connect(
        lambda reason: _show_from_tray()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()

    QTimer.singleShot(0, sound_player.init)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
