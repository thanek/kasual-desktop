"""System actions — the catalog of what Kasual can do from the top bar / home menu.

This is the single source of truth for *which* actions exist, *in what order*,
*which require a confirmation*, and *what each one does* (a call onto an injected
port). It is the "WHAT" — pure application logic, free of Qt and of any concrete
adapter. How each action looks (icon, colour, localized label) and the wording of
its confirmation live in the view layer (`infrastructure/qt/ui/action_view`); the
concrete power/desktop adapters are wired in at the composition root.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ports import DesktopShell, PowerControl

# Action identities — stable keys shared with the presentation table and the
# top-bar / home-menu renderers.
VOLUME       = "volume"
SLEEP        = "sleep"
RESTART      = "restart"
SHUTDOWN     = "shutdown"
HIDE_DESKTOP = "hide_desktop"


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
    VOLUME:       SystemAction(False, lambda d: d.desktop.open_volume_overlay()),
    SLEEP:        SystemAction(True,  lambda d: d.power.suspend()),
    RESTART:      SystemAction(True,  lambda d: d.power.reboot()),
    SHUTDOWN:     SystemAction(True,  lambda d: d.power.poweroff()),
    HIDE_DESKTOP: SystemAction(False, lambda d: d.desktop.pause()),
}


class ActionRunner:
    """Executes a system action: gates the confirmable ones behind the injected
    confirmation flow, runs the rest immediately.

    `confirm(action_key, execute)` is supplied by the view — it resolves the
    localized question for the key and shows the dialog, calling `execute` on
    acceptance. Keeping the question text out of here is what lets this stay
    Qt-free.
    """

    def __init__(
        self,
        deps:    ActionDeps,
        confirm: Callable[[str, Callable[[], None]], None],
    ) -> None:
        self._deps    = deps
        self._confirm = confirm

    def run(self, action_key: str) -> None:
        action  = ACTIONS[action_key]
        execute = lambda: action.effect(self._deps)
        if action.needs_confirmation:
            self._confirm(action_key, execute)
        else:
            execute()
