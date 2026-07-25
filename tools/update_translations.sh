#!/usr/bin/env bash
# Wyodrębnia napisy i18n z kodu Python, aktualizuje pliki .ts
# i kompiluje je do binarnych .qm.
#
# Użycie:
#   ./update_translations.sh          – aktualizuje wszystkie języki
#   ./update_translations.sh en       – tylko angielski
#
# Wymagania: pylupdate6, lrelease (pakiet qt6-linguist, qt6-tools lub pyqt6-dev-tools)

set -euo pipefail
cd "$(dirname "$0")"/../

LRELEASE=""
for candidate in lrelease-qt6 lrelease /usr/lib64/qt6/bin/lrelease /usr/lib/qt6/bin/lrelease; do
    if command -v "$candidate" >/dev/null 2>&1; then
        LRELEASE="$candidate"
        break
    fi
done

if [[ -z "$LRELEASE" ]]; then
    echo "Nie znaleziono lrelease. Zainstaluj: qt6-linguist (Fedora)," >&2
    echo "qt6-tools (Debian/Ubuntu) lub qt6-tools (Arch)." >&2
    exit 1
fi

LANGUAGES=("pl" "en")

if [[ $# -gt 0 ]]; then
    LANGUAGES=("$@")
fi

SRC_FILES=$(find src -name "*.py" | sort | tr '\n' ' ')

echo "── Wyodrębnianie napisów z kodu źródłowego ──────────────────────────────"
for lang in "${LANGUAGES[@]}"; do
    ts="locale/kasual_${lang}.ts"
    echo "  pylupdate6 → ${ts}"
    # shellcheck disable=SC2086
    pylupdate6 $SRC_FILES -ts "$ts"
done

echo
echo "── Kompilowanie .ts → .qm ───────────────────────────────────────────────"
for lang in "${LANGUAGES[@]}"; do
    ts="locale/kasual_${lang}.ts"
    if [[ -f "$ts" ]]; then
        echo "  $LRELEASE  → locale/kasual_${lang}.qm"
        "$LRELEASE" "$ts" -qm "locale/kasual_${lang}.qm"
    fi
done

cd -
echo
echo "Gotowe."
