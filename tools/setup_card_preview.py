"""Show a setup card on its own, without starting Kasual Desktop.

Usage:
    python3 setup_card_preview.py [source|packaged|no-udev|no-uinput|ready|gnome]

source     pretends the access rule was never installed (a source checkout)
packaged   pretends the rule is installed but has not been applied
no-udev    pretends a host with no udevadm at all
no-uinput  pretends /dev/uinput is closed, with the gamepad readable
ready      uses this machine as it really is
gnome      the helper-extension card, which blocks instead of letting you past

In the pretending scenarios the fault stays until the marker file exists, so
"Check again" has something to discover: with the card open, run

    touch /tmp/kd-access-fixed

and press Check again.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from PyQt6.QtWidgets import QApplication                                # noqa: E402

from domain.input_access.ports import NodeAccess                        # noqa: E402
from domain.input_access.recipes import all_recipes                     # noqa: E402
from domain.input_access.requirement import GamepadAccess               # noqa: E402
from domain.preflight.extension import (                                # noqa: E402
    ENABLE, LOG_OUT, ExtensionState, HelperExtension,
)
from domain.preflight.extension_recipes import (                        # noqa: E402
    all_recipes as extension_recipes,
)
from domain.setup.gate import SetupGate                                 # noqa: E402
from domain.setup.readiness import SetupReadiness                       # noqa: E402
from infrastructure.common.qt.i18n import install_translations          # noqa: E402
from infrastructure.common.qt.overlays.setup_overlay import QtSetupView  # noqa: E402
from infrastructure.linux.input.access import (                         # noqa: E402
    RULE_FILE, LinuxDeviceAccess,
)
from infrastructure.linux.system_facts import LinuxSystemFacts          # noqa: E402

MARKER = Path("/tmp/kd-access-fixed")


class FakeAccess(LinuxDeviceAccess):
    def __init__(self, *, rule=True, udev=True, uinput_open=True, pad=True) -> None:
        self._rule = rule
        self._udev = udev
        self._uinput_open = uinput_open
        self._pad = pad

    @property
    def _fixed(self) -> bool:
        return MARKER.exists()

    def uinput(self):
        if self._uinput_open or self._fixed:
            return NodeAccess.GRANTED
        return NodeAccess.DENIED

    def joysticks(self):
        if not self._pad:
            return ()
        return (NodeAccess.GRANTED if self._fixed else NodeAccess.DENIED,)

    def grants_joystick_access(self):
        return self._fixed

    def access_rule_installed(self):
        return self._rule

    def udev_available(self):
        return self._udev


class FakeProbe:
    def __init__(self, state: ExtensionState) -> None:
        self._state = state

    def state(self):
        return ExtensionState.READY if MARKER.exists() else self._state


_SCENARIOS = {
    "source": lambda: FakeAccess(rule=False),
    "packaged": lambda: FakeAccess(rule=True),
    "no-udev": lambda: FakeAccess(rule=False, udev=False, pad=False),
    "no-uinput": lambda: FakeAccess(uinput_open=False, pad=False),
    "ready": LinuxDeviceAccess,
}


def _gamepad_access_gate(view, scenario):
    return SetupGate(
        SetupReadiness(
            GamepadAccess(_SCENARIOS[scenario]()),
            LinuxSystemFacts(),
            all_recipes(str(REPO / "packaging" / RULE_FILE)),
        ),
        view,
    )


def _extension_gate(view, app):
    return SetupGate(
        SetupReadiness(
            HelperExtension(FakeProbe(ExtensionState.UNLOADED)),
            LinuxSystemFacts(),
            extension_recipes("kasual-helper@consoledesktop.org"),
        ),
        view,
        remedies={ENABLE: lambda: print("enable pressed"),
                  LOG_OUT: lambda: print("log out pressed")},
        on_abort=app.quit,
    )


def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "source"
    if scenario not in _SCENARIOS and scenario != "gnome":
        sys.exit(__doc__)

    app = QApplication(sys.argv)
    app.setApplicationName("Kasual Desktop")
    install_translations(app, str(REPO / "locale"))

    view = QtSetupView(MagicMock(), MagicMock())
    gate = (_extension_gate(view, app) if scenario == "gnome"
            else _gamepad_access_gate(view, scenario))
    gate.ensure(app.quit, force=True)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
