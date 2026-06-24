# ViGEmBus + HidHide — ekskluzywny pad na Windows (plan implementacji)

## 1. Cel

Odtworzyć model Linuxowy (KDE) na Windows: Kasual ma pada na wyłączność, a aplikacjom
(Steam, grom, bundled apps) udostępnia go przez wirtualny pad. Eliminuje to efekt
"cooperative" — dwie aplikacje nawigujące tym samym padem naraz (Kasual menu + Steam
pod spodem), opisany w `windows_plan_2.md:129-131`.

Docelowo: hold `BTN_HOME` → menu Kasuala (jak dziś), ale nawigacja po nim nie krwawi do
Steama, bo Steam widzi tylko wirtualny pad, a Kasual wstrzymuje do niego pisanie gdy
`stack.suppressed` (UI Kasuala aktywne).

## 2. Kontekst architektoniczny (co już mamy)

**Domena jest platform-neutralna i gotowa:**
- `src/domain/input/pad_control.py` — port `PadControl` (stos handlerów, trigger
  BTN_MODE, refresh). Implementuje go KDE i Windows identycznie.
- `src/domain/input/gamepad_signals.py` — port `GamepadSignals` (connect/disconnect/
  btn_mode).
- `src/domain/input/focus_stack.py:44-48` — `InputFocusStack.suppressed`: "True when
  our UI is active (stack non-empty) → block raw forwarding". To jest **kontrakt**
  bramkowania forwardu pada do aplikacji — zdefiniowany w domenie.
- `src/domain/input/recall.py:54-59` — `RecallTrigger.release(suppressed)` zwraca
  `bool`: czy forward synthetic press+release BTN_MODE do aplikacji jest potrzebny.
  Linux używa tego w `kde/gamepad_watcher.py:336-339`.
- `src/domain/lifecycle/app_lifecycle.py:128-131, 160-163` — `set_app_btn_mode_trigger`
  ustawiany per-aplikacja (HOLD_1S dla Steama z `_HOLD_1S_TARGETS` w
  `infrastructure/windows/app_discovery.py:33`).

**Model Linuxowy (`src/infrastructure/kde/gamepad_watcher.py`):**
- `d.grab()` (linia 237) — kernel-level exclusive grab, nikt nie widzi
  `/dev/input/eventX`.
- `UInput.from_device(d, name=VIRTUAL_DEVICE_NAME)` (linia 238) — wirtualny pad.
- `not self._stack.suppressed` (linia 343) — bramka forwardu raw eventów do uinput.
- BTN_MODE: synthetic press+release forward na release jeśli `RecallTrigger.release`
  zwróci `True` (linie 332-339).

**Model Windowsowy obecnie (`src/infrastructure/windows/gamepad_watcher.py`):**
- Cooperative — czyta przez pygame, nie ma wirtualnego pada, nie ma bramkowania.
- Komentarz w linii 4-5: "There is no exclusive grab on Windows without a kernel
  driver."
- Komentarz w liniach 206-209: short-press forward BTN_MODE jest "moot" bo pad jest
  cooperative i apka już widziała press. **Po wprowadzeniu ViGEm+HidHide to przestaje
  być prawdą** — apka nie widzi fizycznego pada, więc forward synthetic staje się
  konieczny (mirror Linuxa).
- `bool(self._stack)` (linie 189, 209) zamiast `self._stack.suppressed` — bo używa
  plain list zamiast `InputFocusStack` (otechniczne zadanie **P1.9** w
  `infra_refactor.md:18`).

**Bundled apps (`apps/file_browser/src/padbackend.py:51-103`):**
- Windows: czyta pada przez pygame bezpośrednio (cooperative). Linia 91-93: "On
  Windows the controller is cooperative (Kasual doesn't grab it), so we just take the
  first joystick. The *names* argument is ignored."
- Linux: czyta wirtualny `kasual-vpad` po nazwie (`padbackend.py:260-273`).
- Bundled apps są launchowane przez `pythonw.exe` (`infrastructure/windows/app_discovery.py:145`)
  — **inny image path** niż `python.exe` używany przez `kasual.ps1` do uruchomienia
  głównego procesu Kasual. To ma znaczenie dla HidHide (sekcja 5).

## 3. Model docelowy — mapowanie Linux → Windows

| Linux (KDE) | Windows (ViGEmBus + HidHide) |
|---|---|
| `evdev.InputDevice.grab()` (`kde/gamepad_watcher.py:237`) | **HidHide** — kernel driver ukrywa fizyczne urządzenie HID przed wszystkim poza allowlistą procesów. Kasual rejestruje swój image path w allowliście → tylko Kasual widzi fizycznego pada. |
| `UInput.from_device(d, name="kasual-vpad")` (linia 238) | **ViGEmBus** — kernel driver tworzący wirtualne pady Xbox360/DS4. Kasual pisze eventy na wirtualny pad o nazwie `kasual-vpad` (mirror nazwy z Linuxa). |
| `not self._stack.suppressed` → `uinput.write(ev.type, ev.code, ev.value)` (linia 343-344) | `not self._stack.suppressed` → `vigembus_writer.write_button(...)` / `write_axis(...)`. Identyczna semantyka bramki. |
| BTN_MODE synthetic forward na release (linie 332-339) | Identycznie: `uinput.write(BTN_MODE, 1)` + `syn()` + `uinput.write(BTN_MODE, 0)` + `syn()` → `vigembus_writer.set_guide(True)` + `set_guide(False)`. |
| `RecallTrigger.release(suppressed)` zwraca forward bool (linia 332) | Bez zmian — domena. Watcher wywołuje i warunkowo pisze synthetic do ViGEm. |
| `refresh()` po wyjściu Steama (`app_lifecycle.py:261, 281`) | Bez zmian — domena wywołuje, watcher reinituje. |

## 4. Zależności

### Drivery kernelowe (runtime requirement, nie Python)
- **ViGEmBus** — `ViGEmBus_1.22.0_x64_x86_arm64.exe` z release Nefariusa. Stabilny
  od lat (używany przez DS4Windows). Wymaga admin do instalacji, potem userland.
- **HidHide** — `HidHideMSI.msi` z release Nefariusa. Kernel driver filtrujący
  HID po image-path allowliście. Wymaga admin do instalacji, potem userland.

### Pakiety Python (do `requirements.txt`)
- **`vigembus`** — oficjalny binding Nefariusa dla ViGEmBus (`TargetType.Xbox360Wired`,
  `VigemTarget`, `VigemClient`, `xusb_request`, `set_axis_signed`, `set_axis_unsigned`,
  `set_pad_state`). **Weryfikacja nazwy pakietu na PyPI przy implementacji** — może
  być `pyvigembus` lub inna.
- **`comtypes`** — do sterowania HidHide przez COM API
  (`Nefarius.HidHide.Client`). Alternatywa: bezpośrednia edytacja rejestru
  `HKLM\SOFTWARE\Nefarius\HidHide\Blacklist` / `Whitelist` (ale COM API jest stabilniejszym
  kontraktem). Lub `HidHideControl.exe` shellowane — najprostsze, ale zależność od
  zewnętrznego binary.

## 5. Decyzje architektoniczne

### D1. Mechanizm czytania pada: pygame (zachowanie) vs hidapi (nowe)

**Wybór: pygame w głównym procesie Kasual (Option B — pragmatic).**

- Whitelist image-path `python.exe` w HidHide → pygame w procesie Kasual widzi
  fizycznego pada (SDL idzie przez RawInput, HidHide puszcza whitelisted proces).
- Bundled apps (`pythonw.exe`) **nie** whitelistowane → ich pygame nie widzi
  fizycznego pada, tylko wirtualnego.
- Steam.exe, gry.exe — nie whitelistowane → widzą tylko wirtualny pad.
- **Komprois dev**: każdy inny skrypt `python.exe` na maszynie też widzi pada.
  Akceptowalne dla dev; nieistotne dla packaged (Kasual jako `kasual.exe`).

**Alternatywa odłożona (Option A — clean, future):** Kasual czyta przez `hidapi`
(raw HID, bypass SDL), whitelistowany jest tylko proces Kasual. Większa zmiana
(rewrite read loopa z pygame na hidapi report parsing), ale zerowy komprois dev i
bliższe archetypowi Linuxowemu (`evdev` czyta raw, nie przez warstwę SDL). Miejsce
na przyszłą iterację.

### D2. Typ wirtualnego pada: Xbox360Wired

Najlepsza compat z XInput (Steam, gry, pygame w bundled apps wszyscy czytają
XInput natywnie). DS4 jest opcją przyszłą (dla userów z DS4/DualSense).

### D3. Nazwa wirtualnego pada: `kasual-vpad`

Mirror Linuxowego `VIRTUAL_DEVICE_NAME` (`kde/gamepad_watcher.py:27`). Pozwala
bundled apps szukać go po nazwie (`padbackend.py` Linux branch, linia 267) na obu
platformach jednoznacznie.

### D4. Fallback all-or-nothing

Jeśli **którykolwiek** z driverów (ViGEmBus, HidHide) jest nieobecny lub inicjalizacja
zawodzi → pełny fallback na obecny tryb cooperative (dzisiejszy behavior, bez
wirtualnego pada). Powód: ViGEm bez HidHide = Steam widzi **oba** pady (fizyczny +
wirtualny) → podwójne inputy, gorzej niż dzisiaj. Więc: albo pełny exclusive, albo
pełny cooperative. Tryb decyduje `driver_probe` przy starcie.

### D5. HidHide whitelist scope: tylko główny proces Kasual

Whitelist `python.exe` (lub `kasual.exe` po packagingu). **Nie** whitelistować
`pythonw.exe` (bundled apps), `steam.exe`, ani żadnych gier. To zapewnia:
Kasual ma pada na wyłączność, reszta świata widzi tylko wirtualnego.

### D6. Cykl życia rejestracji HidHide

- **Startup** (po wykryciu fizycznego pada): (1) dodaj image-path Kasuala do
  whitelist (idempotentnie), (2) dodaj instance ID pada do blacklist. HidHide
  generuje fake hotplug → Steam/Aple widzą zniknięcie fizycznego pada.
- **Shutdown / disconnect pada**: usuń instance ID z blacklist. Fake hotplug →
  Steam znów widzi fizyczny pad (jeśli Kasual się zamyka).
- **Kasual crash**: blacklist zostaje. Skutek: pad niewidoczny dla apek po
  restarcie. Mitigacja: `kasual.ps1` przy starcie sprawdza i czyści "stale"
  wpisy blacklist należące do niedziałającego Kasuala (po image-path + PID nie
  pasującym do żywego procesu). Lub prościej: registry wpis jest per-instance-ID,
  a instance ID pada się zmienia po replug → po restarcie pada wpis jest niegroźny.

### D7. Przyjęcie `InputFocusStack` (techniczne P1.9)

`WindowsGamepadWatcher` używa plain `list` jako stos handlerów (`gamepad_watcher.py:87`)
zamiast `InputFocusStack` z domeny. To zadanie **P1.9** z `infra_refactor.md:18`.
Przy okazji wprowadzamy ViGEm+HidHide — robimy to najpierw, bo bramkowanie ViGEm
będzie czytać `self._stack.suppressed` (mirror `kde/gamepad_watcher.py:191, 199, 343`),
a nie `bool(self._stack)`.

## 6. Warstwa domeny — brak zmian

Nic się nie zmienia w `src/domain/input/`. Wszystkie porty, kontrakty i logika
(`RecallTrigger`, `InputFocusStack.suppressed`, `DirectionRepeat`) są już
platform-neutralne i pokryte testami (`test_recall_trigger.py`,
`test_input_focus.py`, `test_direction_repeat.py`).

Jedyna "zmiana" w domenie: usunięcie technicznego długu P1.9 —
`WindowsGamepadWatcher` zaczyna używać `InputFocusStack` zamiast plain list. To
czysta refactorizacja w warstwie infrastruktury (`gamepad_watcher.py`), domena
bez zmian.

## 7. Nowa infrastruktura Windows — pliki

```
src/infrastructure/windows/
├── driver_probe.py        # NOWY — detekcja ViGEmBus + HidHide przy starcie
├── vigembus_writer.py     # NOWY — wrapper ViGEmClient + Xbox360 target
├── hidhide.py             # NOWY — wrapper HidHide COM API (whitelist/blacklist)
├── gamepad_watcher.py     # MODYFIKACJA — orchestracja exclusive/cooperative
└── ...
```

### `driver_probe.py` (nowy)
```python
@dataclass(frozen=True)
class DriverCapabilities:
    vigembus: bool       # ViGEmBus kernel driver installed & connectable
    hidhide: bool        # HidHide kernel driver installed & COM API reachable

def probe_drivers() -> DriverCapabilities: ...
```
- ViGEmBus: próba `VigemClient().connect()` — jeśli się uda, driver jest.
- HidHide: próba `comtypes.CoCreateInstance(CLSID_HidHideClient)` i wywołanie
  gettera — jeśli się uda, driver jest.
- Caching: wywołuje się raz na starcie, wynik trzymany w `WindowsGamepadWatcher`.

### `vigembus_writer.py` (nowy)
```python
class VigemWriter:
    """Pisanie na wirtualny pad Xbox360 przez ViGEmBus.

    Mirror semantyki evdev UInput: pojedyncze write(event) zamiast stateful
    bitmask rebuilding. Wewnętrznie utrzymuje aktualny stan przycisków jako
    bitmask i odsyła pełny report na każdym write (ViGEm przyjmuje diff
    implicite — wysyłka pełnego stanu jest tanie)."""

    def __init__(self, name: str = "kasual-vpad") -> None: ...
    def connect(self) -> None: ...        # VigemClient.connect + alloc Xbox360 target
    def disconnect(self) -> None: ...      # free target + client disconnect
    def write_button(self, button: int, value: int) -> None: ...   # EV_KEY-style
    def write_axis(self, axis: int, value: int) -> None: ...       # EV_ABS-style
    def set_guide(self, value: bool) -> None: ...                  # BTN_MODE synthetic
    def syn(self) -> None: ...             # no-op (ViGEm nie wymaga SYN jak evdev)
```

Mapowania (ważne, bo pygame i ViGEm używają różnych konwencji):
- pygame button index → XUSB_BUTTONS (bitmask: `XUSB_GAMEPAD_A`=0x1000, `B`=0x2000,
  `X`=0x4000, `Y`=0x8000, `LB`=0x0100, `RB`=0x0200, `START`=0x0008, `BACK`=0x0004,
  `GUIDE`=0x0400, `LEFT_THUMB`=0x0040, `RIGHT_THUMB`=0x0080).
- pygame axis (-1..1 float) → ViGEm s16 (-32768..32767) dla sticków X/Y, u8 (0..255)
  dla triggerów LT/RT. D-pad jako HAT lub 4 poszczególne buttony — XInput używa
  przycisków D-pad, nie HAT-a.
- Wartości stałe (próg, normalizacja) — reużyj `STICK_THRESHOLD` / `STICK_RESET`
  z `gamepad_watcher.py:37-38`.

### `hidhide.py` (nowy)
```python
class HidHideClient:
    """Sterowanie HidHide przez COM (Nefarius.HidHide.Client).

    Operacje: whitelistowanie image-path Kasuala, blacklistowanie device instance
    ID fizycznego pada. Wywołania idempotentne (HidHide samo deduplikuje)."""

    def register_self(self) -> None: ...              # add python.exe/kasual.exe to whitelist
    def hide_device(self, instance_id: str) -> None: ...
    def unhide_device(self, instance_id: str) -> None: ...
    def unhide_all(self) -> None: ...                 # cleanup przy shutdown
```
- COM API przez `comtypes`. CLSID do weryfikacji w dokumentacji HidHide.
- `instance_id` pada: uzyskany z pygame (joystick.get_guid()?) lub przez
  `pygame.joystick.Joystick.get_instance_id()` — jeśli to nie HID instance ID,
  trzeba dobrać się przez `SetupAPI` (ctypes) do prawdziwego device instance path.
  To najtrudniejszy element — do dopracowania w implementacji.

### `gamepad_watcher.py` (modyfikacja)

**Nowy stan w `__init__`:**
```python
self._caps = probe_drivers()                              # DriverCapabilities
self._stack = InputFocusStack()                            # (P1.9) — było plain list
self._writer: VigemWriter | None = None                   # ViGEm, None jeśli cooperative
self._hidhide: HidHideClient | None = None                # HidHide, None jeśli cooperative
self._pad_instance_id: str | None = None                  # do unhide przy shutdown
```

**Tryb exclusive** (gdy `self._caps.vigembus and self._caps.hidhide`):
- W `_loop`, po `JOYDEVICEADDED` i `Joystick.init()` (linia 149-151):
  1. `HidHideClient().register_self()`
  2. Rozwiąż instance ID pada → `self._pad_instance_id`
  3. `self._hidhide.hide_device(self._pad_instance_id)`
  4. `self._writer = VigemWriter(name="kasual-vpad"); self._writer.connect()`
- W `JOYDEVICEREMOVED` (linia 154-163): `self._writer.disconnect()`,
  `self._hidhide.unhide_device(self._pad_instance_id)`, `self._writer = None`.

**Tryb cooperative** (gdy którykolwiek driver nieobecny): jak dziś — brak
`_writer`, brak `_hidhide`, zachowanie 1:1 z obecnym kodem.

**Forwarding eventów do ViGEm** (w trybie exclusive):
- `_handle_button_down(button)` — po dispatch nav do stacka, dopisz:
  ```python
  if self._writer is not None and not self._stack.suppressed:
      self._writer.write_button(button, 1)
  ```
  Działa to **oprócz** BTN_MODE (BTN_MODE nigdy nie jest forwardowany real-time,
  tylko przez synthetic press+release na release — mirror Linuxa).
- `_handle_button_up(button)` — analogicznie z `value=0`. **Dla BTN_MODE**:
  ```python
  forward = self._recall.release(suppressed=self._stack.suppressed)
  if forward and self._writer is not None:
      self._writer.set_guide(True)
      self._writer.set_guide(False)
  ```
  To zastępuje obecny komentarz w `gamepad_watcher.py:206-209` ("moot on Windows")
  — po wprowadzeniu HidHide **przestaje być moot**: apka nie widziała press,
  więc musi dostać synthetic.
- `_handle_axis(axis, value)` / `_handle_hat(...)` — dopisz
  `self._writer.write_axis(...)` gdy `not self._stack.suppressed`.

**Zmiana P1.9**: `bool(self._stack)` → `self._stack.suppressed` (linie 189, 209).
Pozostałe metody `push_handler`/`pop_handler`/`top_handler` delegują do
`InputFocusStack` zamiast manipulować listą.

**`shutdown()`**: jeśli `_hidhide` i `_pad_instance_id` — `unhide_device`.
Wątek join. `pygame.quit`.

## 8. Fallback cooperative — brak driverów

`driver_probe.probe_drivers()` zwraca `DriverCapabilities(vigembus=False, ...)`
→ `WindowsGamepadWatcher` inicjalizuje w trybie cooperative:
- `_writer = None`, `_hidhide = None`
- Log WARN: "ViGEmBus/HidHide not installed — running in cooperative mode (pad
  bleed to foreground apps will occur). Install both drivers for exclusive
  control."
- Tray notification na pierwszym uruchomieniu (info, nie error — Kasual działa,
  tylko bez exclusive).

`windows_main.py:79-86` — bez zmian sygnatury (`WindowsGamepadWatcher()` bez
argumentów). Watcher sam dla siebie probe'uje drivery.

## 9. Bundled apps (file_browser) — przestawienie na wirtualny pad

**Dlaczego konieczne:** pod HidHide bundled apps (`pythonw.exe`) nie widzą
fizycznego pada. Bez zmiany `padbackend.py` file_browser nie dostaje żadnych
eventów pada.

**Zmiana w `apps/file_browser/src/padbackend.py:87-103` (Windows `find_pad`):**
- Skanuj `pygame.joystick.Joystick(i)` dla `i in range(get_count())`, wybierz ten
  którego `get_name() == "kasual-vpad"`.
- Fallback: jeśli nie znaleziono (tryb cooperative Kasuala — drivery nieobecne),
  weź `Joystick(0)` jak dziś.
- Argument `names` (linia 87) — dziś ignorowany na Windows; wykorzystać go:
  przekazać `["kasual-vpad"]` z `apps/file_browser/src/gamepad.py`.

**To jest osobna faza (patrz sekcja 12) — bez niej file_browser nie działa pod
HidHide, ale Kasual menu + Steam działają.** Można wysłać ViGEm+HidHide bez
tej zmiany i dokumentować, że file_browser wymaga Kasuala w trybie cooperative
(jeszcze jeden argument za all-or-nothing fallback w D4).

## 10. Provisioning / instalacja driverów

### `kasual.ps1` — check + prompt
Dodać na początku `kasual.ps1` (przed startem Kasuala):
- Sprawdź `Get-Service ViGEmBus` i `Get-Service HidHide` (lub przez COM/registry).
- Jeśli którykolwiek nieobecny: wyświetl komunikat z linkiem do release Nefariusa
  i opcjonalnie ofertuj automatyczny install (download + silent `msiexec /i`).
- `--install-drivers` flag dla automatycznego install bez prompt.

### `requirements.txt`
- Dodać `vigembus` (lub właściwą nazwę z PyPI) i `comtypes`.

### `windows_main.py`
- Po `probe_drivers()` log info: "Exclusive gamepad mode (ViGEmBus + HidHide)" lub
  "Cooperative gamepad mode (drivers missing — pad bleed will occur)".
- Przekazać capability do tray (status indicator w tooltipie? future).

## 11. Testy

### Nowe pliki testów
- `tests/test_vigembus_writer.py` — mock `vigembus` modułu, weryfikacja:
  - `write_button(BTN_SOUTH, 1)` → set_pad_state z `XUSB_GAMEPAD_A` bit set
  - `write_button(BTN_SOUTH, 0)` → bit cleared
  - `set_guide(True)` + `set_guide(False)` → `XUSB_GAMEPAD_GUIDE` puls
  - `write_axis` normalizacja -1..1 → -32768..32767
  - `connect`/`disconnect` lifecycle
- `tests/test_hidhide_client.py` — mock `comtypes.CoCreateInstance`, weryfikacja:
  - `register_self` → wywołanie COM z image-path Kasuala
  - `hide_device(instance_id)` → COM z instance ID
  - `unhide_device` / `unhide_all` cleanup
  - Idempotentność (drugie `hide_device` z tym samym ID → no-op lub bezpieczne)
- `tests/test_driver_probe.py` — mock importów, weryfikacja:
  - ViGEmBus obecny + HidHide obecny → `DriverCapabilities(True, True)`
  - Jeden nieobecny → `(False, ...)` / `(..., False)`
  - Obecny ale `connect()` rzuca → `False`

### Aktualizacja `tests/test_windows_gamepad_watcher.py`
- Fixture `mock_watcher` — patch `probe_drivers` + `VigemWriter` + `HidHideClient`
  (analogicznie do dzisiejszego patcha `pygame.init`).
- Nowe testy w nowej klasie `TestExclusiveForwarding`:
  - `test_button_press_when_not_suppressed_writes_to_vigem` — push handlera
    (pusty stack), wciśnij BTN_SOUTH, assercja `_writer.write_button` wołane.
  - `test_button_press_when_suppressed_does_not_write_to_vigem` — push handlera
    (stack non-empty), wciśnij BTN_SOUTH, assercja `_writer.write_button` NIE
    wołane.
  - `test_btn_mode_short_press_forwards_synthetic_to_vigem` — HOLD_1S trigger,
    pusty stack, press+release BTN_MODE (< 1s), assercja `_writer.set_guide(True)`
    + `set_guide(False)` wołane.
  - `test_btn_mode_hold_recall_does_not_forward` — HOLD_1S trigger, pusty stack,
    press, hold > 1s (timer fire), release, assercja `_writer.set_guide` NIE wołane.
  - `test_btn_mode_press_when_suppressed_does_not_forward` — handler na stacku,
    press+release BTN_MODE, assercja `set_guide` NIE wołane.
  - `test_axis_forwarded_when_not_suppressed` — analogicznie dla sticka.
  - `test_hat_forwarded_when_not_suppressed` — analogicznie dla D-pada.
- Nowa klasa `TestCooperativeFallback`:
  - `test_no_vigem_writes_when_drivers_absent` — `probe_drivers` zwraca
    `DriverCapabilities(False, False)`, wciśnij przycisk, assercja `_writer is None`
    i żadne write się nie dzieje.
  - `test_hidhide_absent_disables_exclusive_even_if_vigem_present` —
    `DriverCapabilities(True, False)`, assercja watcher w trybie cooperative (all-
    or-nothing, D4).
- Modyfikacja istniejących testów `TestBtnModeTrigger` — te przetestowane już
  logiki `RecallTrigger` zostają, tylko semantics z `bool(self._stack)` na
  `self._stack.suppressed` (transparentne przez `InputFocusStack`).

### Testy integracyjne (manualne, na Windows z driverami)
- Skrypt `tools/verify_exclusive_pad.ps1` (nowy):
  1. Uruchom Kasual.
  2. Potwierdź w Device Manager: fizyczny pad hidden, wirtualny `kasual-vpad`
     widoczny.
  3. Uruchom Steam Big Picture, nawiguj D-padem — Steam reaguje.
  4. Hold BTN_HOME 1s → menu Kasual, nawiguj D-padem — Steam NIE reaguje
     (weryfikacja że bleed zniknął).
  5. Zamknij menu — Steam znów reaguje.
  6. Zamknij Kasual — fizyczny pad znów widoczny w Device Manager.

## 12. Kolejność realizacji (fazy)

### Faza 0 — Prerekwizyt refactor (P1.9)
- `WindowsGamepadWatcher` na `InputFocusStack` zamiast plain list.
- `bool(self._stack)` → `self._stack.suppressed` (linie 189, 209).
- Update `test_windows_gamepad_watcher.py` — fixture + testy stacka idą przez
  `InputFocusStack` API.
- **Bez driverów, bez ViGEm** — czysty refactor, semantyka zachowana.

### Faza 1 — ViGEmBus writer (połowa wirtualna)
- Implementacja `vigembus_writer.py` + `driver_probe.py` (tylko ViGEmBus).
- `gamepad_watcher.py`: tryb exclusive z samym ViGEm (bez HidHide) →
  **tymczasowo Steam widzi OBA pady** (fizyczny + wirtualny) → podwójne inputy.
  Dlatego Faza 1 **niewydawana samodzielnie** — tylko do smoke testu, że writer
  działa (verifikacja: w `gamepad-tester.com` widać drugi pad `kasual-vpad`
  reagujący na fizyczne inputy).
- Testy: `test_vigembus_writer.py`, `TestExclusiveForwarding` (z mockiem HidHide
  — passing testowo, choć Faza 1 runtime nie używa HidHide).

### Faza 2 — HidHide (połowa ukrywania)
- Implementacja `hidhide.py` + rozszerzenie `driver_probe.py` o HidHide.
- `gamepad_watcher.py`: pełny tryb exclusive (ViGEm + HidHide). Steam widzi tylko
  wirtualny. **Tu bleed znika.**
- Fallback cooperative all-or-nothing (D4).
- Provisioning: `kasual.ps1` check driverów.
- Testy: `test_hidhide_client.py`, `TestCooperativeFallback`.
- Test integracyjny `tools/verify_exclusive_pad.ps1`.
- **Faza 2 = pierwsza wydwalna wersja z exclusive padem.**

### Faza 3 — Bundled apps na wirtualny pad
- `apps/file_browser/src/padbackend.py` Windows `find_pad` szuka `kasual-vpad`
  po nazwie.
- Test: `apps/file_browser/tests/` — test `find_pad` z mock pygame zwracającym
  wirtualny + fizyczny joystick, assercja że wybrany wirtualny.
- **Faza 3 odblokowuje file_browser pod HidHide.** Bez niej file_browser działa
  tylko gdy Kasual w trybie cooperative (drivery nieobecne).

### Faza 4 — Polish
- Tray status indicator (exclusive vs cooperative).
- `--install-drivers` auto-installer w `kasual.ps1`.
- Packaging: bundled installer dołącza ViGEmBus + HidHide (lub linkuje do
  Nefarius releases z user prompt).
- Opcjonalnie: Option A (hidapi w główym procesie Kasual) jako przyszła iteracja
  eliminująca python.exe whitelist kompromis dev.

## 13. Ryzyka i kompromisy

| Ryzyko | Mitigacja |
|---|---|
| Driver install wymaga admin (UAC prompt) | Jednorazowe, przy instalacji Kasuala. Runtime nie wymaga admin. |
| `python.exe` whitelist → inne skrypty widziom pad (dev) | Akceptowane dla dev. Po packagingu (`kasual.exe`) nieistotne. Future: hidapi (Option A) eliminuje. |
| HidHide blacklist zostaje po crash Kasuala | `kasual.ps1` czyści stale wpisy przy starcie (po image-path + sprawdzeniu PID). Pad replug też resetuje (instance ID się zmienia). |
| ViGEmBus/HidHide konflikty z DS4Windows jeśli user ma zainstalowane | HidHide whitelist jest addytywna — Kasual dodaje swój image-path, nie rusza innych wpisów. ViGEmBus pozwala na wiele wirtualnych klientów. |
| `vigembus` Python binding nazwa/availability na PyPI niepewna | Weryfikacja przy implementacji. Fallback: ctypes bezpośrednio do `ViGEmClient.dll` (C API stabilne). |
| Instance ID pada z pygame vs HID instance ID HidHide | Może wymagać SetupAPI (ctypes) do rozwiązania. Najtrudniejszy technicznie element. |
| HidHide COM API może się zmienić między wersjami | HidHide jest dojrzały (Nefarius, używany globalnie). COM interfejs stabilny od lat. |

## 14. Checklista akceptacji (Definition of Done)

- [ ] Faza 0: `WindowsGamepadWatcher` używa `InputFocusStack`, testy zielone.
- [ ] Faza 1: `VigemWriter` pisze na wirtualny pad, smoke test pokazuje drugi
      pad w `gamepad-tester.com`.
- [ ] Faza 2: Steam Big Picture nawigacja nie reaguje gdy menu Kasuala otwarte
      (verifikacja `tools/verify_exclusive_pad.ps1` zielony).
- [ ] Faza 2: fallback cooperative — Kasual startuje i działa bez zainstalowanych
      driverów (z warn logiem).
- [ ] Faza 2: shutdown Kasuala przywraca widoczność fizycznego pada (Device
      Manager).
- [ ] Faza 2: `kasual.ps1` detect + prompt install driverów.
- [ ] Faza 3: file_browser działa pod HidHide (czyta wirtualny pad po nazwie).
- [ ] Wszystkie testy jednostkowe zielone: `test_vigembus_writer.py`,
      `test_hidhide_client.py`, `test_driver_probe.py`, zaktualizowany
      `test_windows_gamepad_watcher.py`.
- [ ] `requirements.txt` zaktualizowane (`vigembus`, `comtypes`).

## 15. Odsyłacze

- Linux model: `src/infrastructure/kde/gamepad_watcher.py:237-239, 319-339, 343-344`
- Windows obecny: `src/infrastructure/windows/gamepad_watcher.py:1-14, 182-209, 331-337`
- Domena bramki: `src/domain/input/focus_stack.py:44-48`
- Domena recall forward: `src/domain/input/recall.py:54-59`
- P1.9 prerequisite: `infra_refactor.md:18`
- Bleed odłożony: `windows_plan_2.md:129-131`
- Bundled apps launch path: `src/infrastructure/windows/app_discovery.py:136-145`
- Bundled apps pad read: `apps/file_browser/src/padbackend.py:51-103, 260-273`
- Provisioning Steam HOLD_1S: `src/infrastructure/windows/app_discovery.py:30-33`
