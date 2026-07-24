"""Session-wiring shared by both composition roots (`main.py`, `windows_main.py`).

Each platform builds its own OS-specific adapters, then hands them to these
helpers for the wiring that is identical either way — logging setup, the
provisioning branch, tray/controller assembly, and the deferred-start/
stop-on-quit pattern used by the notification and network monitors. Kept here
rather than duplicated so a fix made for one platform can't silently miss the
other.
"""

import faulthandler
import logging
import os
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from application import Application
from domain.provisioning.provisioning import needs_provisioning
from domain.shared.feedback import Cue
from domain.system.actions import ActionDeps
from infrastructure.common.qt.overlays.about_overlay import AboutOverlay
from infrastructure.common.qt.overlays.onboarding_overlay import OnboardingOverlayFactory
from infrastructure.common.qt.ui.tray import SystemTray, TrayIconFor, glyph_icon

logger = logging.getLogger(__name__)

_LOG_FMT      = "%(asctime)s  [%(name)-22s]  %(levelname)-8s  %(message)s"
_LOG_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_no_keep_alive: Callable[[object], None] = lambda _obj: None


def setup_logging(log_dir: Path) -> Path:
    """File + stderr handlers under `log_dir`. `KASUAL_DEBUG` raises the level to DEBUG."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "kasual.log"

    fmt = logging.Formatter(_LOG_FMT, datefmt=_LOG_DATE_FMT)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)

    level = logging.DEBUG if os.environ.get("KASUAL_DEBUG") else logging.INFO
    logging.basicConfig(level=level, handlers=[stream_handler, file_handler])
    _record_crashes(log_file)
    return log_file


# Kept open for the lifetime of the process: faulthandler writes to this file
# descriptor from a signal handler, long after Python has stopped running.
_crash_log = None


def _record_crashes(log_file: Path) -> None:
    """Have a fatal signal leave a Python stack behind in the log.

    A segfault inside Qt or a C extension otherwise leaves nothing at all — the
    process is gone before any handler runs and the log simply stops mid-sentence,
    which says only that Kasual died, never where. Every thread is dumped: the
    notification monitor and the gamepad watcher both live off the GUI thread.
    """
    global _crash_log
    try:
        _crash_log = open(log_file, "a", encoding="utf-8", buffering=1)
        faulthandler.enable(file=_crash_log, all_threads=True)
    except OSError as exc:
        logger.warning("Could not arm the crash handler: %s", exc)


def run_onboarding_or_start(
    provisioning,
    provisioning_uc,
    gamepad,
    feedback,
    start_session: Callable[[], None],
    keep_alive: Callable[[object], None] = _no_keep_alive,
) -> None:
    """First run shows the picker; otherwise goes straight to `start_session`.

    Confirming with zero apps still marks the catalog provisioned, so onboarding
    won't nag on next launch. `keep_alive` lets Windows park the overlay in its
    `_refs` bookkeeping — Linux's closures already keep it alive.
    """
    if needs_provisioning(provisioning):
        logger.info("First run — showing onboarding")
        onboarding = OnboardingOverlayFactory(gamepad, feedback).create()
        keep_alive(onboarding)
        onboarding.present(
            provisioning_uc.candidates(),
            on_confirm=lambda chosen: (provisioning_uc.complete(chosen), start_session()),
        )
    else:
        start_session()


def build_tray(
    *,
    feedback,
    desktop,
    log_viewer,
    version: str,
    gamepad,
    quit_fn: Callable[[], None],
    keep_alive: Callable[[object], None] = _no_keep_alive,
    icon_for: TrayIconFor = glyph_icon,
) -> SystemTray:
    def on_about() -> None:
        keep_alive(AboutOverlay(version, gamepad, feedback))

    return SystemTray(
        on_show=lambda: (feedback.play(Cue.START), desktop.show_desktop()),
        on_logs=log_viewer.open,
        on_about=on_about,
        on_quit=quit_fn,
        icon_for=icon_for,
    )


def build_controller(*, gamepad, desktop, tray, wm, power, hud) -> Application:
    return Application(
        gamepad=gamepad,
        desktop=desktop,
        app_control=desktop.app_control,
        action_deps=ActionDeps(desktop=desktop, power=power),
        tray=tray,
        wm=wm,
        overlay_factory=desktop.home_overlay_factory(),
        hud=hud,
    )


def wire_notification_badge(source, desktop) -> None:
    """Keeps the top-bar notifications badge in sync with the in-memory count."""
    source.on_notification(lambda _n: desktop.refresh_notification_badge())


def defer_start(app: QApplication, monitor) -> None:
    """Starts `monitor` once the event loop is running — never on the critical
    startup path — and stops it on quit."""
    QTimer.singleShot(0, monitor.start)
    app.aboutToQuit.connect(monitor.stop)
