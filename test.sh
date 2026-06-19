#!/bin/bash
# Test runner. Uses the SYSTEM Python + PyQt6 (no venv) — install the dev deps
# with ./install.sh (pulls python3-pytest / python3-pytest-qt too).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Hide ~/.local so the SYSTEM PyQt6 (Qt 6.9) is used — same as the runtime
# launcher — not a pip PyQt6 there. The test stack (pytest/pytest-qt/subtests)
# must be installed system-wide (./install.sh handles it).
export PYTHONNOUSERSITE=1
overall=0

echo "=== Kasual Desktop (core) ==="
python3 -m pytest "$@" || overall=1

for app_dir in "$SCRIPT_DIR/apps"/*/; do
    [ -d "$app_dir/tests" ] || continue
    app_name=$(basename "$app_dir")
    echo ""
    echo "=== $app_name ==="
    (cd "$app_dir" && python3 -m pytest tests/ "$@") || overall=1
done

exit $overall
