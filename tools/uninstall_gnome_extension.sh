#!/usr/bin/env bash
set -euo pipefail

UUID=kasual-helper@consoledesktop.org
TARGET="${XDG_DATA_HOME:-$HOME/.local/share}"/gnome-shell/extensions/"$UUID"
SYSTEM_TARGET=/usr/share/gnome-shell/extensions/"$UUID"

# Disabling first lets the extension tear down its hooks in the running Shell.
gnome-extensions disable "$UUID" 2>/dev/null || true

# `uninstall` also drops the UUID from the Shell's list; it fails when this
# session never loaded the extension, hence the plain removal afterwards.
gnome-extensions uninstall "$UUID" 2>/dev/null || true
rm -rf "$TARGET"

echo "Rozszerzenie $UUID wyłączone i usunięte z $TARGET."

if [ -d "$SYSTEM_TARGET" ]; then
    echo "Kopia systemowa w $SYSTEM_TARGET pochodzi z pakietu Kasual Desktop;" >&2
    echo "usuń ją menedżerem pakietów." >&2
fi
