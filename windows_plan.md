# Windows Support Implementation Plan - Kasual Desktop

## Cel
Port pełnego pulpitu Kasual Desktop (Steam Big Picture style) na Windows.
Iteracja 1 = działający pulpit z pełnym layoutem (TopBar, TileBar, HomeOverlay)
identycznym jak wersja Linuksowa, z niezaimplementowanymi funkcjami jako stuby.

> **AKTUALIZACJA ARCHITEKTURY (2026-06-21): de-fork.**
> Pierwotna iteracja sforkowała całą warstwę Qt UI do `infrastructure/windows/qt/`
> (desktop_view, tile_bar, topbar, app_tile, overlaye). To był błąd — te widżety są
> platform-neutralne. Zostały **usunięte**; Windows reużywa teraz **współdzielone**
> `infrastructure/qt/desktop/*` i `infrastructure/qt/overlays/*`, identycznie jak Linux.
>
> Różnice OS są ujęte w dwóch wąskich szwach:
> - **`DesktopSurface`** (`infrastructure/qt/desktop/surface.py`) — jak pulpit staje się
>   fullscreen/topmost. Linux: `LayerShellSurface` (wlr-layer-shell). Windows:
>   `WindowsHostSurface` (`infrastructure/windows/qt/host_surface.py`) — host WS_EX_TOPMOST
>   + monitor przywracania foreground + `TimedLaunchHide`.
> - **`promote_overlay_surface`** (`infrastructure/qt/ui/top_surface.py`) — jak overlay
>   wychodzi na wierzch. Linux: layer-shell OVERLAY. Windows: `Qt.WindowStaysOnTopHint`.
>
> Pozostałe pliki OS-specyficzne pod `infrastructure/windows/`: `shell.py`,
> `window_manager.py`, `app_manager.py`, `gamepad_watcher.py`, `wallpaper.py`,
> `desktop_shell.py`, `stubs.py`, `qt/host_surface.py`, `windows_main.py`.
> Sekcje "Struktura plików docelowych" i tabele statusu poniżej opisują stan
> *sprzed* de-forku — zachowane jako kontekst historyczny.

---

## Menu HomeOverlay (identyczne jak Linux)

### Gdy pulpit pusty (idle):
1. `Return to Desktop` (fa5s.home)
2. `Volume` (fa5s.volume-up)
3. `Brightness` (fa5s.sun)
4. `Notifications` (fa5s.bell)
5. `Network` (fa5s.wifi)
6. `Sleep` (fa5s.moon) - z confirm
7. `Restart` (fa5s.redo-alt) - z confirm
8. `Shut Down` (fa5s.power-off) - z confirm
9. `Minimize Desktop` (fa5s.window-minimize)

### Gdy aplikacja na foreground:
1. `Return to {nazwa}` (RETURN_TO_APP)
2. `Close {nazwa}` (CLOSE_APP)
3. [HUD item - jeśli hud skonfigurowany i foreground_is_game]
4. `Return to Desktop`

(cancel/B przywraca focus na foreground app)

---

## TopBar (identycznie jak Linux)
- Lewa strona: spacerek
- Środek: zegar (dzień + godz:min:sek)
- Prawa strona: 8 przycisków z ACTIONS w kolejności:
  1. Volume (fa5s.volume-up, #3b4252)
  2. Brightness (fa5s.sun, #434c5e)
  3. Notifications (fa5s.bell, #ebcb8b)
  4. Network (fa5s.wifi, #81a1c1 - ikona dynamiczna)
  5. Sleep (fa5s.moon, #4c566a)
  6. Restart (fa5s.redo-alt, #5e81ac)
  7. Shut Down (fa5s.power-off, #bf616a)
  8. Minimize Desktop (fa5s.window-minimize, #d580ff)

---

## Struktura plików docelowych

```
src/infrastructure/windows/
├── __init__.py
├── wallpaper.py                   # WindowsWallpaper (SystemWallpaper port)
├── app_manager.py                 # WindowsAppManager (subprocess + .lnk)
├── window_manager.py             # WindowsWindowManager (Win32 EnumWindows)
├── gamepad_watcher.py            # [ISTNIEJE] - do ewentualnych poprawek
├── shell.py                       # [ISTNIEJE] - WindowsShellManager
├── desktop_shell.py               # [ISTNIEJE] - stub DesktopShell
├── qt/
│   ├── __init__.py
│   ├── desktop_builder.py        # build_desktop() - kompozycja Desktop
│   ├── desktop_view.py           # WindowsDesktop (QWidget, port DesktopView/Shell/Control)
│   ├── topbar.py                 # WindowsTopBar
│   ├── tile_bar.py               # WindowsTileBar
│   ├── app_tile.py               # WindowsAppTile
│   ├── home_overlay.py           # WindowsHomeOverlay (MenuCursor + MenuItem)
│   ├── base_overlay.py           # BaseOverlay (stub)
│   ├── volume_overlay.py          # Stub
│   ├── brightness_overlay.py      # Stub
│   ├── network_overlay.py          # Stub
│   ├── notifications_overlay.py    # Stub
│   └── confirm_dialog.py           # Stub

src/infrastructure/windows/windows_main.py   # Entry point
```

---

## Status implementacji

### Iteracja 1 - MVP Desktop

| Komponent | Status | Uwagi |
|-----------|--------|-------|
| `windows_main.py` entry point | [x] | |
| `infrastructure/windows/__init__.py` aktualizacja | [x] | |
| `infrastructure/windows/wallpaper.py` | [x] | WindowsSystemWallpaper |
| `infrastructure/windows/window_manager.py` | [x] | Win32 EnumWindows |
| `infrastructure/windows/app_manager.py` | [x] | subprocess + .lnk |
| `infrastructure/windows/qt/__init__.py` | [x] | |
| `infrastructure/windows/qt/desktop_builder.py` | [x] | build_desktop() |
| `infrastructure/windows/qt/desktop_view.py` | [x] | WindowsDesktop |
| `infrastructure/windows/qt/topbar.py` | [x] | 8 przycisków + zegar |
| `infrastructure/windows/qt/tile_bar.py` | [x] | AppTile + dynamic |
| `infrastructure/windows/qt/app_tile.py` | [x] | WindowsAppTile |
| `infrastructure/windows/qt/home_overlay.py` | [x] | MenuCursor + MenuItem |
| `infrastructure/windows/qt/base_overlay.py` | [x] | Stub BaseOverlay |
| `infrastructure/windows/qt/volume_overlay.py` | [x] | Stub |
| `infrastructure/windows/qt/brightness_overlay.py` | [x] | Stub |
| `infrastructure/windows/qt/network_overlay.py` | [x] | Stub |
| `infrastructure/windows/qt/notifications_overlay.py` | [x] | Stub |
| `infrastructure/windows/qt/confirm_dialog.py` | [x] | Stub |

### Iteracja 2 - Dodatki (po Iteracji 1)

| Komponent | Status |
|-----------|--------|
| WindowsVolumeControl (pycaudio/Core Audio) | [ ] |
| WindowsBrightnessControl (WMI/DDC-CI) | [ ] |
| WindowsNetworkMonitor (psutil/Win32) | [ ] |
| WindowsNotificationMonitor (Win32 Toast) | [ ] |
| WindowsSoundFeedback | [ ] |

---

## Co DZIAŁA po Iteracji 1

- [x] Fullscreen shell (frameless, stays-on-top) - [ISTNIEJE w shell.py]
- [x] TopBar z zegarem i 8 przyciskami (jak Linux) - [x] ✓
- [x] HomeOverlay idle: "Return to Desktop" + 8 akcji (jak Linux) - [x] ✓
- [x] HomeOverlay app: "Return/Close {name}", "Return to Desktop" (jak Linux) - [x] ✓
- [x] Overlay'e panelowe (Volume/Brightness/Network/Notifications) renderują się - [x] ✓
- [x] Nawigacja gamepad (D-pad, A/B, BTN_MODE) - [x] (gamepad_watcher.py ISTNIEJE)
- [x] TileBar: statyczne kafle + separator + dynamic kafle okien - [x] ✓
- [x] Uruchamianie aplikacji z kafli (.lnk) - [x] ✓ (WindowsAppManager z .lnk resolution)
- [x] Minimize Desktop (hide shell) - [x] ✓ (WindowsDesktopShell.pause())
- [x] Return to Desktop - [x] ✓

## Co jest STUBEM

- [x] Volume suwak (UI jest, nie zmienia głośności systemu) - [x] ✓ stub
- [x] Brightness suwak (UI jest, nie zmienia jasności) - [x] ✓ stub
- [x] Network overlay (UI jest, nie pokazuje realnego stanu) - [x] ✓ stub
- [x] Notifications overlay (UI jest, nie pokazuje prawdziwych powiadomień) - [x] ✓ stub
- [x] Sleep/Restart/Shutdown (confirm dialog działa, akcja = logger.info("TODO")) - [x] ✓ stub

---

## Zmiany do pliku planu

- 2026-06-20: Utworzono plan
- 2026-06-20: Zaimplementowano Iterację 1 - pełny MVP Desktop dla Windows
- 2026-06-21: De-fork — usunięto sforkowaną warstwę `windows/qt/*`; Windows reużywa
  współdzielone widżety Qt przez szwy `DesktopSurface` + `promote_overlay_surface`.
  Naprawiono po drodze: confirm overlay nie na wierzchu (WS_EX_TOPMOST przez
  `promote_overlay_surface`), home overlay na współdzielonym `HomeOverlay`.
- 2026-06-21: Stan "running" kafli. Protokoły ms- NIE zwracają uchwytu procesu z
  ShellExecuteEx, więc śledzenie procesowe jest niemożliwe — running wykrywamy przez
  dopasowanie okna. Wymagało: (1) naprawy `_get_exe_path` (QueryFullProcessImageNameW
  zamiast nieistniejącego kernel32.GetModuleFileNameExW — wcześniej lista okien była
  pusta), (2) populacji `resource_class` basename'em exe, (3) rozwiązania realnego
  procesu UWP dla okien ApplicationFrameHost (np. SystemSettings.exe), (4) kafel
  ms-settings ma `wm_class="SystemSettings"`.

---

## Zależności Windows (do dodania w przyszłości)

- `pycaudio` lub `comtypes` - Volume control
- `psutil` - Network monitoring
- `win32api` (pywin32) - Notifications, brightness (WMI)