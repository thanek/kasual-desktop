import logging
import os
import signal
import sys
from pathlib import Path

# Layer-shell requires the native Wayland platform plus KDE's layer-shell shell
# integration; both must be selected before QApplication is created. setdefault
# lets the environment override (e.g. tests force offscreen).
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
os.environ.setdefault("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell")

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from application import Application
from infrastructure.audio.feedback import SoundFeedback
from infrastructure.input.gamepad_watcher import GamepadWatcher
from infrastructure.qt.desktop import build_desktop
from infrastructure.qt.overlays.home_overlay import HomeOverlayFactory
from infrastructure.qt.ui.tray import SystemTray
from infrastructure.system.app_config import load_apps
from infrastructure.system.app_manager import AppManager
from infrastructure.system.log_viewer_launcher import LogViewerLauncher
from infrastructure.system.power import SystemdPowerControl
from infrastructure.system.volume import PactlVolumeControl
from infrastructure.qt.scheduler import QtScheduler
from infrastructure.system.kde_wallpaper import KdeSystemWallpaper
from domain.system.actions import ActionDeps
from infrastructure.system.window_manager import KWinWindowManager
from infrastructure.qt.i18n import install_translations

logger = logging.getLogger(__name__)

_LOG_FMT      = "%(asctime)s  [%(name)-22s]  %(levelname)-8s  %(message)s"
_LOG_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _setup_logging() -> Path:
    log_dir = Path.home() / ".local" / "cache" / "kasual"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "kasual.log"

    fmt = logging.Formatter(_LOG_FMT, datefmt=_LOG_DATE_FMT)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)

    logging.basicConfig(level=logging.INFO, handlers=[stream_handler, file_handler])
    return log_file


def main() -> None:
    # Restore default Ctrl+C handling: Qt's Wayland event loop swallows SIGINT
    # (Python's handler never runs while app.exec() blocks), leaving the app
    # unkillable from the terminal. SIG_DFL lets the OS terminate it directly.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    log_file = _setup_logging()
    logger.info("Running Kasual Desktop")

    apps = load_apps()
    logger.info("Loaded %d apps", len(apps))

    app = QApplication(sys.argv)
    app.setApplicationName("Kasual Desktop")
    app.setQuitOnLastWindowClosed(False)

    install_translations(app, str(Path(__file__).parent.parent / "locale"))

    gamepad = GamepadWatcher()
    wm = KWinWindowManager()
    feedback = SoundFeedback()
    # One PowerControl shared by the Desktop's action runner and the Application.
    power = SystemdPowerControl()
    desktop = build_desktop(
        apps=apps, gamepad=gamepad, window_manager=wm,
        wallpaper=KdeSystemWallpaper(), feedback=feedback,
        volume=PactlVolumeControl(), power=power, scheduler=QtScheduler(),
        process_manager=AppManager(),
    )

    # The log viewer runs in its own process so it is a normal xdg window, not a
    # layer-shell surface (see LogViewerLauncher).
    log_viewer = LogViewerLauncher(
        log_file=str(log_file),
        entry=Path(__file__).parent / "log_viewer_main.py",
    )
    tray = SystemTray(
        on_show=lambda: (feedback.play("start"), desktop.show_desktop()),
        on_logs=log_viewer.open,
        on_quit=app.quit,
    )

    controller = Application(
        gamepad=gamepad,
        desktop=desktop,
        app_control=desktop.app_control,
        action_deps=ActionDeps(desktop=desktop, power=power),
        tray=tray,
        wm=wm,
        overlay_factory=HomeOverlayFactory(gamepad, feedback),
    )
    wm.start_periodic_refresh(3000)
    app.aboutToQuit.connect(controller.shutdown)
    app.aboutToQuit.connect(log_viewer.close)

    QTimer.singleShot(0, feedback.init)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
