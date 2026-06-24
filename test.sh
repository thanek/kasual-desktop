#!/bin/bash
# Test runner. On Linux uses the SYSTEM Python + PyQt6 (no venv) — install the
# dev deps with ./install.sh (pulls python3-pytest / python3-pytest-qt too).
# On macOS uses ./venv if present (pip-installed PyQt6 + pytest-qt).
#
# OS-specific tests are skipped via skipif markers in the test files:
#   - Linux-only:  skipif(sys.platform != "linux")
#   - Windows-only: skipif(sys.platform != "win32")
# So on macOS both families are skipped automatically; only cross-platform
# tests run.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Pick the Python interpreter: prefer the project venv (macOS dev), fall back
# to system python3 (Linux — distro PyQt6).
if [ -x "$SCRIPT_DIR/venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python3"
else
    PYTHON="python3"
    # Hide ~/.local so the SYSTEM PyQt6 (Qt 6.9) is used — same as the runtime
    # launcher — not a pip PyQt6 there. The test stack (pytest/pytest-qt/subtests)
    # must be installed system-wide (./install.sh handles it).
    export PYTHONNOUSERSITE=1
fi

overall=0

echo "=== Kasual Desktop (core) — $(uname -s) ==="
"$PYTHON" -m pytest "$@" || overall=1

for app_dir in "$SCRIPT_DIR/apps"/*/; do
    [ -d "$app_dir/tests" ] || continue
    app_name=$(basename "$app_dir")
    echo ""
    echo "=== $app_name ==="
    (cd "$app_dir" && "$PYTHON" -m pytest tests/ "$@") || overall=1
done

exit $overall
