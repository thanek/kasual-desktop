"""The known paths to a readable gamepad, one recipe per kind of system.

Order matters: the first match wins. What separates them is not the distribution
but how Kasual Desktop got here — a package install already carries the access
rule and only needs it applied, a source checkout has to place it first, and a
host without udev has nothing but the ``input`` group to fall back on.

A recipe's strings are translated as it is built, which must therefore happen
after the composition root installs the translator.
"""

from domain.input_access.requirement import (
    JOYSTICK_NODES, NO_UDEV, RULE_INSTALLED, UINPUT_NODE,
)
from domain.setup.plan import Recipe, Step
from domain.shared.i18n import translate

INSTALLED_RULE_PATH = "/etc/udev/rules.d/99-kasual-desktop.rules"

_GAMEPAD_SUBSYSTEM = "input"
_UINPUT_SUBSYSTEM = "misc"

_RELOAD_COMMAND = (
    "sudo udevadm control --reload-rules && sudo udevadm trigger "
    f"--subsystem-match={_GAMEPAD_SUBSYSTEM} --subsystem-match={_UINPUT_SUBSYSTEM}"
)
_UINPUT_RELOAD = (
    "sudo modprobe uinput && sudo udevadm trigger "
    f"--subsystem-match={_UINPUT_SUBSYSTEM} --name-match=uinput"
)
_UINPUT_BY_HAND = (
    "sudo modprobe uinput "
    "&& sudo chgrp input /dev/uinput && sudo chmod 660 /dev/uinput"
)


def all_recipes(rule_source: str) -> tuple[Recipe, ...]:
    """*rule_source* is the rule file shipped alongside this checkout — the one
    a source run installs, so its contents live in exactly one place."""
    return (_without_udev(), _rule_already_installed(), _from_source(rule_source))


def _without_udev() -> Recipe:
    return Recipe(
        key="input-group",
        traits=(NO_UDEV,),
        notice=_notice(),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Join the input group"),
                instruction=translate(
                    "Kasual Desktop",
                    "Without udev there is no rule to install, so group "
                    "membership is what opens the device nodes. It applies to "
                    "new logins only — log out and back in afterwards.",
                ),
                check=JOYSTICK_NODES,
                command="sudo usermod -aG input $USER",
            ),
            _uinput_step(_UINPUT_BY_HAND),
        ),
    )


def _rule_already_installed() -> Recipe:
    return Recipe(
        key="reload-rule",
        traits=(RULE_INSTALLED,),
        notice=_notice(),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Apply the access rule"),
                instruction=translate(
                    "Kasual Desktop",
                    "The rule is already installed but has not taken effect. "
                    "Devices the kernel created before it was loaded keep their "
                    "old permissions until udev is told to look again.",
                ),
                check=JOYSTICK_NODES,
                command=_RELOAD_COMMAND,
            ),
            _uinput_step(_UINPUT_RELOAD),
        ),
    )


def _from_source(rule_source: str) -> Recipe:
    return Recipe(
        key="install-rule",
        notice=_notice(),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Install the access rule"),
                instruction=translate(
                    "Kasual Desktop",
                    "Running from a source checkout, so nothing has placed the "
                    "rule yet. It is the same file the packages ship, and it "
                    "grants gamepads only — never your keyboard or mouse.",
                ),
                check=JOYSTICK_NODES,
                command=f"sudo install -Dm644 {rule_source} {INSTALLED_RULE_PATH}",
            ),
            Step(
                title=translate("Kasual Desktop", "Apply the access rule"),
                instruction=translate(
                    "Kasual Desktop",
                    "A controller that is already plugged in keeps the "
                    "permissions it was created with until udev looks again.",
                ),
                check=JOYSTICK_NODES,
                command=_RELOAD_COMMAND,
            ),
            _uinput_step(_UINPUT_RELOAD),
        ),
    )


def _uinput_step(command: str) -> Step:
    """Loading the module is only half of it: one that was already loaded before
    the rule landed keeps the permissions it was created with, so the node has to
    be re-made as well."""
    return Step(
        title=translate("Kasual Desktop", "Make /dev/uinput available"),
        instruction=translate(
            "Kasual Desktop",
            "The virtual gamepad Kasual Desktop hands to your apps is built on "
            "this node. Add it to /etc/modules-load.d/uinput.conf to keep it "
            "across reboots, unless the access rule above already brings it up.",
        ),
        check=UINPUT_NODE,
        command=command,
    )


def _notice() -> str:
    return translate(
        "Kasual Desktop",
        "Kasual Desktop talks to the controller through the kernel directly, "
        "the way Steam does, rather than through the desktop session. That is "
        "what lets it reach the pad while another app is in the foreground — "
        "and it is why the device nodes have to be opened to your user.",
    )
