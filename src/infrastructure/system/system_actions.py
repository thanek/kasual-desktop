"""System action dispatch — single source of truth for all topbar/home-menu actions."""

from collections.abc import Callable
from dataclasses import dataclass, field

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

from ports import DesktopShell, PowerControl
from infrastructure.system.power import SystemdPowerControl


@dataclass
class ActionDeps:
    """Collaborators the actions drive, injected behind ports."""

    desktop: DesktopShell
    power:   PowerControl = field(default_factory=SystemdPowerControl)


# Ordered dict — insertion order defines topbar button order.
# confirmation: translated string shown in ConfirmDialog; None = execute immediately.
# action:       callable(d: ActionDeps) — talks only to the injected ports.
ACTIONS: dict[str, dict] = {
    "volume": {
        "label": QT_TRANSLATE_NOOP("Kasual", "Volume"),
        "icon": "fa5s.volume-up",
        "color": "#3b4252",
        "confirmation": None,
        "action": lambda d: d.desktop.open_volume_overlay(),
    },
    "sleep": {
        "label": QT_TRANSLATE_NOOP("Kasual", "Sleep"),
        "icon": "fa5s.moon",
        "color": "#4c566a",
        "confirmation": QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to sleep?"),
        "action": lambda d: d.power.suspend(),
    },
    "restart": {
        "label": QT_TRANSLATE_NOOP("Kasual", "Restart"),
        "icon": "fa5s.redo-alt",
        "color": "#5e81ac",
        "confirmation": QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to restart?"),
        "action": lambda d: d.power.reboot(),
    },
    "shutdown": {
        "label": QT_TRANSLATE_NOOP("Kasual", "Shut Down"),
        "icon": "fa5s.power-off",
        "color": "#bf616a",
        "confirmation": QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to shut down?"),
        "action": lambda d: d.power.poweroff(),
    },
    "hide_desktop": {
        "label": QT_TRANSLATE_NOOP("Kasual", "Minimize Desktop"),
        "icon": "fa5s.window-minimize",
        "color": "#d580ff",
        "confirmation": None,
        "action": lambda d: d.desktop.pause(),
    },
}


class ActionRunner:
    """Executes system actions for a given context (deps + confirmation UI)."""

    def __init__(
            self,
            deps: ActionDeps,
            show_confirm: Callable[[str, Callable[[], None]], None],
    ) -> None:
        self._deps         = deps
        self._show_confirm = show_confirm

    def run(self, action_type: str) -> None:
        spec = ACTIONS[action_type]
        execute = lambda: spec["action"](self._deps)
        if spec["confirmation"] is not None:
            question = QCoreApplication.translate("Kasual", spec["confirmation"])
            self._show_confirm(question, execute)
        else:
            execute()
