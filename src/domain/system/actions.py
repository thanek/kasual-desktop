"""System actions — the catalog of what Kasual can do from the top bar / home menu.

The single source of truth for *which* actions exist, *in what order*, *which
require a confirmation*, *what each one does* (a call onto an injected port), and
*how each one looks/reads* (icon, colour, localized label, confirmation wording).

Identity, effect and presentation used to live in two parallel dicts keyed by the
same action keys — adding an action meant editing both, with nothing keeping them
in sync. They are one :class:`SystemAction` per key now. Executing an action (the
confirm-gating) lives next door in :mod:`domain.system.runner`; turning these into
render-ready menu items / a confirm callback lives in
:mod:`domain.system.action_view`.

It is pure application logic — free of Qt and of any concrete adapter. Its only
outward need is translation, which it gets through the `domain.shared.i18n` port.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from domain.shared.i18n import translate
from domain.system.desktop_shell import DesktopShell
from domain.system.power_control import PowerControl

# Action identities — stable keys shared with the renderers (top bar / home menu).
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
    """One action: what it does, whether it needs confirming, and how it looks.

    Invariant: ``needs_confirmation`` ⟺ ``confirm_question is not None`` — a
    confirmable action carries the wording of its question, an immediate one
    does not.
    """

    effect:             Callable[[ActionDeps], None]
    label:              str          # source string; re-translated at render time
    icon:               str          # qtawesome glyph name
    color:              str
    needs_confirmation: bool        = False
    confirm_question:   str | None  = None   # source string; None for immediate actions


# The `translate(...)` calls below run at import time — before the composition
# root installs a backend — so they return the source string unchanged and act
# purely as extraction markers (pylupdate6 harvests them). The actual
# localization happens when consumers re-translate the label/question at render
# time (see action_view.system_action_items / make_action_confirm); keep the
# literal `translate("Kasual Desktop", "...")` call shape — pylupdate6 scans
# statically and only harvests that exact form.
#
# Insertion order defines the top-bar button order and the home-menu order.
ACTIONS: dict[str, SystemAction] = {
    VOLUME: SystemAction(
        lambda d: d.desktop.open_volume_overlay(),
        translate("Kasual Desktop", "Volume"), "fa5s.volume-up", "#3b4252",
    ),
    BRIGHTNESS: SystemAction(
        lambda d: d.desktop.open_brightness_overlay(),
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
        translate("Kasual Desktop", "Network"), "fa5s.wifi", "#81a1c1",  # icon overridden live in the top bar
    ),
    HIDE_DESKTOP: SystemAction(
        lambda d: d.desktop.pause(),
        translate("Kasual Desktop", "Minimize Kasual Desktop"), "fa5s.window-minimize", "#d580ff",
    ),
}
