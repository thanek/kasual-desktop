"""System actions — the catalog of what Kasual can do from the top bar / home menu.

This is the single source of truth for *which* actions exist, *in what order*,
*which require a confirmation*, and *what each one does* (a call onto an injected
port). It is the "WHAT" — pure application logic, free of Qt and of any concrete
adapter. How each action looks (icon, colour, localized label) and the wording of
its confirmation live next door in :mod:`domain.system.action_view`; the
concrete power/desktop adapters are wired in at the composition root. Executing an
action (the confirm-gating) lives next door in :mod:`domain.system.runner`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from domain.system.desktop_shell import DesktopShell
from domain.system.power_control import PowerControl

# Action identities — stable keys shared with the presentation table and the
# top-bar / home-menu renderers.
NETWORK       = "network"
NOTIFICATIONS = "notifications"
VOLUME        = "volume"
BRIGHTNESS    = "brightness"
SLEEP         = "sleep"
RESTART       = "restart"
SHUTDOWN      = "shutdown"
HIDE_DESKTOP  = "hide_desktop"


@dataclass
class ActionDeps:
    """Collaborators the actions drive, injected behind ports. The concrete
    implementations (e.g. SystemdPowerControl) are chosen at the composition
    root so this stays free of any adapter dependency."""

    desktop: DesktopShell
    power:   PowerControl


@dataclass(frozen=True)
class SystemAction:
    """One action: whether it needs confirming, and its effect on the ports."""

    needs_confirmation: bool
    effect:             Callable[[ActionDeps], None]


# Insertion order defines the top-bar button order and the home-menu order.
ACTIONS: dict[str, SystemAction] = {
    VOLUME:        SystemAction(False, lambda d: d.desktop.open_volume_overlay()),
    BRIGHTNESS:    SystemAction(False, lambda d: d.desktop.open_brightness_overlay()),
    SLEEP:         SystemAction(True,  lambda d: d.power.suspend()),
    RESTART:       SystemAction(True,  lambda d: d.power.reboot()),
    SHUTDOWN:      SystemAction(True,  lambda d: d.power.poweroff()),
    NOTIFICATIONS: SystemAction(False, lambda d: d.desktop.open_notifications_overlay()),
    NETWORK:       SystemAction(False, lambda d: d.desktop.open_network_overlay()),
    HIDE_DESKTOP:  SystemAction(False, lambda d: d.desktop.pause()),
}
