"""The catalog of system actions — identity, effect and presentation per key."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from domain.shared.i18n import translate
from domain.system.desktop_shell import DesktopShell
from domain.system.power_control import PowerControl

NETWORK       = "network"
NOTIFICATIONS = "notifications"
VOLUME        = "volume"
BRIGHTNESS    = "brightness"
SLEEP         = "sleep"
RESTART       = "restart"
SHUTDOWN      = "shutdown"
HIDE_DESKTOP  = "hide_desktop"
GAMEPAD_ACCESS = "gamepad_access"

# First is the out-of-the-box default.
POWER_ACTIONS = (SLEEP, RESTART, SHUTDOWN)


@dataclass
class ActionDeps:
    """Collaborators the actions drive, injected behind ports."""

    desktop: DesktopShell
    power:   PowerControl


@dataclass(frozen=True)
class SystemAction:
    """One action: what it does, whether it needs confirming, and how it looks.

    Invariant: ``needs_confirmation`` ⟺ ``confirm_question is not None``.
    """

    effect:             Callable[[ActionDeps], None]
    label:              str          # source string, re-translated at render
    icon:               str
    color:              str
    needs_confirmation: bool        = False
    confirm_question:   str | None  = None   # source string, None for immediate actions


# The translate() calls run at import (before a backend is installed), so they
# pass through as pylupdate6 extraction markers — keep the literal call shape.
# Insertion order defines the top-bar / home-menu order.
ACTIONS: dict[str, SystemAction] = {
    VOLUME: SystemAction(
        # Presentation-only: adjusted live, never dispatched through the runner.
        lambda d: None,
        translate("Kasual Desktop", "Volume"), "fa5s.volume-up", "#3b4252",
    ),
    BRIGHTNESS: SystemAction(
        # Presentation-only; shown only where the backlight is controllable.
        lambda d: None,
        translate("Kasual Desktop", "Brightness"), "fa5s.sun", "#434c5e",
    ),
    SLEEP: SystemAction(
        lambda d: d.power.suspend(),
        translate("Kasual Desktop", "Sleep"), "fa5s.moon", "#4c566a",
        needs_confirmation=True,
        confirm_question=translate("Kasual Desktop", "Are you sure you want to sleep?"),
    ),
    RESTART: SystemAction(
        lambda d: d.power.reboot(),
        translate("Kasual Desktop", "Restart"), "fa5s.redo-alt", "#5e81ac",
        needs_confirmation=True,
        confirm_question=translate("Kasual Desktop", "Are you sure you want to restart?"),
    ),
    SHUTDOWN: SystemAction(
        lambda d: d.power.poweroff(),
        translate("Kasual Desktop", "Shut Down"), "fa5s.power-off", "#bf616a",
        needs_confirmation=True,
        confirm_question=translate("Kasual Desktop", "Are you sure you want to shut down?"),
    ),
    NOTIFICATIONS: SystemAction(
        lambda d: d.desktop.open_notifications_overlay(),
        translate("Kasual Desktop", "Notifications"), "fa5s.bell", "#ebcb8b",
    ),
    NETWORK: SystemAction(
        lambda d: d.desktop.open_network_overlay(),
        translate("Kasual Desktop", "Network"), "fa5s.wifi", "#81a1c1",  # icon overridden live
    ),
    HIDE_DESKTOP: SystemAction(
        lambda d: d.desktop.pause(),
        translate("Kasual Desktop", "Minimize Kasual Desktop"), "fa5s.window-minimize", "#d580ff",
    ),
    GAMEPAD_ACCESS: SystemAction(
        lambda d: d.desktop.open_gamepad_access_check(),
        translate("Kasual Desktop", "Check gamepad access"), "fa5s.gamepad", "#8fbcbb",
    ),
}
