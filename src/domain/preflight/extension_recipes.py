"""The way out of each state the helper extension can be found in.

A recipe's strings are translated as it is built, which must therefore happen
after the composition root installs the translator.
"""

from domain.preflight.extension import (
    ABSENT, DISABLED, ENABLE, LOG_OUT, UNLOADED,
)
from domain.setup.plan import GOAL_REACHED, Recipe, Remedy, Step
from domain.shared.i18n import translate


def all_recipes(uuid: str) -> tuple[Recipe, ...]:
    return (_absent(uuid), _unloaded(uuid), _disabled(uuid))


def _disabled(uuid: str) -> Recipe:
    return Recipe(
        key="enable",
        traits=(DISABLED,),
        notice=_notice(),
        remedies=(Remedy(ENABLE, translate("Kasual Desktop", "Enable")),),
        steps=(_enable_step(uuid),),
    )


def _absent(uuid: str) -> Recipe:
    return Recipe(
        key="install",
        traits=(ABSENT,),
        notice=_notice(),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Install Kasual Desktop's package"),
                instruction=translate(
                    "Kasual Desktop",
                    "The extension ships inside it. A source checkout run in "
                    "place has never put it where GNOME Shell looks.",
                ),
                check=GOAL_REACHED,
            ),
            _enable_step(uuid),
        ),
    )


def _unloaded(uuid: str) -> Recipe:
    return Recipe(
        key="relogin",
        traits=(UNLOADED,),
        notice=_notice(),
        remedies=(Remedy(LOG_OUT, translate("Kasual Desktop", "Log out")),),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Start a fresh session"),
                instruction=translate(
                    "Kasual Desktop",
                    "The extension is installed, but GNOME Shell built its list "
                    "of extensions when you logged in and cannot be made to look "
                    "again. Log out and back in.",
                ),
                check=GOAL_REACHED,
            ),
            _enable_step(uuid),
        ),
    )


def _enable_step(uuid: str) -> Step:
    return Step(
        title=translate("Kasual Desktop", "Enable the extension"),
        instruction=translate(
            "Kasual Desktop",
            "GNOME keeps extensions off until they are turned on, once per user.",
        ),
        check=GOAL_REACHED,
        command=f"gnome-extensions enable {uuid}",
    )


def _notice() -> str:
    return translate(
        "Kasual Desktop",
        "The extension is part of Kasual Desktop, not a third-party add-on: it "
        "is what carries out the window operations Mutter offers no protocol for.",
    )
