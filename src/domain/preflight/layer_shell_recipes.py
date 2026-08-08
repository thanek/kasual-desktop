"""The ways to a working LayerShellQt, one recipe per kind of system.

Order matters: the first match wins. What separates them is whether the
distribution has a Qt 6 build to install at all — Debian, Ubuntu and Pop!_OS
package `layer-shell-qt` for Qt 5 only, so there the way through is to build it —
and, where it does, which package manager installs it.

Every recipe ends by restarting Kasual Desktop: Qt binds its shell integration
when the application is created, so nothing installed now reaches this process.

A recipe's strings are translated as it is built, which must therefore happen
after the composition root installs the translator.
"""

from domain.preflight.layer_shell import NO_LIBRARY, NO_PLUGIN
from domain.setup.plan import GOAL_REACHED, Recipe, Step
from domain.shared.i18n import translate

UPSTREAM = "https://invent.kde.org/plasma/layer-shell-qt"

PACKAGE = "layer-shell-qt"

_QT5_ONLY_DISTROS = ("debian", "ubuntu", "pop", "raspbian", "linuxmint")

# The package is spelled the same everywhere; only the manager differs.
_INSTALL_COMMANDS = (
    (("fedora", "rhel", "centos"), f"sudo dnf install {PACKAGE}"),
    (("arch", "manjaro", "endeavouros"), f"sudo pacman -S {PACKAGE}"),
    ((), ""),   # anything else: named, not commanded
)


def all_recipes() -> tuple[Recipe, ...]:
    """Source-build first — a Debian-family machine matches an install recipe too,
    and installing its Qt 5 package would leave this exactly where it started."""
    return (_build_from_source(), *_install_recipes())


def _build_from_source() -> Recipe:
    return Recipe(
        key="build-layer-shell-qt",
        traits=(NO_PLUGIN,),
        distros=_QT5_ONLY_DISTROS,
        notice=_notice(),
        steps=(
            Step(
                title=translate(
                    "Kasual Desktop", "Build LayerShellQt against Qt 6"),
                instruction=translate(
                    "Kasual Desktop",
                    "This distribution packages layer-shell-qt for Qt 5 only, and "
                    "the plugin has to match the Qt that PyQt6 runs on. Build the "
                    "5.27 series with -DQT_MAJOR_VERSION=6 for Qt 6.4; the 6.x "
                    "series needs Qt 6.6 or newer. The soname is no guide — it "
                    "tracks LayerShellQt's own version, not Qt's.",
                ),
                check=GOAL_REACHED,
                command=f"git clone {UPSTREAM}",
            ),
            _restart_step(),
        ),
    )


def _install_recipes() -> tuple[Recipe, ...]:
    """The same package, reached by whichever manager the machine has, for each of
    the two ways it can be half-there."""
    return tuple(
        Recipe(
            key=f"install-{trait}-{'-'.join(distros) or 'other'}",
            traits=(trait,),
            distros=distros,
            notice=_notice(),
            steps=(
                Step(
                    title=translate(
                        "Kasual Desktop", "Install LayerShellQt for Qt 6"),
                    instruction=instruction,
                    check=GOAL_REACHED,
                    command=command,
                ),
                _restart_step(),
            ),
        )
        for trait, instruction in (
            (NO_PLUGIN, _missing_plugin_instruction()),
            (NO_LIBRARY, _missing_library_instruction()),
        )
        for distros, command in _INSTALL_COMMANDS
    )


def _missing_plugin_instruction() -> str:
    return translate(
        "Kasual Desktop",
        "The package is called layer-shell-qt. It must be the Qt 6 build: the "
        "shell-integration plugin is version-locked to the Qt that PyQt6 runs on, "
        "and a Qt 5 one is invisible to this process.",
    )


def _missing_library_instruction() -> str:
    return translate(
        "Kasual Desktop",
        "Qt's side of the integration is already installed; what is missing is "
        "libLayerShellQtInterface, which ships in the same layer-shell-qt package.",
    )


def _restart_step() -> Step:
    return Step(
        title=translate("Kasual Desktop", "Restart Kasual Desktop"),
        instruction=translate(
            "Kasual Desktop",
            "Qt chooses its shell integration once, when the application starts, "
            "so this session keeps running without it however the installation "
            "goes.",
        ),
        check=GOAL_REACHED,
    )


def _notice() -> str:
    return translate(
        "Kasual Desktop",
        "This affects every layer-shell compositor Kasual Desktop supports — "
        "KWin, Sway, Hyprland, cosmic-comp, labwc and wayfire — not just this "
        "one. GNOME is the exception: there the bundled Shell extension does the "
        "same job.",
    )
