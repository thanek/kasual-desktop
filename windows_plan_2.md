# Windows Plan 2 — gapy do 100% parytetu z Linuksem

Analiza luk między Linuksowym `main.py` (źródło prawdy o pełnej funkcjonalności) a
`windows_main.py`. Kolejność realizacji zatwierdzona; **HUD na samym końcu**.

---

## Stan obecny: co już działa na Windows

Pulpit, kafle, topbar (zegar + 8 przycisków), home overlay, tile popover, confirm
dialog, **dźwięki**, **tray + sesja (start w tle / pokaż przy padzie)**, stan
„running" kafli (z UWP), uruchamianie apek (.lnk/.exe/protokół), tapeta, nawigacja
pad+klawiatura. Wszystko współdzielone z Linuksem (po de-forku).

---

## Gapy do 100% parytetu (wg priorytetu)

### Tier 1 / Faza 1 — Rdzeń użyteczności

**1. Katalog aplikacji + trwałość** — *największy gap*.
- [x] **App store/load** — reuse Linuksowego `app_config.py` (`config_root()` zrobione
  cross-platform: `%APPDATA%\kasual-desktop` na Windows). Format `.desktop` (INI) —
  ten sam co Linux, pełny reuse. (Decyzja: `.desktop`, nie `.lnk` — `.lnk` binarny i bez
  miejsca na `X-Kasual-*`; `.lnk` zostaje jako źródło discovery/target.)
- [x] **Trwałość kolejności** (`DesktopTileOrderStore`) — reuse.
- [x] **Trwałość koloru** (`DesktopTileColorStore`) — reuse.
- [x] **Pinowanie okna jako kafel** (`WindowsAppPinning`) — wariant Windows: okno→exe
  (ścieżka procesu) + nazwa z version-info (FileDescription) + `wm_class`=basename exe.
- [x] **Onboarding interaktywny + odkrywanie aplikacji** — `WindowsAppDiscovery`
  skanuje Menu Start (batch-resolve celów `.lnk` jednym wywołaniem PowerShell przez
  `-EncodedCommand`, bez pywin32), kuracja (pomijanie uninstall/help/folderów
  systemowych, dedupe po celu, priorytet top-level, limit 16), `wm_class`=basename
  celu. Wpięty współdzielony `OnboardingOverlay` przy 1. uruchomieniu; fallback na
  seed domyślny (Settings+Browser) gdy skan pusty.
- [x] **Launch `.lnk` naprawiony** — `ms-`/`.lnk` idą wspólną ścieżką `ShellExecuteEx`
  (Explorer rozwiązuje skrót; dla zwykłego exe dostajemy uchwyt do śledzenia). Usunięto
  zależność od pywin32 (`_resolve_lnk`).

**→ Item 1 (katalog) UKOŃCZONY i zweryfikowany na venv.**

**2. Kontrole systemowe** (overlaye się otwierają, ale na stubach):
- [ ] **Volume** — `pycaw`/`comtypes` (Core Audio). Wymaga zależności.
- [ ] **Brightness** — WMI (laptopy) / DDC-CI (monitory), graceful no-op gdy brak.
- [ ] **Power** (sleep/restart/shutdown) — czysty ctypes Win32 (bez zależności).

**3. Sieć** — wskaźnik statyczny. Domena ma `PollingNetworkMonitor` + port
`NetworkProbe`, więc wystarczy implementacja `NetworkProbe` + podpięcie
`update_network_status` w `windows_main`. (ctypes/wininet, bez zależności.)

### Tier 2 — Polski i wykończenie

**4. Powiadomienia** — `NotificationCenter` pusty; WinRT `UserNotificationListener`
→ `record()` + sync `refresh_notification_badge`.

**5. Tłumaczenia** — `install_translations` niewołane → UI po angielsku.

**6. Font Awesome** — `install_fontawesome5` niewołane (do weryfikacji, czy ikony OK).

**7. Logowanie do pliku + log viewer** — teraz tylko konsola.

### Tier 3 — Cykl życia na Windows

**8. Autostart przy logowaniu** (Startup/Task Scheduler/registry Run) + **single-instance
guard** — by „start w tle" był realny na maszynie użytkownika.

### Tier 4 — HUD (na końcu)

**9. Odpowiednik HUD wydajności** — zostawione, użytkownik ma pomysł.

---

## Kolejność realizacji

Faza 1 (Tier 1) najpierw, a w niej **katalog+trwałość (1)** przed resztą (pinowanie/
kolejność/kolor o niego zaczepiają). Potem (2) kontrole systemowe, (3) sieć. Następnie
Tier 2 (dopieszczanie), Tier 3 (dystrybucja), HUD na końcu.

---

## Decyzje architektoniczne

- **Format katalogu: `.desktop` (INI tekst)**, nie `.lnk`. Powód: `.lnk` to format binarny
  bez sekcji dowolnych kluczy — nie pomieści `X-Kasual-Order`/`X-Kasual-Color`; edycja
  wymaga COM. `.desktop` round-trippuje nasze metadane i pozwala reużyć 100% kodu z
  Linuksa. `.lnk` używamy tylko jako źródło discovery (skan Menu Start) i jako poprawny
  cel uruchomienia (WindowsAppManager rozwiązuje `.lnk`).
- **Reuse zamiast forka:** `app_config.py` jest czystym Pythonem; jedyna zmiana to
  cross-platform `config_root()`. `WindowsAppPinning` dziedziczy po `DesktopAppPinning`
  i nadpisuje tylko rozwiązanie źródła okna.

---

## Changelog

- 2026-06-21: Utworzono plan 2 (analiza luk).
- 2026-06-21: Faza 1, item 1 (katalog) — load/order/color/pin/provisioning na
  współdzielonym `.desktop`; zweryfikowane round-trip na venv.
- 2026-06-21: Faza 1, item 1 ukończony — onboarding (skan Menu Start + picker),
  launch `.lnk` przez ShellExecuteEx (bez pywin32). Zweryfikowane na venv.
- 2026-06-21: Onboarding dopracowany — picker listuje WSZYSTKIE skuratorowane apki
  (scroll w `OnboardingOverlay`, cap ~60% wysokości ekranu, podążanie kursorem), a
  wstępnie zaznacza tylko gry/launchery przez domenową heurystykę `looks_like_game`
  (`domain/catalog/game_heuristic.py`, współdzielona Linux+Windows, do rozbudowy).
  Gry sortowane na górę.
- 2026-06-21: `kasual.ps1 --provisioning` (alias `--provision`) usuwa marker
  `.provisioned` (jak `kasual.sh`). Picker pokazuje ikony aplikacji (ikona powłoki
  z `.lnk`/exe przez `QFileIconProvider` — fallback w `_candidate_icon`, cross-platform).
  Płaski scrollbar (`styles.flat_scrollbar()`, współdzielony z notifications), większy
  margines toggli pod scrollbar.
- 2026-06-21: Autofire D-pada/gałki — reuse domenowego `DirectionRepeat` w
  `gamepad_watcher` (pętla pygame 60fps odpytuje `due()` co tick; press/release na
  przejściach kierunku). Zweryfikowane deterministycznie.
- 2026-06-22: Ikony kafli — `shell_icon` (QFileIconProvider) w `icons.py`, fallback
  w `_make_static_tile` + reuse w onboardingu. Poprawione mapowanie przycisków pada
  (8BitDo/XInput): START 4→7, SELECT 5→6, WEST/NORTH odwrócone (X=2/Y=3) — MANAGE na
  Start, CLOSE na X.
- 2026-06-22: Ikony zbyt małe — `QFileIconProvider` dostarcza tylko 32px (mimo
  raportowania 256). Dodano ekstrakcję jumbo 256px przez Win32 (`win_icons.py`:
  image list + ImageList_GetIcon → HICON → QImage); `shell_icon` używa jej na Windows.
  Naprawiono Minimize z Home Overlay: strażnik `not _state.paused` w `Desktop.changeEvent`
  (focus-gain przy zamykaniu overlayu nie reaktywuje świadomie zminimalizowanego pulpitu).
- 2026-06-22: BTN_MODE recall (jak Linux) — `RecallTrigger` w `gamepad_watcher`
  (`set_app_btn_mode_trigger`, kasual_active=bool(stack), HOLD_1S=1s). Provisioning
  nadaje Steamowi `recall_menu_trigger=HOLD_1S` (`_HOLD_1S_TARGETS` w discovery).
  Dziedziczenie przez dzieci: na Windows trigger jest sticky od launchu do powrotu na
  pulpit, więc gry odpalone ze Steama dziedziczą HOLD_1S bez chodzenia po drzewie
  procesów (per-okno rozwiązywanie triggera dla dynamicznych kafli = NTH, fragile przez forking).
- 2026-06-22: Mitygant dual-nav (przejmowanie fokusu) NIE zadziałał (Steam czyta XInput
  niezależnie od fokusu) — usunięty. Bleed do Steama odłożony (czeka na decyzję: HidHide/ViGEm,
  zawieszanie procesu, lub akceptacja).
- 2026-06-22: Ikony dynamicznych kafli — `WindowIconResolver` rozwiązuje ikonę z exe procesu
  okna (jumbo, krok 4) na Windows. Builtin apps (File Browser, YouTube) provisionowane na
  Windows: `builtin_candidates()` (venv pythonw + `.py` z `apps/`), zawsze oferowane; round-trip
  przez `.desktop` zachowuje ścieżki Windows. Następne: item 2 (kontrole: power/volume/brightness).
- 2026-06-22: Filtrowanie okien po taskbar-eligibility — `_is_taskbar_eligible` w
  `window_manager.py` (odpowiednik KWin `!skipTaskbar && normalWindow`): pomija
  zawieszone UWP frames (`ApplicationFrameWindow` z `WS_EX_NOACTIVATE`/`TOOLWINDOW`
  lub z ownerem), tool windows i owned transients. Naprawia p. 2 z `todo.md`:
  zawieszony `SystemSettings.exe` nie jest już enumerowany, więc tile Settings
  nie świeci się jako "running" i close-path nie próbuje zamykać zawieszonej UWP.
  Dodatkowo: `systemsettings` dodany do `_SKIP_EXES` (Windows utrzymuje
  zawieszony SystemSettings jako widoczne okno bez wpisu na taskbarze —
  heurystyka ex_style go nie łapała; Settings to built-in tile, nie potrzebuje
  dynamicznego kafelka) + guard w UWP branch odrzuca resolve, które zwraca
  `applicationframehost` (edge case pustego frame'a).
- 2026-06-22: Stabilna kolejność dynamicznych kafli — `TileBar._dyn_order`
  (first-seen order window id) w `tile_bar.py`. Na Windows `EnumWindows` zwraca
  okna w Z-orderze (aktywacja okna → przesunięcie na początek), więc bez tego
  dynamiczne kafle zmieniały kolejność przy aktywacji. KWin's `windowList()`
  jest już stabilny (creation order), więc fix jest no-op na Linuxie. Nowe okna
  lądują na końcu, zniknięcie okna nie rusza pozostałych, pusta lista czyści
  pamięć kolejności. Testy: `TestDynamicTileOrder` w `test_tile_bar.py`.
- 2026-06-22: Brightness na Windows — `WindowsBrightnessControl` w
  `brightness.py` z dwoma backendami: (1) `screen_brightness_control` (real
  backlight via WMI/DDC-CI) gdy sbc działa, (2) gamma-ramp fallback via Win32
  `SetDeviceGammaRamp` gdy sbc zawodzi (zepsute DDC/CI, np. HDMI TV bez CEC).
  Gamma ramp: per-monitor dimming przez `EnumDisplayMonitors`+`CreateDCW`
  (sięga wszystkich GPU, nie tylko primary), power-curve `(i/255)^gamma` zamiast
  linear (driver Della odrzuca linear <50%, power-curve schodzi do ~25%).
  Partial failure (driver anti-blackout floor) logowany info, nie warning.
  Reset LUT do identity przy 100%.
