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
_INSTALLER_CLONE = "~/widevine-installer"


def all_recipes() -> tuple[Recipe, ...]:
    return (
        _fedora_arm_ostree(), _fedora_arm(),
        _raspberrypi_arm(), _generic_arm(),
        _intel_ostree(), _intel(),
    )


def _fedora_arm_ostree() -> Recipe:
    return Recipe(
        key="fedora-arm-ostree",
        arch=("aarch64",),
        distros=("fedora",),
        traits=("ostree",),
        notice=_google_notice(),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Layer the Widevine installer"),
                instruction=translate(
                    "Kasual Desktop",
                    "Your system image is read-only, so the installer is layered "
                    "onto it instead of installed into it. It exists only after "
                    "the reboot that command asks for.",
                ),
                check=Check(CheckKind.COMMAND, "widevine-installer"),
                command="rpm-ostree install widevine-installer",
            ),
            _run_installer_step("sudo widevine-installer"),
        ),
    )


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


def _raspberrypi_arm() -> Recipe:
    return Recipe(
        key="raspberrypi-arm",
        arch=("aarch64", "armv7l"),
        distros=("raspbian", "debian"),
        traits=("raspberrypi",),
        notice=translate(
            "Kasual Desktop",
            "Kasual Desktop does not ship Widevine. Raspberry Pi OS packages "
            "Google's module itself, and installing that package is what makes "
            "DRM playback work here.",
        ),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Install the Widevine package"),
                instruction=translate(
                    "Kasual Desktop",
                    "One package is all this system needs — no download and no "
                    "unpacking by hand.",
                ),
                check=Check(CheckKind.CDM),
                command="sudo apt install libwidevinecdm0",
            ),
        ),
    )


def _generic_arm() -> Recipe:
    return Recipe(
        key="generic-arm",
        arch=("aarch64",),
        notice=_google_notice(),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Install the extraction tool"),
                instruction=translate(
                    "Kasual Desktop",
                    "The installer unpacks a squashfs image, which needs "
                    "unsquashfs — the one tool your system may not have already.",
                ),
                check=Check(CheckKind.COMMAND, "unsquashfs"),
                command="",
            ),
            Step(
                title=translate("Kasual Desktop", "Get the installer script"),
                instruction=translate(
                    "Kasual Desktop",
                    "Your distribution does not package it, so fetch it from the "
                    "Asahi Linux project. It lands in your home directory.",
                ),
                check=Check(CheckKind.PATH, f"{_INSTALLER_CLONE}/widevine-installer"),
                command=f"git clone {_ASAHI_INSTALLER_URL} {_INSTALLER_CLONE}",
            ),
            _run_installer_step(f"sudo {_INSTALLER_CLONE}/widevine-installer"),
        ),
    )


def _intel_ostree() -> Recipe:
    return Recipe(
        key="intel-ostree",
        arch=("x86_64",),
        traits=("ostree",),
        notice=_chrome_notice(),
        steps=(
            Step(
                title=translate("Kasual Desktop", "Install Google Chrome from Flathub"),
                instruction=translate(
                    "Kasual Desktop",
                    "Your system image is read-only, so take Chrome as a Flatpak. "
                    "Kasual Desktop reads the Widevine module out of it.",
                ),
                check=Check(CheckKind.CDM),
                command="flatpak install flathub com.google.Chrome",
            ),
        ),
    )


def _intel() -> Recipe:
    return Recipe(
        key="intel-chrome",
        arch=("x86_64",),
        notice=_chrome_notice(),
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
            "answers. Kasual Desktop finds the module right away; the re-login "
            "the installer asks for is only for browsers.",
        ),
        check=Check(CheckKind.CDM),
        command=command,
    )


def _chrome_notice() -> str:
    return translate(
        "Kasual Desktop",
        "Kasual Desktop does not ship Widevine. Google Chrome carries it, and "
        "installing Chrome is what makes DRM playback work here.",
    )


def _google_notice() -> str:
    return translate(
        "Kasual Desktop",
        "Kasual Desktop does not ship Widevine. The installer downloads it from "
        "Google and shows you Google's licence, which you accept yourself.",
    )
