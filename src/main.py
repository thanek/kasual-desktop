import logging
import sys
from pathlib import Path

import yaml
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from app import Application
from audio import sound_player
from desktop import Desktop
from input.gamepad_watcher import GamepadWatcher
from overlays.home_overlay import HomeOverlay
from system.window_manager import KWinWindowManager
from ui.log_viewer import LogViewer
from ui.tray import SystemTray

logger = logging.getLogger(__name__)


def _setup_logging() -> Path:
    log_dir  = Path.home() / ".local" / "cache" / "kasual"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "kasual.log"

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


def main() -> None:
    log_file = _setup_logging()
    logger.info("Uruchamiam Kasual")

    apps = _load_apps()
    logger.info("Załadowano %d aplikacji", len(apps))

    app = QApplication(sys.argv)
    app.setApplicationName("Kasual")
    app.setQuitOnLastWindowClosed(False)

    gamepad = GamepadWatcher()
    wm      = KWinWindowManager()
    desktop = Desktop(apps=apps, gamepad=gamepad, window_manager=wm)
    overlay = HomeOverlay(gamepad=gamepad, on_hide_desktop=desktop.pause)

    log_viewer = LogViewer(str(log_file))
    tray = SystemTray(
        on_show=lambda: (sound_player.play("start"), desktop.show_desktop()),
        on_logs=log_viewer.show,
        on_quit=app.quit,
    )

    controller = Application(
        apps=apps, gamepad=gamepad,
        desktop=desktop, overlay=overlay,
        tray=tray, wm=wm,
    )
    controller.start()

    QTimer.singleShot(0, sound_player.init)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
