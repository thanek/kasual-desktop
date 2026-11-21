"""The way out of each state the helper extension can be found in.

A recipe's strings are translated as it is built, which must therefore happen
after the composition root installs the translator.
"""

from domain.preflight.extension import (
    ABSENT, DISABLED, ENABLE, FRESH_SESSION, INSTALLED, LOG_OUT, UNLOADED,
    stage_check,
)
from domain.setup.plan import GOAL_REACHED, Recipe, Remedy, Step
from domain.shared.i18n import translate


def all_recipes(uuid: str, desktop: str) -> tuple[Recipe, ...]:
    return (
        _absent(uuid, desktop),
        _unloaded(uuid, desktop),
        _disabled(uuid, desktop),
    )


def _absent(uuid: str, desktop: str) -> Recipe:
    return _recipe("install", ABSENT, uuid, desktop)


def _unloaded(uuid: str, desktop: str) -> Recipe:
    return _recipe(
        "relogin", UNLOADED, uuid, desktop,
        Remedy(LOG_OUT, translate("Kasual Desktop", "Log out")))


def _disabled(uuid: str, desktop: str) -> Recipe:
    return _recipe(
        "enable", DISABLED, uuid, desktop,
        Remedy(ENABLE, translate("Kasual Desktop", "Enable")))


def _recipe(
    key: str, trait: str, uuid: str, desktop: str, *remedies: Remedy
) -> Recipe:
    return Recipe(
        key=key,
        traits=(trait,),
        notice=_notice(desktop),
        remedies=remedies,
        steps=_path(uuid),
        timeline=True,
    )


def _path(uuid: str) -> tuple[Step, ...]:
    return (
        Step(
            title=translate("Kasual Desktop", "Installing the extension"),
            instruction=translate(
                "Kasual Desktop",
                "The extension ships inside Kasual Desktop's package. A source "
                "checkout run in place has never put it where GNOME Shell looks. "
                "You need to install the extension, e.g. with the "
                "./tools/reinstall_gnome_extension.sh script.",
            ),
            check=stage_check(INSTALLED),
        ),
        Step(
            title=translate("Kasual Desktop", "Logging out"),
            instruction=translate(
                "Kasual Desktop",
                "The extension is already on the system, but the session needs "
                "reloading. To do that, log out and log back in.",
            ),
            check=stage_check(FRESH_SESSION),
        ),
        Step(
            title=translate("Kasual Desktop", "Enabling the extension"),
            instruction=translate(
                "Kasual Desktop",
                "The extension is already on the system, but it is not enabled "
                "yet. You can enable it with the command, or by clicking Enable.",
            ),
            check=GOAL_REACHED,
            command=f"gnome-extensions enable {uuid}",
        ),
    )


def _notice(desktop: str) -> str:
    return translate(
        "Kasual Desktop",
        "Kasual Desktop on {0} needs the Kasual Helper extension running. This "
        "window walks you through installing it on your desktop, step by step.",
    ).format(desktop)
