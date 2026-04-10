import logging
import subprocess
import sys
from pathlib import Path

import yaml
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt

from gamepad_watcher import GamepadWatcher
from desktop import Desktop
from home_overlay import HomeOverlay

logger = logging.getLogger(__name__)


def _get_active_xwindow() -> str | None:
    """Zwróć ID aktywnego okna X11 (działa dla aplikacji XWayland, np. gier przez Proton)."""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=1,
        )
        win_id = result.stdout.strip()
        if not win_id or win_id == "0":
            return None
        return win_id
    except Exception:
        return None


def _get_xwindow_title(win_id: str) -> str | None:
    """Zwróć tytuł okna X11."""
    try:
        result = subprocess.run(
            ["xdotool", "getwindowname", win_id],
            capture_output=True, text=True, timeout=1,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _activate_xwindow(win_id: str) -> None:
    """Przywróć i aktywuj okno X11 (un-minimize + focus)."""
    try:
        subprocess.Popen(["xdotool", "windowactivate", "--sync", win_id])
    except Exception:
        logger.warning("xdotool windowactivate nieudane dla okna %s", win_id)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  [%(name)-22s]  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler()],
    )


def _load_apps() -> list[dict]:
    cfg_path = Path(__file__).parent / "apps.yml"
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
    app.setQuitOnLastWindowClosed(False)   # aplikacja żyje w tray nawet gdy okna są ukryte

    gamepad = GamepadWatcher()
    desktop = Desktop(apps=apps, gamepad=gamepad)
    overlay = HomeOverlay(gamepad=gamepad)

    # ── BTN_MODE → pokaż overlay z kontekstem ──────────────────────────────

    def _on_btn_mode() -> None:
        running_idx = desktop.app_manager.running_idx()
        if running_idx is None:
            overlay.show_overlay()
        else:
            # Pobierz aktywne okno PRZED pokazaniem overlay – to okno gry/aplikacji
            prev_win    = _get_active_xwindow()
            win_title   = _get_xwindow_title(prev_win) if prev_win else None
            app_name    = apps[running_idx]["name"]
            return_label = f"  Wróć do {win_title}" if win_title else f"  Wróć do {app_name}"

            logger.debug("BTN_MODE: aktywne okno=%s (%s)", prev_win, win_title)

            extra = [
                {
                    "label":    "  Powrót do Pulpitu",
                    "icon":     "fa5s.home",
                    "callback": lambda w=prev_win, t=win_title: desktop.show_desktop(
                        guest_win=w, guest_title=t
                    ),
                },
                {
                    "label":    return_label,
                    "icon":     "fa5s.arrow-left",
                    "callback": lambda win=prev_win: _activate_xwindow(win) if win else None,
                },
                {
                    "label":    f"  Zamknij {app_name}",
                    "icon":     "fa5s.times-circle",
                    "callback": desktop.request_close_running_app,
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
