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
from version import get_version
from infrastructure.common.audio.feedback import SoundFeedback
from infrastructure.common.single_instance import SingleInstanceGuard
from infrastructure.linux.input.gamepad_watcher import GamepadWatcher
from infrastructure.common.qt.desktop import build_desktop
from infrastructure.kde.qt.desktop.deferred_hide import DeferredHide
from infrastructure.kde.qt.desktop.surface import LayerShellSurface
from infrastructure.common.qt.icons import install_fontawesome5
from infrastructure.common.qt.overlays.about_overlay import AboutOverlay
from infrastructure.common.qt.overlays.home_overlay import HomeOverlayFactory
from infrastructure.common.qt.overlays.onboarding_overlay import OnboardingOverlayFactory
from infrastructure.common.qt.ui.tray import SystemTray
from infrastructure.common.catalog.app_config import (
    DesktopAppProvisioning, DesktopTileColorStore, DesktopTileOrderStore,
    load_apps,
)
from infrastructure.linux.catalog.app_discovery import WhichAppDiscovery
from infrastructure.linux.catalog.app_pinning import DesktopAppPinning
from infrastructure.linux.catalog.installed_apps import XdgInstalledApps
from domain.provisioning.provisioning import Provisioning, needs_provisioning
from domain.provisioning.add_apps import AppAdder
from infrastructure.linux.catalog.app_manager import AppManager
from infrastructure.linux.proc import parent_pid, is_game_pid
from infrastructure.linux.log.log_viewer_launcher import LogViewerLauncher
from infrastructure.linux.power.power import SystemdPowerControl
from infrastructure.linux.audio.volume import PactlVolumeControl
from infrastructure.linux.display.brightness import select_brightness_control
from infrastructure.common.qt.scheduler import QtScheduler
from infrastructure.linux.hud.mangohud import MangoHudControl
from domain.shared.feedback import Cue
from infrastructure.kde.display.wallpaper import KdeSystemWallpaper
from infrastructure.linux.notifications.notifications import KdeNotificationMonitor
from infrastructure.linux.network.network_manager import NMNetworkControl, NMNetworkMonitor
from domain.notifications.center import NotificationCenter
from domain.system.actions import ActionDeps
from domain.system.action_view import make_action_confirm
from domain.system.power_menu import PowerMenu
from infrastructure.common.catalog.preferences import DesktopPowerPreference
from infrastructure.kde.wm.window_manager import KWinWindowManager
from infrastructure.common.qt.i18n import install_translations

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

    level = logging.DEBUG if os.environ.get("KASUAL_DEBUG") else logging.INFO
    logging.basicConfig(level=level, handlers=[stream_handler, file_handler])
    return log_file


def main() -> None:
    # Restore default Ctrl+C handling: Qt's Wayland event loop swallows SIGINT
    # (Python's handler never runs while app.exec() blocks), leaving the app
    # unkillable from the terminal. SIG_DFL lets the OS terminate it directly.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    log_file = _setup_logging()
    version = get_version()
    logger.info("Running Kasual Desktop %s", version)

    app = QApplication(sys.argv)
    app.setApplicationName("Kasual Desktop")
    app.setApplicationVersion(version)
    app.setQuitOnLastWindowClosed(False)

    guard = SingleInstanceGuard(log_file.parent)
    if not guard.try_lock():
        sys.exit(0)
    app.aboutToQuit.connect(guard.release)

    # Use the bundled genuine Font Awesome 5 fonts, not the distro's Fork Awesome
    # substitute (see icons.install_fontawesome5). Before any icon is built.
    install_fontawesome5()

    install_translations(app, str(Path(__file__).parent.parent / "locale"))

    gamepad = GamepadWatcher()
    feedback = SoundFeedback()

    # Provisioning: a fresh install has no apps. We detect that via an explicit
    # marker (not dir-absence, so choosing zero apps still counts) and run
    # onboarding *before* the session comes up — load_apps() must see whatever
    # the user just picked. The bundled launchers resolve against the repo root.
    provisioning = DesktopAppProvisioning()
    provisioning_uc = Provisioning(
        provisioning, WhichAppDiscovery(),
        bundled_base=str(Path(__file__).parent.parent),
    )
    # The [＋] add-app tile reopens provisioning after first run: it offers every
    # installed app (XDG .desktop scan), minus the apps already pinned, and
    # persists the chosen ones through the same store as onboarding.
    app_adder = AppAdder(XdgInstalledApps(), provisioning)

    def start_session() -> None:
        """Bring up the Desktop and controller from the (now-provisioned) apps.

        Deferred behind onboarding via a callback continuation rather than a
        nested QEventLoop, matching how the rest of the app defers work."""
        apps = load_apps()
        logger.info("Loaded %d apps", len(apps))

        wm = KWinWindowManager()
        # One PowerControl shared by the Desktop's action runner and the Application.
        power = SystemdPowerControl()

        # One persisted power-default preference is the single source of truth
        # shared by the Home Overlay's Power split-button and the top bar's single
        # Power button (§7.10).
        power_preference = DesktopPowerPreference()

        # Recent-notifications feature: the KDE monitor (source port) feeds the
        # platform-agnostic NotificationCenter, which the Desktop's overlay reads.
        notification_center = NotificationCenter()
        notification_monitor = KdeNotificationMonitor()
        notification_monitor.on_notification(notification_center.record)

        volume = PactlVolumeControl()
        brightness = select_brightness_control()
        home_surface = bool(os.environ.get("KASUAL_HOME_SURFACE"))
        desktop = build_desktop(
            apps=apps, gamepad=gamepad, window_manager=wm,
            wallpaper=KdeSystemWallpaper(), feedback=feedback,
            volume=volume, brightness=brightness,
            power=power, scheduler=QtScheduler(),
            process_manager=AppManager(), notifications=notification_center,
            network_control=NMNetworkControl(),
            order_store=DesktopTileOrderStore(),
            color_store=DesktopTileColorStore(),
            app_pinning=DesktopAppPinning(),
            surface=LayerShellSurface(),
            parent_of=parent_pid,
            is_game_pid=is_game_pid,
            app_adder=app_adder,
            power_preference=power_preference,
            # §8 / Faza 5 (experimental): collapse the top bar into a persistent
            # Home-view surface. Off by default; opt in with KASUAL_HOME_SURFACE=1.
            home_surface_enabled=home_surface,
            deferred_hide_factory=lambda wm_, pm_, apps_, on_hide:
                DeferredHide(wm_, pm_, apps_, on_hide=on_hide),
        )
        # Keep the top-bar notifications badge in sync with the in-memory count.
        # Subscribed after `record` above, so the count is already updated when
        # this runs; delivered on the GUI thread by the monitor's signal hop.
        notification_monitor.on_notification(
            lambda _n: desktop.refresh_notification_badge()
        )

        # Network status indicator: the concrete adapter (NetworkManager) is the
        # only NM-aware piece; everything downstream depends on the domain
        # NetworkMonitor port, so it can be swapped for another backend here.
        network_monitor = NMNetworkMonitor()
        network_monitor.on_changed(desktop.update_network_status)
        desktop.update_network_status(network_monitor.current())

        # The log viewer runs in its own process so it is a normal xdg window,
        # not a layer-shell surface (see LogViewerLauncher).
        log_viewer = LogViewerLauncher(
            log_file=str(log_file),
            entry=Path(__file__).parent / "log_viewer_main.py",
        )
        tray = SystemTray(
            on_show=lambda: (feedback.play(Cue.START), desktop.show_desktop()),
            on_logs=log_viewer.open,
            on_about=lambda: AboutOverlay(version, gamepad, feedback),
            on_quit=app.quit,
        )

        # The sectioned factory needs the volume/brightness controls and a power
        # menu (sticky-default dropdown) backed by the same preference the top bar
        # reads. The top bar's Power dropdown (Y) runs + persists through it too.
        power_menu = PowerMenu(
            ActionDeps(desktop=desktop, power=power),
            power_preference,
            make_action_confirm(desktop.show_confirm),
        )
        desktop.set_power_menu(power_menu)
        # In persistent-surface mode contexts 2/3 reuse the Desktop's one Home
        # surface (so the header's live status carries over); otherwise each
        # BTN_MODE maps a fresh overlay.
        overlay_factory = (
            desktop.home_overlay_factory() if home_surface
            else HomeOverlayFactory(gamepad, feedback, volume, brightness, power_menu)
        )

        controller = Application(
            gamepad=gamepad,
            desktop=desktop,
            app_control=desktop.app_control,
            action_deps=ActionDeps(desktop=desktop, power=power),
            tray=tray,
            wm=wm,
            overlay_factory=overlay_factory,
            hud=MangoHudControl(),
        )
        wm.start_periodic_refresh(3000)
        # Start the notification monitor only once the event loop is running, so
        # its subprocess spawn can never sit on the critical startup path (e.g.
        # delaying the gamepad-connected activation). Non-essential to bring-up.
        QTimer.singleShot(0, notification_monitor.start)
        app.aboutToQuit.connect(controller.shutdown)
        app.aboutToQuit.connect(notification_monitor.stop)
        app.aboutToQuit.connect(log_viewer.close)

    if needs_provisioning(provisioning):
        logger.info("First run — showing onboarding")
        onboarding = OnboardingOverlayFactory(gamepad, feedback).create()
        # Confirm-only (the picker has no dismissal path); confirming with zero
        # apps still marks provisioned, so onboarding won't nag on next launch.
        onboarding.present(
            provisioning_uc.candidates(),
            on_confirm=lambda chosen: (provisioning_uc.complete(chosen), start_session()),
        )
    else:
        start_session()

    QTimer.singleShot(0, feedback.init)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
