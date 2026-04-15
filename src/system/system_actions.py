"""System action dispatch — single source of truth for all topbar/home-menu actions."""

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication


@dataclass
class ActionDeps:
    desktop: Any


# Ordered dict — insertion order defines topbar button order.
# confirmation: translated string shown in ConfirmDialog; None = execute immediately.
# action:       callable(d: ActionDeps) — no imports from Desktop needed here.
ACTIONS: dict[str, dict] = {
    "volume": {
        "label": QT_TRANSLATE_NOOP("Kasual", "Volume"),
        "icon": "fa5s.volume-up",
        "color": "#3b4252",
        "confirmation": None,
        "action": lambda d: d.desktop._open_volume_overlay(),
    },
    "sleep": {
        "label": QT_TRANSLATE_NOOP("Kasual", "Sleep"),
        "icon": "fa5s.moon",
        "color": "#4c566a",
        "confirmation": QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to sleep?"),
        "action": lambda d: subprocess.Popen(["systemctl", "suspend"]),
    },
    "restart": {
        "label": QT_TRANSLATE_NOOP("Kasual", "Restart"),
        "icon": "fa5s.redo-alt",
        "color": "#5e81ac",
        "confirmation": QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to restart?"),
        "action": lambda d: subprocess.Popen(["systemctl", "reboot"]),
    },
    "shutdown": {
        "label": QT_TRANSLATE_NOOP("Kasual", "Shut Down"),
        "icon": "fa5s.power-off",
        "color": "#bf616a",
        "confirmation": QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to shut down?"),
        "action": lambda d: subprocess.Popen(["systemctl", "poweroff"]),
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
