#!/bin/bash
# Dev launcher: runs Kasual Desktop straight from the repo against the SYSTEM
# PyQt6 (distro python3-pyqt6, version-locked to the layer-shell plugin). No
# venv — install the system deps once (see install.sh / README). The installed
# package ships an equivalent /usr/bin/kasual-desktop wrapper.
cd "$(dirname "$0")"

# --provisioning: re-trigger first-run onboarding by removing the marker, so the
# next launch shows the app picker again.
if [ "$1" = "--provisioning" ]; then
    rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/kasual-desktop/.provisioned"
    echo "Removed provisioning marker — onboarding will run on next launch."
fi

# Force the SYSTEM PyQt6 (Qt 6.9, locked to the layer-shell plugin) by hiding
# ~/.local — a pip-installed PyQt6 there (newer Qt) ships no layer-shell
# integration and makes the wayland platform plugin fail to load.
export PYTHONNOUSERSITE=1
export QT_QPA_PLATFORM=wayland
export QT_WAYLAND_SHELL_INTEGRATION=layer-shell
exec python3 src/main.py
