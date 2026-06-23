# Plan testów Windows — wyrównanie pokrycia z wersją KDE

## Stan obecny

- **914 testów** w `tests/` (was 873), **162 nowe testy Windows** w 4 plikach
- Pełna suita: `914 passed, 121 skipped, 0 failed` na Windows; testy Windows
  są `skipif(sys.platform != "win32")` więc leżą cicho na Linux CI
- Oryginalne 4 pliki skipowane na Windows (`test_app_manager.py`,
  `test_app_pinning.py`, `test_app_config.py`, `test_gamepad_watcher.py`) mają
  teraz swoje lustrzane odpowiedniki w `test_windows_*.py`
- Cała logika w `src/infrastructure/windows/` Poziomu 1 (app manager, pinning,
  config, gamepad) jest pokryta; Poziom 2 (window manager, discovery,
  brightness, network, power, volume, wallpaper, icons, surface, log window)
  nadal niepokryta

### Konwencja skipów

Testy stricte windowsowe dostają:
```python
pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Tests Windows Win32/ctypes adapters; needs ctypes.windll",
)
```
— symetryczne do istniejących `skipif(sys.platform == "win32", …)` na testach
Linux. Leżą cicho na Linux CI, działają na `windows-latest` i lokalnie.

---

## Poziom 1 — lustra skipowanych testów Linux [ukończone]

Odpowiedniki 4 plików skipowanych na Windows, z tą samą charakterystyką.

- [x] **`tests/test_windows_app_manager.py`** — odpowiednik `test_app_manager.py` (69 testów, pass)
  - `.lnk` i `ms-*` kierowane do `_shell_execute` (mock `ShellExecuteExW`)
  - zwykły `.exe` → `subprocess.Popen` z `CREATE_NO_WINDOW` + `STARTUPINFO`
  - PATH-resolution w `_find_in_path` (+ dodanie `.exe`)
  - `_shell_execute`: brak uchwytu → `AppStarted` emitowane, running via window-match
  - `_shell_execute`: jest uchwyt → `_WinHandle` śledzi PID
  - `_WinHandle.poll/wait/terminate` (mock `WaitForSingleObject`/`GetExitCodeProcess`/`TerminateProcess`)
  - `is_running` / `running_idxs` / `running_pid` / `all_running_pids`
  - idempotentny launch tego samego idx
  - `_on_finished`, `swap_indices`, `remove_index`
  - błędy: `FileNotFoundError`, `PermissionError`, `ShellExecuteExW` → 0

- [x] **`tests/test_windows_app_pinning.py`** — odpowiednik `test_app_pinning.py` (22 testy, pass)
  - `pin()` rozwiązuje exe przez `_get_exe_path`, buduje `App(command=exe, wm_class=resource_class)`
  - łańcuch fallback nazwy: `_file_description` → `resource_class.title()` → `window.title` → "App"
  - `_file_description` czyta PE version-info (mock `GetFileVersionInfoW`/`VerQueryValueW`)
  - brak exe / brak FileDescription → fallbacki
  - persystencja `.desktop` (order, unique filename) — dziedziczone z bazy
  - `unpin` i integracja z `AppPinningBase`

- [x] **`tests/test_windows_app_config.py`** — odpowiednik `test_app_config.py` (26 testów, pass)
  - `config_root()` pod `%APPDATA%\kasual-desktop` (monkeypatch `APPDATA`)
  - round-trip load → write `.desktop` (te same reguły INI co Linux)
  - `DesktopTileOrderStore` / `DesktopTileColorStore` / `provisioned_marker` na Windows

- [x] **`tests/test_windows_gamepad_watcher.py`** — odpowiednik `test_gamepad_watcher.py` (45 testów, pass)
  - mapowanie przycisków pygame → `Event`: SOUTH→SELECT, EAST→CANCEL, NORTH→CLOSE, START→MANAGE
  - `BTN_START` + `BTN_SELECT` w held → `btn_mode`
  - stick: threshold/hysteresis przez `_handle_stick_axis`
  - D-pad przez `_handle_hat`
  - `set_app_btn_mode_trigger` + `RecallTrigger` (CLICK vs HOLD_1S)
  - stack handlerów, `inject`, `on_btn_mode`/`on_connected`/`on_disconnected`
  - `refresh()`, `shutdown()` (mock `threading.Thread`)

## Poziom 2 — czysta logika adapterów Windows [in_progress]

- [x] **`tests/test_windows_window_manager.py`** — największa niepokryta powierzchnia (56 testów, pass)
  - `_is_taskbar_eligible`: APPWINDOW→True; TOOLWINDOW/NOACTIVATE→False; owner→False; exc→True
  - `_SKIP_EXES`: explorer/systemsettings/steam nigdy nie stają się kaflem
  - `_exe_basename` z `QueryFullProcessImageNameW` (mock)
  - `_resolve_uwp_pid`: ApplicationFrameHost → pierwsze dziecko z innym PID; brak → None
  - `_enum_windows`: pomija niewidoczne/bez tytułu/własny PID/skip-exes; active po `GetForegroundWindow`
  - cache, `on_windows_updated`, `activate_window`, `close_window`, `minimize_windows_for_pids`
  - `_request_list_refresh` deduplikuje

- [x] **`tests/test_windows_app_discovery.py`** (48 testów, pass)
  - `is_available`: which hit, `ms-settings:`, istniejący `.lnk`, plik, brak
  - `discover_candidates`: mock `_scan_start_menu`; kuracja (`_SKIP_NAME`/`_SKIP_TARGET`/`_SKIP_FOLDER`)
  - dedupe po basename, keep shallowest (`_depth`); sort: gry→depth→nazwa; `limit`; HOLD_1S dla steam
  - `_slug`, `builtin_candidates`, `_default_candidates`, `WindowsAppDiscovery.extra_candidates`
  - `_scan_start_menu`: mock `subprocess.run`, parsowanie `name\tlnk\ttarget`, timeout → `[]`

- [x] **`tests/test_windows_brightness.py`** (26 testów, pass)
  - `_build_ramp` (czysta fn): 100%→identity, 50%→gamma 2.0, 25%→gamma 4.0, clamp [1,100], monotoniczna
  - `WindowsBrightnessControl.__init__`: sbc działa→sbc; sbc rzuca→gamma (mock `_probe_sbc`)
  - `_SbcBrightnessControl.get/set` (mock `screen_brightness_control`)
  - `_GammaRampBrightnessControl.set`: mock `_collect_monitor_dcs` + `SetDeviceGammaRamp`; odrzucenie→info; `DeleteDC` w finally
  - `_collect_monitor_dcs`: mock `EnumDisplayMonitors`/`GetMonitorInfoW`/`CreateDCW`

- [x] **`tests/test_windows_network.py`** (35 testów, pass)
  - `_classify`, `_ipv4`, `_SKIP` filtrowanie
  - `_primary_interface`: Ethernet > Wi-Fi > unknown; offline → None
  - `WindowsNetworkProbe.read`: wybór, offline, exception → offline()
  - `_runas_netsh`: ShellExecuteEx → 0 (UAC declined) → False; brak uchwytu → True; WAIT_TIMEOUT/FAILED → False; exit_code != 0 → False; CloseHandle w finally
  - `WindowsNetworkControl`: disconnect/reconnect/can_reconnect z pamięcią `_last_interface`

- [x] **`tests/test_windows_power.py`** (7 testów, pass)
- [x] **`tests/test_windows_volume.py`** (8 testów, pass)
- [x] **`tests/test_windows_wallpaper.py`** (5 testów, pass)

- [ ] **`tests/test_windows_win_icons.py`**
  - `jumbo_icon`: sukces z `QImage` (mock SHGetFileInfoW/SHGetImageList/ImageList_GetIcon/GetIconInfo/GetDIBits)
  - każde pole failure → None; `DestroyIcon`/`DeleteObject` w finally; `shil=SHIL_EXTRALARGE` też działa

- [ ] **`tests/test_windows_desktop_surface.py`**
  - `install`: `FramelessWindowHint` + `WindowStaysOnTopHint`
  - `show_fullscreen`/`hide`/`activate`/`is_visible`/`on_reactivate`
  - `hide_for_launch`: ukrywa + singleShot(1500) startuje monitor
  - `_check_foreground`: klasa w `_DESKTOP_WIN_CLASSES` (Progman/WorkerW/Shell_TrayWnd/"") → stop + callback; inna → noop; widoczny → stop bez callback
  - `TimedLaunchHide`: arm/cancel/is_armed/_fire; arm po arm resetuje timer

- [ ] **`tests/test_windows_log_window.py`**
  - `open()` leniwie buduje `LogViewer`; drugie `open()` re-show bez duplikatu
  - `close()` woła `close` + `deleteLater`; po zamkniętym → noop

## Poziom 3 — integracja / composition

- [ ] **`tests/test_windows_main_composition.py`** — mirror `test_application.py`
  - `main()` importuje i wire'uje Windows-owe adaptery bez rzucania
  - `Application` dostaje instancje właściwych typów

- [ ] **`tests/test_windows_provisioning_roundtrip.py`**
  - Fake Start Menu → `extra_candidates` → `AppSelection` → `provision` → `load_apps`
  - `.desktop` round-trip: `command` (ścieżka `.lnk`), `wm_class`, `X-Kasual-Order`, `X-Kasual-RecallMenuTrigger`
