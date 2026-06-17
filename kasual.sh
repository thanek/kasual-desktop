#!/bin/bash

cd `dirname $0`
if [ ! -f venv/bin/activate ]; then
    echo "No venv directory. Run ./install.sh first" >&2
    exit 1
fi
source venv/bin/activate

# --provisioning: re-trigger first-run onboarding by removing the marker, so the
# next launch shows the app picker again.
if [ "$1" = "--provisioning" ]; then
    rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/kasual-desktop/.provisioned"
    echo "Removed provisioning marker — onboarding will run on next launch."
fi

# Use the SYSTEM PyQt6 (Qt 6.9) for layer-shell, not ~/.local pip PyQt6 (Qt 6.11).
export PYTHONNOUSERSITE=1
export QT_QPA_PLATFORM=wayland
export QT_WAYLAND_SHELL_INTEGRATION=layer-shell
python3 src/main.py
cd -
