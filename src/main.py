import logging
import sys
from pathlib import Path

import yaml
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt

from gamepad_watcher import GamepadWatcher
from desktop import Desktop
from home_overlay import HomeOverlay
from window_manager import KWinWindowManager

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  [%(name)-22s]  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler()],
    )


def _load_apps() -> list[dict]:
    cfg_path = Path(__file__).parent.parent / "apps.yml"
    with open(cfg_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("apps", [])


def _make_tray_icon() -> QIcon:
    px = QPixmap(32, 32)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#88c0d0"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    painter.setBrush(QColor("#0b140e"))
    painter.drawEllipse(8, 8, 16, 16)
    painter.end()
    return QIcon(px)


def main() -> None:
    _setup_logging()
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
    overlay = HomeOverlay(gamepad=gamepad)

    # Odświeżaj listę okien co 3 sekundy
    wm.start_periodic_refresh(3000)

    # ── BTN_MODE → pokaż overlay z kontekstem ──────────────────────────────

    def _on_btn_mode() -> None:
        running_idx = desktop.app_manager.running_idx()
        if running_idx is None:
            overlay.show_overlay(
                on_cancel=lambda: (desktop.showFullScreen(), desktop.activateWindow()),
            )
        else:
            # Zapamiętaj aktywne okno zanim overlay przykryje ekran
            prev_win = wm.get_active_window_id()
            app_name = apps[running_idx]["name"]

            logger.debug("BTN_MODE: aktywne okno=%s", prev_win)

            extra = [
                {
                    "label":    "  Powrót do Pulpitu",
                    "icon":     "fa5s.home",
                    "callback": desktop.show_desktop,
                },
                {
                    "label":    f"  Zamknij {app_name}",
                    "icon":     "fa5s.times-circle",
                    "callback": desktop.request_close_running_app,
                },
                {
                    "label":    "  Anuluj",
                    "icon":     "fa5s.times",
                    "callback": lambda win=prev_win: wm.activate_window(win) if win else None,
                },
            ]
            overlay.show_overlay(extra_items=extra)

    gamepad.btn_mode_pressed.connect(_on_btn_mode)

    # ── Tray icon ──────────────────────────────────────────────────────────

    tray = QSystemTrayIcon(_make_tray_icon())
    tray.setToolTip("Console Desktop")

    tray_menu = QMenu()
    show_action = tray_menu.addAction("Pokaż pulpit")
    show_action.triggered.connect(lambda: (desktop.showFullScreen(), desktop.activateWindow()))
    tray_menu.addSeparator()
    quit_action = tray_menu.addAction("Zamknij")
    quit_action.triggered.connect(app.quit)

    tray.setContextMenu(tray_menu)
    tray.activated.connect(
        lambda reason: (desktop.showFullScreen(), desktop.activateWindow())
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
