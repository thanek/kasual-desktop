"""The two ways to a HUD over a game a launcher started, safest first.

The order is the point, and the reason is not in the steps: MangoHud runs its own
sampling threads inside every process it attaches to, and one that faults takes
that application down — Kasual Desktop's own bundled apps have been killed this
way. So handing the whole session to it comes second, for all that it is the
permanent fix, and letting Kasual Desktop start the launcher comes first.

A recipe's strings are translated as it is built, which must therefore happen
after the composition root installs the translator.
"""

from domain.preflight.hud import NO_SESSION_HUD
from domain.setup.plan import GOAL_REACHED, PATH, Check, Recipe, Step
from domain.shared.i18n import translate

CONFIG_FILE = "~/.config/environment.d/50-kasual-mangohud.conf"

_WRITTEN = Check(PATH, CONFIG_FILE)


def all_recipes() -> tuple[Recipe, ...]:
    return (
        Recipe(
            key="mangohud-reaches-games",
            traits=(NO_SESSION_HUD,),
            notice=_notice(),
            steps=(_launcher_step(), _session_step()),
        ),
    )


def _launcher_step() -> Step:
    return Step(
        title=translate(
            "Kasual Desktop", "Let Kasual Desktop start your launcher"),
        instruction=translate(
            "Kasual Desktop",
            "Close Steam (or Heroic, or Lutris) and start it from its tile, or pick "
            "a game tile with the launcher closed. A launcher Kasual Desktop starts "
            "is given the HUD, and hands it to every game it goes on to start — "
            "while one that was already running starts them from its own "
            "environment, without it. Nothing to install, nothing to undo.",
        ),
        check=GOAL_REACHED,
    )


def _session_step() -> Step:
    return Step(
        title=translate(
            "Kasual Desktop", "Or hand the whole session to MangoHud"),
        instruction=translate(
            "Kasual Desktop",
            "Files in ~/.config/environment.d hold what a desktop session starts "
            "everything else with, so this reaches every game whoever starts it — "
            "and every other Vulkan application too, which is the cost. MangoHud "
            "runs inside each process it attaches to, and a fault in it takes that "
            "application down. Log out and back in afterwards: a session's "
            "environment is built when it starts.",
        ),
        check=_WRITTEN,
        command=("mkdir -p ~/.config/environment.d && "
                 f"echo MANGOHUD=1 > {CONFIG_FILE}"),
    )


def _notice() -> str:
    return translate(
        "Kasual Desktop",
        "Either way this leaves the HUD loaded, not shown: whether it is on screen "
        "stays MangoHud's own setting, and the Home Menu's toggle over a game.",
    )
