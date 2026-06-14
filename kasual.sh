#!/bin/bash

cd `dirname $0`
if [ ! -f venv/bin/activate ]; then
    echo "No venv directory. Run ./install.sh first" >&2
    exit 1
fi
source venv/bin/activate
# Use the SYSTEM PyQt6 (Qt 6.9) for layer-shell, not ~/.local pip PyQt6 (Qt 6.11).
export PYTHONNOUSERSITE=1
export QT_QPA_PLATFORM=wayland
export QT_WAYLAND_SHELL_INTEGRATION=layer-shell
python3 src/main.py
cd -
