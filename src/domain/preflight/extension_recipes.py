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


def all_recipes(uuid: str) -> tuple[Recipe, ...]:
    return (_absent(uuid), _unloaded(uuid), _disabled(uuid))


def _absent(uuid: str) -> Recipe:
    return _recipe("install", ABSENT, uuid)


def _unloaded(uuid: str) -> Recipe:
    return _recipe(
        "relogin", UNLOADED, uuid,
        Remedy(LOG_OUT, translate("Kasual Desktop", "Log out")))


def _disabled(uuid: str) -> Recipe:
    return _recipe(
        "enable", DISABLED, uuid,
        Remedy(ENABLE, translate("Kasual Desktop", "Enable")))


def _recipe(key: str, trait: str, uuid: str, *remedies: Remedy) -> Recipe:
    return Recipe(
        key=key,
        traits=(trait,),
        notice=_notice(),
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
                "checkout run in place has never put it where GNOME Shell looks.",
            ),
            check=stage_check(INSTALLED),
        ),
        Step(
            title=translate("Kasual Desktop", "Logging out"),
            instruction=translate(
                "Kasual Desktop",
                "GNOME Shell builds its list of extensions when you log in and "
                "cannot be made to look again, so one installed since then waits "
                "for the next session. Log out and back in.",
            ),
            check=stage_check(FRESH_SESSION),
        ),
        Step(
            title=translate("Kasual Desktop", "Enabling the extension"),
            instruction=translate(
                "Kasual Desktop",
                "GNOME keeps extensions off until they are turned on, once per user.",
            ),
            check=GOAL_REACHED,
            command=f"gnome-extensions enable {uuid}",
        ),
        Step(
            title=translate("Kasual Desktop", "Starting Kasual Desktop"),
            instruction=translate(
                "Kasual Desktop",
                "Kasual Desktop starts on its own as soon as the extension answers.",
            ),
            check=GOAL_REACHED,
        ),
    )


def _notice() -> str:
    return translate(
        "Kasual Desktop",
        "The extension is part of Kasual Desktop, not a third-party add-on: it "
        "is what carries out the window operations Mutter offers no protocol for.",
    )
