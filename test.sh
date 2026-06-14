#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
if [ ! -f venv/bin/activate ]; then
    echo "No venv directory. Run ./install.sh first" >&2
    exit 1
fi
source venv/bin/activate
# Use the SYSTEM PyQt6 (Qt 6.9), not ~/.local pip PyQt6 (Qt 6.11).
export PYTHONNOUSERSITE=1
overall=0

echo "=== Kasual Desktop (core) ==="
pytest "$@" || overall=1

for app_dir in "$SCRIPT_DIR/apps"/*/; do
    [ -d "$app_dir/tests" ] || continue
    app_name=$(basename "$app_dir")
    echo ""
    echo "=== $app_name ==="
    (cd "$app_dir" && pytest tests/ "$@") || overall=1
done

exit $overall
