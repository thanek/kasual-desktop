# Plan migracji KD na layer-shell

Branch: `layer_shell`. Cel: przebudować Kasual Desktop tak, by działał jako
nakładki **wlr-layer-shell** nad żywą sesją DE (Plasma), zamiast pełnoekranowego
okna `xdg-toplevel` walczącego o stos przez sztuczki KWin.

Walidacja wykonalności: spike (`tools/spike_layershell.py`) potwierdził, że z PyQt6
na **systemowym Qt** da się postawić powierzchnię `overlay` nad wszystkim, łącznie
z pełnoekranową treścią (KWin 6.5.2 / Qt 6.9.2). Pip-owy bundel Qt tego nie potrafi
(nie ładuje systemowego pluginu `liblayer-shell.so`) → przechodzimy na systemowe Qt.

## Model stanów (nie-destrukcyjny — wszystko to pokaż/ukryj powierzchni)

| Stan | Powierzchnie KD | Co widać |
|---|---|---|
| **DE mode** (pad off) | żadne | czyste, nietknięte DE |
| **KD home** | Desktop (`top`) | kafle KD zasłaniają DE |
| **KD home + menu** | Desktop (`top`) + Home Overlay (`overlay`) | KD zasłania DE, Home Overlay przykrywa KD |
| **W grze/apce** | żadne | gra nad nietkniętym DE |
| **W grze + menu** | Home Overlay (`overlay`) | sidebar nad żywą grą |

Dobór warstw: **Desktop = `top`** (nad panelami; ukryty w grze), **Home Overlay =
`overlay`** (nad grą i nad Desktopem — `overlay` > `top`, więc „KD home + menu"
wychodzi z modelu za darmo).

Przejścia: pad on → pokaż Desktop; pad off → ukryj wszystko (DE wraca w 100%);
start gry → ukryj Desktop; BTN_MODE → pokaż Home Overlay; z Home Overlay → ukryj
(powrót do gry) lub ukryj + pokaż Desktop (powrót do KD).

## Fazy

### Faza 0 — Fundament  ✅ GOTOWE
- [x] `main.py` + `kasual.sh`: wymuszone `QT_QPA_PLATFORM=wayland` + `QT_WAYLAND_SHELL_INTEGRATION=layer-shell`
- [x] `kasual.sh` + `test.sh`: `PYTHONNOUSERSITE=1` (odcina `~/.local` pip PyQt6 6.11 → prześwieca systemowe 6.9)
- [x] venv `--system-site-packages` (pyvenv.cfg); usunięte pip-owe PyQt6 z venv
- [x] `requirements.txt`: bez `PyQt6` i nieużywanego `pyqt6-webengine`; deps systemowe udokumentowane
- [x] doinstalowany `python3-pyqt6.qtmultimedia` (wykryte: `sound_player` używa QtMultimedia)
- [x] `src/ui/layer_shell.py`: wrapper ctypes→LayerShellQt (`make_layer_surface`, enumy `Layer`/`Anchor`/`Keyboard`, `is_available`); smoke test OK
- [x] **WALIDACJA: testy zielone na PyQt6 6.9.1 / Qt 6.9.2** — rdzeń 185 + file_browser 54 + yt 10

### Faza 1 — Pilotaż: Home Overlay jako samodzielny overlay
- [ ] `HomeOverlay` → top-level, `layer=overlay`, anchor do prawej krawędzi, `exclusive_zone=-1`
- [ ] usunąć rendering-w-surface-Desktopu i snapshot tła z Home Overlay
- [ ] `app.py::_on_btn_mode`: usunąć `capture_screen()` i taniec minimalizuj/wynieś
- [ ] walidacja na żywo: przywołać nad grą, nawigacja, powrót do gry i do KD

### Faza 2 — KD Desktop jako powierzchnia layer-shell
- [ ] `Desktop` → `layer=top`, anchors=all, pokaż/ukryj zamiast showFullScreen/minimize
- [ ] przepiąć `connected_changed` i logikę start-apki / powroty na pokaż/ukryj
- [ ] usunąć hack `enter_overlay_mode`/`exit_overlay_mode` (jeśli zbędny)

### Faza 3 — Demontaż obejść
- [ ] usunąć z `KWinWindowManager` `minimize_windows_for_pids`/`raise_windows_for_pid_exact` (jeśli martwe)
- [ ] usunąć `src/system/screen_capture.py` + kod snapshotu
- [ ] uprościć `BaseOverlay` (koniec dualnego trybu); zmigrować `ConfirmDialog`/`VolumeOverlay` na wrapper
- [ ] skonfigurować pozostałe top-level okna (po globalnym layer-shell każde okno to powierzchnia warstwy)
- [ ] aktualizacja testów/dokumentacji

### Faza 4 — Dystrybucja
- [ ] `requirements.txt` tylko czyste-pythonowe
- [ ] udokumentować deps systemowe (Debian/Ubuntu: `python3-pyqt6 python3-pyqt6.sip layer-shell-qt qt6-wayland`; Arch: `python-pyqt6 layer-shell-qt`)
- [ ] opcjonalnie `.deb`/PKGBUILD

## Ryzyka / pytania otwarte
1. PyQt6 6.9 vs 6.11 + pytest-qt — walidacja w Fazie 0.
2. Gry z wyłącznym pełnym ekranem (Steam/gamescope) mogą zachowywać się inaczej niż pełnoekranowy YouTube — przetestować na realnej grze.
3. Kruchość ctypes (zmangowane symbole, ABI QFlags/enum) — izolacja w jednym module + self-check.
4. Wiele monitorów — layer-shell jest per-output; wybór wyjścia dla KD.
5. Popupy/menu (tray, ConfirmDialog) jako powierzchnie warstwy — pozycja/rozmiar do ustalenia.
