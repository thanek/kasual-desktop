#!/bin/bash
# Launcher for the bundled YouTube app. Runs against the SYSTEM PyQt6
# (distro python3-pyqt6 + .qtwebengine) — no venv. Works both from the repo
# (dev) and when installed under /usr/share/kasual-desktop (relative cd).
cd "$(dirname "$0")"
exec python3 src/yt.py "$@"
