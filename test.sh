#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
source venv/bin/activate
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
