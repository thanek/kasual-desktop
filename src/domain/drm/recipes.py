"""The known paths to a working Widevine CDM, one recipe per platform.

Order matters: the first match wins, so a derivative that needs different
handling belongs before the family it reports in ``ID_LIKE`` (Pop!_OS reports
``ubuntu debian``, so a Debian recipe already covers it and it earns an entry
only when it genuinely differs).

A recipe's strings are translated as it is built, which must therefore happen
after the composition root installs the translator.
"""

from domain.drm.plan import Check, CheckKind, Recipe, Step
from domain.shared.i18n import translate

_ASAHI_INSTALLER_URL = "https://github.com/AsahiLinux/widevine-installer"


def all_recipes() -> tuple[Recipe, ...]:
    return (_fedora_arm(), _generic_arm(), _intel())


def _fedora_arm() -> Recipe:
    return Recipe(
        key="fedora-arm",
        arch=("aarch64",),
        distros=("fedora",),
        notice=_google_notice(),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Install the Widevine installer"),
                instruction=translate(
                    "Kasual Desktop",
                    "Fedora packages the installer script itself. Install it, then "
                    "come back here.",
                ),
                check=Check(CheckKind.COMMAND, "widevine-installer"),
                command="sudo dnf install widevine-installer",
            ),
            _run_installer_step("sudo widevine-installer"),
        ),
    )


def _generic_arm() -> Recipe:
    return Recipe(
        key="generic-arm",
        arch=("aarch64",),
        notice=_google_notice(),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Install the extraction tools"),
                instruction=translate(
                    "Kasual Desktop",
                    "The installer unpacks a squashfs image and patches the module, "
                    "so it needs curl, unsquashfs and Python.",
                ),
                check=Check(CheckKind.COMMAND, "unsquashfs"),
                command="",
            ),
            Step(
                title=translate("Kasual Desktop", "Get the installer script"),
                instruction=translate(
                    "Kasual Desktop",
                    "Your distribution does not package it, so fetch it from the "
                    "Asahi Linux project.",
                ),
                check=Check(CheckKind.COMMAND, "widevine-installer"),
                command=f"git clone {_ASAHI_INSTALLER_URL}",
            ),
            _run_installer_step("sudo ./widevine-installer/widevine-installer"),
        ),
    )


def _intel() -> Recipe:
    return Recipe(
        key="intel-chrome",
        arch=("x86_64",),
        notice=translate(
            "Kasual Desktop",
            "Kasual Desktop does not ship Widevine. Google Chrome carries it, and "
            "installing Chrome is what makes DRM playback work here.",
        ),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Install Google Chrome"),
                instruction=translate(
                    "Kasual Desktop",
                    "Install Chrome with your distribution's package manager. Its "
                    "bundled Widevine module is picked up automatically — a "
                    "Chromium build that fetches Widevine works too.",
                ),
                check=Check(CheckKind.CDM),
                command="",
            ),
        ),
    )


def _run_installer_step(command: str) -> Step:
    return Step(
        title=translate("Kasual Desktop", "Run the installer"),
        instruction=translate(
            "Kasual Desktop",
            "It downloads the module from Google, shows you the licence and asks "
            "you to accept it. Run it in a terminal — it needs root and your "
            "answers.",
        ),
        check=Check(CheckKind.CDM),
        command=command,
    )


def _google_notice() -> str:
    return translate(
        "Kasual Desktop",
        "Kasual Desktop does not ship Widevine. The installer downloads it from "
        "Google and shows you Google's licence, which you accept yourself.",
    )
