#!/bin/bash
# Launcher for the bundled File Browser app. Runs against the SYSTEM PyQt6
# (distro python3-pyqt6) — no venv. Works both from the repo (dev) and when
# installed under /usr/share/kasual-desktop (relative cd).
cd "$(dirname "$0")"
exec python3 src/file_browser.py "$@"
