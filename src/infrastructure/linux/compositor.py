"""Compositor detection and the backend seam that picks DE-specific adapters.

Kasual Desktop's only hard desktop-environment dependencies are window management 
and the wallpaper source. The rest of the stack talks to ports, so a single
detection here decides which concrete adapters the composition root wires up.
A compositor that offers neither an IPC CLI nor a toplevel-management protocol
degrades to no-op window management rather than crashing, so the app still starts
with reduced functionality.
"""

import enum
import logging
import os
import stat

from collections.abc import Callable
from typing import TYPE_CHECKING

from domain.catalog.window import Window
from domain.lifecycle.window_manager import WindowManager
from domain.shell.wallpaper import SystemWallpaper

if TYPE_CHECKING:
    from infrastructure.common.qt.desktop.surface import DesktopSurface
    from infrastructure.common.qt.ui.tray import TrayIconFor
    from infrastructure.linux.display.screensaver import ScreenSaverWaker

logger = logging.getLogger(__name__)


class Compositor(enum.Enum):
    KDE = "kde"
    GNOME = "gnome"
    SWAY = "sway"
    HYPRLAND = "hyprland"
    COSMIC = "cosmic"
    LABWC = "labwc"
    WAYFIRE = "wayfire"
    UNKNOWN = "unknown"


WLROOTS = frozenset({
    Compositor.SWAY, Compositor.HYPRLAND, Compositor.LABWC, Compositor.WAYFIRE,
})

# wlroots keeps layer-shell TOP above every window; cosmic-comp 1.5.0 dies on an
# unmap. Either way the Desktop must stay mapped.
CEDE_BY_SINKING = WLROOTS | {Compositor.COSMIC}


def _is_socket(path: str) -> bool:
    try:
        return stat.S_ISSOCK(os.stat(path).st_mode)
    except OSError:
        return False


def _in_sway_session() -> bool:
    socket_path = os.environ.get("SWAYSOCK", "")
    return bool(socket_path) and _is_socket(socket_path)


def _in_hyprland_session() -> bool:
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    if not signature:
        return False
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")
    return any(
        _is_socket(os.path.join(base, "hypr", signature, ".socket.sock"))
        for base in (runtime_dir, "/tmp")   # /tmp: Hyprland before 0.40
        if base
    )


def _session_names() -> str:
    """The session's own names, lowercased. Raspberry Pi OS reports its compositor
    only inside a composite name (``LXDE-pi-labwc``), so these are matched loosely."""
    return ":".join((
        os.environ.get("XDG_CURRENT_DESKTOP", ""),
        os.environ.get("XDG_SESSION_DESKTOP", ""),
    )).lower()


def detect_compositor() -> Compositor:
    """Identify the running Wayland compositor from session env vars.

    A wlroots instance handle (Sway's SWAYSOCK, Hyprland's signature) is decided
    first: it is exported only inside that compositor's own session, whereas a
    nested Sway or Hyprland run under a KDE session inherits KDE_FULL_SESSION from
    its parent and would otherwise be taken for KDE.

    The handle only counts while its socket is alive. Sway's packaging imports
    SWAYSOCK into the systemd user manager, which outlives the session and hands
    the stale value to every session that follows.
    """
    if _in_sway_session():
        return Compositor.SWAY
    if _in_hyprland_session():
        return Compositor.HYPRLAND
    desktop = _session_names()
    if os.environ.get("KDE_FULL_SESSION") or "kde" in desktop:
        return Compositor.KDE
    if "gnome" in desktop:
        return Compositor.GNOME
    if "cosmic" in desktop:
        return Compositor.COSMIC
    if "labwc" in desktop:
        return Compositor.LABWC
    if "wayfire" in desktop:
        return Compositor.WAYFIRE
    return Compositor.UNKNOWN


def layer_shell_available(compositor: Compositor | None = None) -> bool:
    """Whether Kasual's surfaces can really become wlr-layer-shell surfaces.

    Two independent things must hold, and both have bitten: the compositor has to
    implement the protocol (Mutter does not), and the LayerShellQt binding for this
    Qt has to be installed — Debian, Ubuntu and Pop!_OS still package it for Qt5
    only. Neither half is safe to assume from "Wayland, and not GNOME": naming the
    integration when it cannot load leaves every window unmapped, and an anchored
    overlay that waits for the compositor to size it never appears at all.
    """
    if (compositor or detect_compositor()) is Compositor.GNOME:
        return False
    from infrastructure.linux.wayland.layer_shell import is_available
    return is_available()


class NullWindowManager(WindowManager):
    """No-op WindowManager for unrecognised compositors: an empty window list and
    silently ignored operations, so the app runs (without window switching) instead
    of crashing where no supported IPC backend exists."""

    def start_periodic_refresh(self, interval_ms: int = 3000) -> None:
        pass

    def stop_refresh(self) -> None:
        pass

    def refresh_now(self) -> None:
        pass

    def get_active_window_id(self) -> str | None:
        return None

    def get_cached_title(self, window_id: str) -> str | None:
        return None

    def activate_window(self, window_id: str) -> None:
        pass

    def close_window(self, window_id: str) -> None:
        pass

    def minimize_windows_for_pids(self, pids: set[int]) -> None:
        pass

    def activate_windows_for_pids(self, pids: set[int]) -> None:
        pass

    def raise_self(self) -> None:
        pass

    def raise_windows_for_pid_exact(self, pid: int) -> None:
        pass

    def window_exists(self, window_id: str) -> bool:
        return False

    def cached_windows(self) -> list[Window]:
        return []

    def on_windows_updated(
        self, handler: Callable[[list[Window]], None]
    ) -> Callable[[], None]:
        return lambda: None

    def close(self) -> None:
        pass


def build_window_manager(compositor: Compositor | None = None) -> WindowManager:
    """Construct the WindowManager adapter for *compositor* (detected if omitted)."""
    compositor = compositor or detect_compositor()
    if compositor is Compositor.KDE:
        from infrastructure.kde.wm.window_manager import KWinWindowManager
        return KWinWindowManager()
    if compositor is Compositor.SWAY:
        from infrastructure.wlroots.wm.sway import SwayWindowManager
        return SwayWindowManager()
    if compositor is Compositor.HYPRLAND:
        from infrastructure.wlroots.wm.hyprland import HyprlandWindowManager
        return HyprlandWindowManager()
    if compositor is Compositor.GNOME:
        from infrastructure.gnome.helper import helper_present
        if helper_present():
            from infrastructure.gnome.wm.window_manager import GnomeWindowManager
            return GnomeWindowManager()
        logger.warning(
            "GNOME session without the Kasual Helper extension; window switching disabled")
        return NullWindowManager()
    if compositor is Compositor.COSMIC:
        # cosmic-comp speaks ext-foreign-toplevel-list plus its own cosmic-toplevel
        # extensions, not wlr-foreign-toplevel-management, so it needs its own
        # backend rather than the shared wlroots one below.
        from infrastructure.cosmic.wm.window_manager import CosmicWindowManager
        from infrastructure.linux.wayland.client import WaylandError
        try:
            return CosmicWindowManager()
        except (OSError, WaylandError) as exc:
            logger.warning(
                "COSMIC session without the toplevel protocols (%s); "
                "window switching disabled", exc)
            return NullWindowManager()
    from infrastructure.wlroots.wm import foreign_toplevel
    window_manager = foreign_toplevel.build()
    if window_manager is not None:
        return window_manager
    logger.warning(
        "No window-manager backend for compositor %s; window switching disabled",
        compositor.value,
    )
    return NullWindowManager()


def build_system_wallpaper(compositor: Compositor | None = None) -> SystemWallpaper:
    """Construct the SystemWallpaper adapter for *compositor* (detected if omitted)."""
    compositor = compositor or detect_compositor()
    if compositor is Compositor.KDE:
        from infrastructure.kde.display.wallpaper import KdeSystemWallpaper
        return KdeSystemWallpaper()
    if compositor is Compositor.SWAY:
        from infrastructure.wlroots.display.wallpaper import SwayWallpaper
        return SwayWallpaper()
    if compositor is Compositor.HYPRLAND:
        from infrastructure.wlroots.display.wallpaper import HyprlandWallpaper
        return HyprlandWallpaper()
    if compositor is Compositor.WAYFIRE:
        from infrastructure.wlroots.display.wallpaper import WayfireWallpaper
        return WayfireWallpaper()
    if compositor is Compositor.GNOME:
        from infrastructure.gnome.display.wallpaper import GnomeSystemWallpaper
        return GnomeSystemWallpaper()
    if compositor is Compositor.COSMIC:
        from infrastructure.cosmic.display.wallpaper import CosmicSystemWallpaper
        return CosmicSystemWallpaper()
    from infrastructure.linux.display.wallpaper import PcmanfmWallpaper
    return PcmanfmWallpaper()


def build_screensaver_waker(compositor: Compositor | None = None) -> "ScreenSaverWaker":
    """Construct the gamepad-activity → screensaver wake for *compositor*.

    GNOME's freedesktop ScreenSaver proxy only handles Inhibit, so the poke goes
    through the Kasual Helper extension there; everywhere else the standard
    ``SimulateUserActivity`` is used (a harmless no-op where unimplemented)."""
    from infrastructure.linux.display.screensaver import (
        ScreenSaverWaker, simulate_freedesktop_activity,
    )
    if (compositor or detect_compositor()) is Compositor.GNOME:
        from infrastructure.gnome.helper import simulate_user_activity
        return ScreenSaverWaker(simulate_user_activity)
    return ScreenSaverWaker(simulate_freedesktop_activity)


def build_tray_icon_source(compositor: Compositor | None = None) -> "TrayIconFor":
    """Pick how the tray icon is drawn for *compositor* (detected if omitted).

    COSMIC's status area renders a StatusNotifierItem's ``IconName`` and ignores a
    pixmap-only item, which is what a Font Awesome glyph amounts to — so there the
    icon comes from the desktop's theme instead, and the connection state moves to
    the tooltip. Every other host draws the glyph, colour and all.
    """
    from infrastructure.common.qt.ui.tray import glyph_icon, themed_icon
    is_cosmic = (compositor or detect_compositor()) is Compositor.COSMIC
    return themed_icon if is_cosmic else glyph_icon


def build_desktop_surface(compositor: Compositor | None = None) -> "DesktopSurface":
    """Construct the DesktopSurface adapter for *compositor* (detected if omitted).

    Layer-shell compositors (KWin, cosmic-comp and every wlroots one) promote the
    Desktop to a wlr-layer-shell surface; GNOME (no layer-shell) uses a frameless
    window that the Kasual Helper extension pins above the foreground app.
    """
    compositor = compositor or detect_compositor()
    if compositor is Compositor.GNOME:
        from infrastructure.gnome.helper import helper_present
        if helper_present():
            from infrastructure.gnome.qt.surface import GnomeSurface
            return GnomeSurface()
    from infrastructure.linux.wayland.surface import LayerShellSurface
    return LayerShellSurface(cede_to_bottom=compositor in CEDE_BY_SINKING)
