#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

# Per README: the venv MUST be created with --system-site-packages so the SYSTEM
# PyQt6 (distro python3-pyqt6, version-locked to the layer-shell plugin) shows
# through. pip's bundled Qt cannot load KDE's layer-shell integration plugin.
if [ ! -f venv/bin/activate ]; then
    echo "==> Creating venv (--system-site-packages)"
    python3 -m venv --system-site-packages venv
else
    echo "==> venv already exists – no need to create one"
fi

source venv/bin/activate

# Match the runtime of kasual.sh / test.sh, which set PYTHONNOUSERSITE=1 to hide
# ~/.local (so the SYSTEM PyQt6 is used, not pip's). Installing under the same
# flag means pip ignores ~/.local too — the pure-Python deps (pytest, qtawesome,
# pytest-qt) land IN the venv instead of being skipped as "already satisfied"
# from ~/.local and then vanishing at runtime. evdev / python-xlib / PyQt6 stay
# satisfied by the system site-packages, which --system-site-packages still sees.
export PYTHONNOUSERSITE=1

echo "==> Installing dependencies (requirements.txt)"
pip install -r requirements.txt

for req in apps/*/requirements.txt; do
    [ -f "$req" ] || continue
    echo "==> Installing dependencies for $req"
    pip install -r "$req"
done

echo "==> Done. Run: ./kasual.sh"
