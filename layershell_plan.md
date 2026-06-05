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

### Faza 1 — Pilotaż: Home Overlay jako samodzielny overlay  ✅ GOTOWE (zwalidowane na żywo)
- [x] `HomeOverlay` → top-level, `layer=OVERLAY`, `anchors=ALL` (pełnoekranowy backdrop, karta wyrównana do prawej w layoucie), `exclusive_zone=-1`, `keyboard=ON_DEMAND`; usunięty tryb child + chrome-hide
- [x] usunięty snapshot tła z Home Overlay (paintEvent = półprzezroczysty dim ~130, żywa treść prześwieca)
- [x] `app.py::_on_btn_mode`: usunięty `capture_screen()`, taniec minimalizuj/wynieś i parentowanie; „Powrót do pulpitu" → `_return_to_desktop` (bezpiecznik: minimalizuje grę + raise, dopóki Desktop=`top` nie jest pewny nad exclusive-fullscreen)
- [x] (wciągnięte z Fazy 2, bo integracja layer-shell jest globalna) minimalna konfiguracja `Desktop` jako `layer=TOP`, `anchors=ALL` — by renderował się pełnoekranowo
- [x] testy zielone (185+54+10) + smoke start prawdziwej aplikacji pod layer-shell bez wyjątków (Desktop wstał jako powierzchnia `top`)
- [x] **walidacja na żywo (user):** Home Overlay nad grą OK, nawigacja padem OK, powrót do gry/pulpitu OK, **nad exclusive-fullscreen grą OK** (rozstrzyga open question #2: Desktop=`top` staje nad wyłącznym pełnym ekranem)
- ⚠️ znany bug (→ Faza 3): `ConfirmDialog`/`VolumeOverlay` (via `BaseOverlay`) nie są jeszcze powierzchniami layer-shell, więc nie wychodzą na wierzch — zniknie po migracji `BaseOverlay`

### Faza 2 — KD Desktop jako powierzchnia layer-shell  ✅ GOTOWE (zwalidowane na żywo, z known-issue)
- [x] `Desktop` jako powierzchnia `layer=TOP` (zrobione w Fazie 1); show=`showFullScreen`/hide=`hide` mapują się na mapowanie powierzchni — `connected_changed`/`pause`/`resume`/`_reactivate_desktop` działają bez zmian
- [x] **ścieżka launch ukrywa teraz Desktop** (`_on_tile_activated`) — spójność z `restore_app`; bez tego aplikacja *okienkowa* zostawała pod KD (`top` jest pod oknami zwykłymi tylko dla nie-fullscreen; patrz niżej)
- [x] `_on_app_launch_failed` → `_reactivate_desktop()` (pokazuje Desktop pod dialog błędu, bo launch go ukrył)
- USTALONE: warstwa `top` jest **pod** oknem exclusive-fullscreen (a `overlay` nad) — dlatego **bezpiecznik z minimalizacją w `_return_to_desktop` ZOSTAJE** (to on niezawodnie odsłania KD nad pełnoekranową grą)
- [x] **walidacja na żywo (user):** launch gry pełnoekranowej OK; powrót do gry/pulpitu OK; rozłączenie/podłączenie pada OK. Okna `dyn`/nie-fullscreen (np. Konsole) → przeniesienie do „starego" DE, zgodne z założeniem (KD wspiera tylko aplikacje fullscreen)
- DESIGN: KD wspiera wyłącznie aplikacje pełnoekranowe; nie-fullscreen traktowane jako „stary tryb" DE
- ⚠️ KNOWN-ISSUE (przyszła poprawka, nie priorytet): przy starcie aplikacji Desktop ukrywa się od razu, więc widać pulpit KDE przez kilka sekund do splash-screena (np. Steam Big Picture). Możliwe rozwiązanie: ukrywać KD dopiero gdy pojawi się okno aplikacji (sygnał `windows_updated`)
- przeniesione do Fazy 3: usunięcie `enter_overlay_mode`/`exit_overlay_mode` (wciąż używane przez `BaseOverlay`) oraz martwych `minimize`/`raise`

### Faza 3 — Demontaż obejść  ✅ GOTOWE (zwalidowane na żywo)
- [x] `BaseOverlay` przepisany na samodzielną powierzchnię `layer=OVERLAY` (koniec dualnego trybu child/top-level); `ConfirmDialog`/`VolumeOverlay`/`InfoDialog` migrują przez dziedziczenie → **naprawia bug z dialogami nie na wierzchu**
- [x] usunięty `src/system/screen_capture.py` (martwy po Fazie 1)
- [x] usunięte `enter_overlay_mode`/`exit_overlay_mode` + `_overlay_depth` z `Desktop` (overlaye i tak zasłaniają chrome z wyższej warstwy)
- [x] usunięte wywołania `self._notify_closed()` z dialogów
- `TilePopover` zostaje bez zmian: to dziecko `Desktop` (nie top-level → nie staje się powierzchnią warstwy), pokazywany tylko w KD home (brak gry nad nim); zgodne z decyzją usera „popovery po staremu"
- `minimize`/`raise` w `KWinWindowManager` ZOSTAJĄ — nie są martwe: bezpiecznik `_return_to_desktop` (fullscreen), `_restore_desktop_view`, `_arrange_windows` (zarządzanie wieloma apkami)
- [x] testy zielone (185+54+10) + smoke start pod layer-shell bez wyjątków
- [x] **walidacja na żywo (user):** dialog „Zamknij…" nad grą JEST na wierzchu ✓; VolumeOverlay ✓; TilePopover ✓ (InfoDialog założony OK — dzieli `BaseOverlay`)

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
