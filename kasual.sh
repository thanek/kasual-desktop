#!/bin/bash
# Dev launcher: runs Kasual Desktop straight from the repo against the SYSTEM
# PyQt6 (distro python3-pyqt6, version-locked to the layer-shell plugin). No
# venv — install the system deps once (see install.sh / README). The installed
# package ships an equivalent /usr/bin/kasual-desktop wrapper.
cd "$(dirname "$0")"

# --provisioning: re-trigger first-run onboarding by removing the marker, so the
# next launch shows the app picker again.
if [ "$1" = "--provisioning" ]; then
    rm -f "${KD_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/kasual-desktop}/.provisioned"
    echo "Removed provisioning marker — onboarding will run on next launch."
fi

# Force the SYSTEM PyQt6, which is the one version-locked to the system's
# layer-shell plugin. Two things can substitute a pip-installed PyQt6 (a newer Qt
# that ships no layer-shell integration, leaving Kasual unable to place its own
# surfaces): ~/.local, hidden by PYTHONNOUSERSITE, and an activated virtualenv,
# which wins through PATH — so the interpreter is named outright rather than
# looked up. The shell integration itself is chosen per compositor by src/main.py.
export PYTHONNOUSERSITE=1
unset VIRTUAL_ENV VIRTUAL_ENV_PROMPT
export QT_QPA_PLATFORM=wayland

PYTHON=/usr/bin/python3
[ -x "$PYTHON" ] || PYTHON=python3
exec "$PYTHON" src/main.py
