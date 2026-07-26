#!/bin/bash
# Dev setup: install the SYSTEM packages Kasual Desktop runs against. There is no
# venv — Kasual must use the distro PyQt6 (version-locked to KDE's layer-shell
# plugin; pip's bundled Qt cannot load it). The .deb/.rpm declare these same deps
# (see nfpm.yaml); this script just sets up a from-repo dev checkout.
set -euo pipefail

DEB_DEPS=(
    python3 python3-pyqt6 python3-pyqt6.sip python3-pyqt6.qtmultimedia
    python3-pyqt6.qtwebengine python3-qtawesome python3-evdev python3-xlib
    layer-shell-qt qt6-wayland brightnessctl
)
# Dev-only (not shipped in the package): the test stack.
DEB_DEV_DEPS=(python3-pytest python3-pytestqt python3-pytest-subtests)

RPM_DEPS=(
    python3 python3-pyqt6 python3-pyqt6-webengine python3-QtAwesome
    python3-evdev python3-xlib layer-shell-qt qt6-qtwayland brightnessctl
)
RPM_DEV_DEPS=(python3-pytest python3-pytest-qt python3-pytest-subtests)

ARCH_DEPS=(
    python python-pyqt6 python-pyqt6-webengine python-qtawesome
    python-evdev python-xlib layer-shell-qt qt6-wayland brightnessctl
)
ARCH_DEV_DEPS=(python-pytest python-pytest-qt python-pytest-subtests)

if command -v apt-get >/dev/null 2>&1; then
    echo "==> Installing system dependencies (apt)"
    sudo apt-get update -q
    sudo apt-get install -y --no-install-recommends "${DEB_DEPS[@]}" "${DEB_DEV_DEPS[@]}"
elif command -v dnf >/dev/null 2>&1; then
    echo "==> Installing system dependencies (dnf)"
    sudo dnf install -y "${RPM_DEPS[@]}" "${RPM_DEV_DEPS[@]}"
elif command -v pacman >/dev/null 2>&1; then
    echo "==> Installing system dependencies (pacman)"
    sudo pacman -S --needed "${ARCH_DEPS[@]}" "${ARCH_DEV_DEPS[@]}"
else
    echo "Unsupported package manager. Install these manually:" >&2
    printf '  %s\n' "${DEB_DEPS[@]}" >&2
    exit 1
fi

EXT_UUID=kasual-helper@consoledesktop.org
if [[ "${XDG_CURRENT_DESKTOP:-}" == *[Gg][Nn][Oo][Mm][Ee]* ]]; then
    # Mutter has no wlr-layer-shell and no window-list protocol; without this
    # extension Kasual starts on GNOME but cannot switch or overlay windows.
    EXT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$EXT_UUID"
    echo "==> Installing the GNOME Shell helper extension into $EXT_DIR"
    mkdir -p "$EXT_DIR"
    cp "$(dirname "$0")/packaging/gnome-extension/$EXT_UUID"/* "$EXT_DIR/"
    if ! gnome-extensions enable "$EXT_UUID" 2>/dev/null; then
        echo "    LOG OUT and back in, then: gnome-extensions enable $EXT_UUID"
    fi
fi

echo "==> Done. Run: ./kasual.sh"
