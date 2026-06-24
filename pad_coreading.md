# Pad co-reading — izolacja inputu na Windowsie

## Problem

Kiedy z poziomu Kasual Desktop uruchomiony jest Steam, krótkie wciśnięcie
`BTN_MODE` wywołuje menu Steama, a przytrzymanie (~1 s) wywołuje Home Overlay
Menu Kasuala (`RecallTrigger`, `HOLD_SECONDS = 1.0`, `domain/input/recall.py:28`).
Gdy Home Overlay jest na wierzchu i nawigujemy nim, **równolegle nawiguje też
menu Steama** — ten sam pad porusza obydwoma menu jednocześnie.

## Root cause

Architektura wejścia fundamentalnie różni się między platformami:

### Linux — pełna izolacja (działa)
- `EVIOCGRAB` daje Kasualowi wyłączny dostęp do fizycznego urządzenia
  (`infrastructure/input/gamepad_watcher.py:240`) — żaden inny proces (w tym
  Steam) nie czyta pada bezpośrednio.
- Wirtualny gamepad `kasual-vpad` (UInput, `:241`) jest **jedyną** drogą, przez
  którą apki widzą input.
- `InputFocusStack.suppressed` (`domain/input/focus_stack.py:44-48`) — `True`,
  gdy overlay jest otwarty (stack niepusty) — bramkuje forwarding do urządzenia
  wirtualnego (`gamepad_watcher.py:346`). Otwarty overlay → Steam nic nie widzi.
- `BTN_MODE` nigdy nie jest forwardowany w czasie rzeczywistym; krótki press,
  który nie wywołał recalla, jest forwardowany syntetycznie na release
  (`gamepad_watcher.py:338-342`), więc Steam reaguje na swój guide button.

### Windows — model kooperatywny (bleed)
- `WindowsGamepadWatcher` (`infrastructure/windows/gamepad_watcher.py:67-83`)
  używa pygame/XInput, które jest **kooperatywne** — bez kernel-drivera nie ma
  odpowiednika `EVIOCGRAB`.
- Kasual routes eventy do `InputFocusStack` → overlay nawiguje poprawnie
  (`home_overlay.py:211`), ale **Steam równolegle sam odpytuje XInput** w swoim
  procesie, niezależnie od stanu stacka i fokusu okna.
- Nie istnieje urządzenie wirtualne, więc `suppressed` nie ma czego bramkować.
- Mitigant „przejęcie fokusu" był próbowany i usunięty
  (`windows_plan_2.md:129`) — Steam czyta XInput niezależnie od fokusu.

W warstwie PyQt/domenu problem **nie jest rozwiązywalny** — trzeba usunąć
apkę pod spodem ze źródła XInput.

## Opcje niemożliwe (sprawdzone)

`RegisterRawInputDevices` + `RIDEV_EXCLUDE`, `WH_KEYBOARD_LL`/`WH_MOUSE_LL`
hooks, `XInputSetState`, `BlockInput`, `ClipCursor`, `SetCapture` — **żadne nie
blokują** XInput do innych procesów. Raw Input jest współdzielony, hooks są
tylko dla klawiatury/myszy, `XInputSetState` steruje tylko wibracją.

## Proponowane rozwiązania

### Opcja A — HidHide + ViGEmBus (REKOMENDOWANA)

Lustro Linuksowego modelu (`EVIOCGRAB` ≈ HidHide, `UInput` ≈ ViGEm):

- **HidHide** (kernel-driver, podpisany) — ukrywa fizycznego pada przed
  wybranymi procesami (allowlist). Kasual trafia do allowlisty; Steam przestaje
  widzieć urządzenie fizyczne.
- **ViGEmBus** (kernel-driver, podpisany) — tworzy wirtualnego pada Xbox 360.
  Kasual pisze do niego eventy; Steam i gry czytają z niego.
- Forwarding do wirtualnego pada jest **bramkowany `suppressed`** — identycznie
  jak Linux (`gamepad_watcher.py:346`). Otwarty overlay → wirtualny pad milczy →
  brak dual-nav.
- `BTN_MODE`: syntetyczny press+release na short-press release, jak Linux
  (`:338-342`), więc Steam dostaje swój guide button tylko wtedy, gdy Kasual
  nie przejmuje sterowania.

**Zalety:** 1:1 parrytet z Linuksem, izolacja każdej apki pod spodem (nie tylko
Steama), gotowa logika domenowa (`InputFocusStack.suppressed`, `RecallTrigger`).
**Wady:** wymaga instalacji 2 kernel-driverów (podpisane, powszechnie używane
przez DS4Windows / Steam Input). Decyzja: **bundling w instalatorze**
(`packaging/`) — sterowniki instalowane obok Kasuala.
**Stack:** `vigembus` (Python bindings), HidHide CLI/COM (`comtypes`/`pythonnet`).

### Opcja B — Zawieszanie procesu

`NtSuspendProcess` / `DebugActiveProcess` na Steamie przy otwarciu overlayu,
resume przy zamknięciu.
**Wady:** anti-cheat w grach (ryzyko bana), timeouty sieciowe Steama, glitches
audio; **gry czytają XInput same** → zawieszenie samego Steama nie zatrzyma
nawigacji w grze pod spodem. Fragilne.

### Opcja C — Tylko ViGEm bez HidHide

Wirtualny pad istnieje, ale fizyczny pozostaje widoczny → Steam widzi OBA pady,
bleed trwa. Nie rozwiązuje problemu.

## Rekomendacja: A + bundling w instalatorze

### Plan implementacji

1. **Detekcja sterowników** (`infrastructure/windows/driver_probe.py` — nowy):
   sprawdzenie against `vigembus` (SC `ROOT\SYSTEM\0001` / urządzenie wirtualne)
   i HidHide (SC `HidHide`) przez `sc query` ctypes. Brak → prompt instalacyjny.

2. **Backend ViGEm** (`infrastructure/windows/virtual_gamepad.py` — nowy):
   `VirtualGamepad` tworzy `ViGEmTargetXbox360`, wrapuje `set_axis`/`set_button`
   dla kodów XInput. API lustrujące `UInput` z `gamepad_watcher.py`.

3. **Backend HidHide** (`infrastructure/windows/hidhide.py` — nowy):
   toggle ukrycia fizycznego pada (COM/CLI). Ukryj przy starcie watchera,
   odkryj przy shutdownie. Allowlista = PID Kasuala.

4. **Refactor `WindowsGamepadWatcher`** (`infrastructure/windows/gamepad_watcher.py`):
   - Zamień pygame na czytanie HID (raw) fizycznego pada (ukrytego przed
     innymi przez HidHide).
   - Wstaw bramkę `if virtual and not self._stack.suppressed: virtual.write(...)`
     w pętli czytającej — odpowiednik `gamepad_watcher.py:346`.
   - `BTN_MODE`: syntetyczny forward na release, jak `:338-342`.
   - Zachować thread→GUI bridge (`_Bridge`, Qt queued signals) i `DirectionRepeat`.

5. **Bundling instalatora** (`packaging/`):
   - Dołączyć instalatory HidHide i ViGEmBus do Windowsowego pakietu.
   - `nfpm.yaml` / skrypt instalacyjny uruchamia je silent (wymaga elevacji —
     UAC prompt) przy pierwszej instalacji.
   - Graceful degrade: jeśli sterowniki nieobecne, log warning i fallback na
     dzisiejszy model kooperatywny (bleed), żeby Kasual nie blokował startu.

6. **Testy** (`tests/`):
   - Jednostkowe: `suppressed` bramkuje forwarding do `VirtualGamepad` (mock
     ViGEm). Mirror testów Linuksowych.
   - Integracyjne (manual): otwarcie overlayu nad Steamem → Steam nie reaguje
     na D-pad/gałkę; zamknięcie → Steam znów nawiguje. Krótki press BTN_MODE →
     Steam menu; hold → Kasual overlay.

7. **Dokumentacja**: sekcja w README o wymaganych sterownikach na Windowsie.

### Pliki dotykane

- Nowe: `infrastructure/windows/{driver_probe,virtual_gamepad,hidhide}.py`
- Zmieniane: `infrastructure/windows/gamepad_watcher.py`, `infrastructure/windows/windows_main.py` (probe przy starcie), `packaging/*`, `requirements.txt` (`vigembus`, `comtypes`)
- Domena: bez zmian (reuse `InputFocusStack`, `RecallTrigger`, `vocabulary`)
