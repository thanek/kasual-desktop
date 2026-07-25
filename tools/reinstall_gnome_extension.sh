#!/usr/bin/env bash
set -euo pipefail

UUID=kasual-helper@consoledesktop.org
TARGET=~/.local/share/gnome-shell/extensions/"$UUID"

rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"/gnome-shell-disable-extensions

mkdir -p "$TARGET"
cp "$(dirname "$0")"/../packaging/gnome-extension/"$UUID"/* "$TARGET"/

gsettings set org.gnome.shell disable-user-extensions false

if gnome-extensions enable "$UUID" 2>/dev/null; then
    gnome-extensions info "$UUID"
else
    echo "Shell tej sesji nie zna jeszcze $UUID." >&2
    echo "Wyloguj się i zaloguj ponownie, potem uruchom skrypt jeszcze raz." >&2
    exit 1
fi
