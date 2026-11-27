#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"/..

readonly EXTENSION_ID=kasual-pad@consoledesktop.org
readonly FIREFOX_APP_ID="{ec8030f7-c20a-464f-9b0e-13a3a9e97384}"
readonly SOURCE=packaging/firefox-extension/"$EXTENSION_ID"
readonly TARGET=/usr/share/mozilla/extensions/"$FIREFOX_APP_ID"/"$EXTENSION_ID"

make --silent firefox-extension
sudo mkdir -p "$TARGET"
sudo rsync -a --delete --chown=root:root --chmod=D755,F644 --exclude='README.md' "$SOURCE"/ "$TARGET"/

echo "Rozszerzenie $EXTENSION_ID zainstalowane w $TARGET."

if pgrep -f -- "--name kasual-vod" >/dev/null; then
    echo "Kiosk VOD działa i ma starą wersję: zamknij go i uruchom kafel ponownie." >&2
fi
