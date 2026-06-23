# Refactoring `src/infrastructure/`

## P0 — najwyższy priorytet

- [x] **P0.1** `common/qt/_meta.py` — wydzielić `_ProtocolQtMeta` (lub usunąć jawne Protocol-dziedziczenie w 13 klasach QObject). Dotknięte: `windows/app_manager.py:21`, `windows/window_manager.py:18`, `kde/app_manager.py:21`, `kde/window_manager.py:36`, `kde/gamepad_watcher.py:24`, `kde/network_manager.py:35`, `kde/notifications.py:41`, `kde/qt/desktop/deferred_hide.py:21`, `common/qt/desktop/{desktop.py:74, tile_bar.py:26, topbar.py:15}`, `common/qt/overlays/{home_overlay.py:25, onboarding_overlay.py:69}`.
- [x] **P0.2** `common/lifecycle/base_app_manager.py` — template-method `BaseAppManager` z abstrakcyjnymi `_spawn`/`_terminate_proc`/`_force_kill_proc`/`_wait_for_exit`. Usunię ~120 linii duplikacji między `windows/app_manager.py:86-296` i `kde/app_manager.py:25-223`.
- [x] **P0.3** `WindowsAppDiscovery(AppDiscovery)` + przepięcie `windows_main.py:121-140, 220-235` na `Provisioning(...).candidates()`. Start Menu scan jako rozszerzenie `starter_candidates`.
- [x] **P0.4** `AppPinningBase._persist(window, app)` w `common/catalog/pinning_base.py` — wyciągnie identyczny tail z `windows/app_pinning.py:57-73` i `kde/app_pinning.py:56-72`.
- [x] **P0.5** Mixin `_NmDbus` w `kde/network_manager.py` (lub osobny `_nm_dbus.py`) — usuwa 3-method duplikację między `NMNetworkMonitor` (137-160) a `NMNetworkControl` (229-248).

## P1 — średni priorytet

- [ ] **P1.6** KDE cache → `dict[str, Window]` (`kde/window_manager.py:405-422`) → `BaseWindowManager` w `common/qt/desktop/`.
- [ ] **P1.7** `common/catalog/xdg.py` — `xdg_app_dirs()` + `desktop_filename_candidates()`.
- [ ] **P1.8** `windows/_win32.py` — `SHELLEXECUTEINFO`, `SEE_MASK_NOCLOSEPROCESS`, `CREATE_NO_WINDOW`, `WAIT_TIMEOUT`.
- [ ] **P1.9** `WindowsGamepadWatcher` na `InputFocusStack` (`windows/gamepad_watcher.py:87, 308-322`).
- [ ] **P1.10** Fabryka `select_brightness_control()` dla Windows (symetryczne z `kde/brightness.py:113-125`).

## P2 — porządek i spójność

- [ ] **P2.11** `WindowsNetworkMonitor` (ukrycie `PollingNetworkMonitor`+probe+scheduler) w `windows/network.py`.
- [ ] **P2.12** Wspólny helper `select_first_backend(*factories)` dla `BrightnessControl`.
- [ ] **P2.13** `_run_subprocess(cmd, *, on_error_msg)` helper dla `power.py` obu platform.
- [ ] **P2.14** Przenieść side-effecty importu `windows/brightness.py:29-33` do `init()`.
- [ ] **P2.15** `kde/window_manager.py:303,308` — `json.dumps(uuid)` zamiast `replace("'", "\\'")`.
- [ ] **P2.16** `windows/app_manager.py:93` — poprawić typ `dict[int, Proc]` (alias na `Popen | _WinHandle`).
- [ ] **P2.17** `windows/app_discovery.py:53-70` — wydzielić skrypt PS do pliku `.ps1`.
- [ ] **P2.18** `windows/window_manager.py:272-288` — ustawić `active` w `enum_proc`.
- [ ] **P2.19** Spójność `# type: ignore[attr-defined]` przy `from typing import _ProtocolMeta`.