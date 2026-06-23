# Infrastructure split plan — `infrastructure/{kde,windows,common}`

Point 6 of `todo.md`: *"po odseparowaniu domeny od implementacji, trzeba pomyśleć
o podobnym podziale wewnątrz infrastruktury (kde, windows, common)".*

Status: **Phase A + Phase B done. Verified on Windows (752 tests pass, all smoke
imports OK). Linux runtime + the evdev/QtDBus-only kde modules still need a
verification run on a Linux checkout (see "Linux verification TODO" below).**

### Realisation log (2026-06-23)

**Done (Phase B — physical move to `infrastructure/{kde,common,windows}`):**
- 52 files `git mv`'d; imports rewritten across 57 files (one-shot script).
  `system/`, `input/`, `mangohud/`, `qt/`, `audio/` packages removed.
- `qt/` → `common/qt/` except `layer_shell` impl + `deferred_hide` → `kde/qt/`.
- `surface.py` split: `DesktopSurface` Protocol + new `PlainSurface` default in
  `common/qt/desktop/surface.py`; `LayerShellSurface` → `kde/qt/desktop/surface.py`.
  `Desktop` now defaults to `PlainSurface`; Linux root injects `LayerShellSurface`.
- `layer_shell` split: the `Layer/Anchor/Keyboard` enums (pure vocabulary) →
  `common/qt/ui/layer_shell.py`; the LayerShellQt ctypes binding stays in
  `kde/qt/ui/layer_shell.py` (imports the enums from common). `top_surface`
  lazy-imports `make_layer_surface` only in the wayland branch.
- Coupling #4: extracted `common/catalog/pinning_base.AppPinningBase` (unpin +
  placement mechanics + slug helpers). Both `DesktopAppPinning` (kde) and
  `WindowsAppPinning` (windows) subclass it — **windows no longer imports kde**.
- `x11_icon` kept in `common/qt/desktop/` (guarded/lazy, X11-not-KDE) so
  `window_icons` needs no cross-package import for it.

**Boundary audit (grep):** `windows → kde` = 0. `common → kde` = lazy only
(`top_surface` wayland branch) + docstrings. `common → windows` = lazy/guarded
only (`icons.jumbo_icon`, `window_icons` exe path) — the established pattern.

**Linux verification TODO (cannot run on Windows — evdev/QtDBus/fcntl):** import
+ runtime-check `kde/{window_manager,notifications,gamepad_watcher,network_manager}`
and `kde/qt/desktop/deferred_hide`, plus a full `kasual.sh` smoke. These
syntax-compile clean and their `infrastructure.*` imports were verified to resolve
to existing modules, but only a Linux run exercises their actual import + behaviour.

**Done (Phase A — sever couplings + cleanup, all verified on Windows):**
- Legacy Windows cleanup: deleted `windows/shell.py`, `windows/desktop_shell.py`;
  emptied `windows/__init__.py` (no eager/side-effect imports).
- Coupling #1+#3: `build_desktop` takes injectable `parent_of`/`process_name_of`
  (no-op defaults); threaded into `ForegroundInspector` and `TileBar`
  (`_get_ppid` removed from the common tile_bar). Linux root passes `proc.py`'s
  readers; Windows uses no-ops. The common Qt layer no longer reads `/proc`.
- Coupling #2: replaced the lazy `DeferredHide` fallback in `build_desktop` with
  an injected `deferred_hide_factory` (+ a common `_ImmediateHide` default), so
  the shared builder never imports a platform's deferred-hide. Linux passes a
  factory building `DeferredHide`; Windows one building `TimedLaunchHide`.
- Moved `windows_main.py` → `src/windows_main.py` (sibling of `main.py`); dropped
  its sys.path hack; updated `kasual.ps1`.

**Pending (Phase B — physical move) — do on a Linux-capable checkout because:**
1. It rewrites Linux import paths (`main.py`, all `kde/*`) that can't be executed
   on Windows (evdev / QtDBus modules don't import here).
2. The move surfaces *common→platform* lazy-import leaks that need injection
   refactors (not just `git mv`), beyond the originally-listed couplings:
   - `qt/desktop/window_icons.py` lazily imports `x11_icon` (→ kde) **and**
     `shell_icon`→`win_icons` (→ windows). Icon resolution should be injected so
     `common/qt/desktop/window_icons.py` imports neither platform.
   - `qt/desktop/surface.py` must be split (Protocol → common; `LayerShellSurface`
     → kde) — a per-file logic split, not a move.
3. Coupling #4 (pinning base) is best created directly in `common/catalog/` during
   the move rather than in a temporary location.

Add to §9 checklist: `grep "from infrastructure.kde" common/` and
`grep "from infrastructure.windows" common/` both return 0 (catches the leaks above).

---

## 1. Current state

The project already has a clean `domain/` ⇄ `infrastructure/` separation. The
domain layer is provably Qt-free and IO-free (zero `from PyQt6` matches in
`src/domain/`; every OS/compositor detail is behind an injected `Protocol` or
callable — 39 ports total across 13 subpackages).

The infrastructure layer, however, is **organised by concern** (`system/`,
`input/`, `audio/`, `mangohud/`, `qt/`, `windows/`) rather than by platform.
KDE/Linux code is scattered across `system/` (10 of 14 files), `input/`, and
`mangohud/`, with no consistent naming convention (only 2 files carry a `kde_`
prefix). Windows is already correctly isolated under `windows/`.

```
infrastructure/
├── system/    ← 10/14 KDE/Linux; 2 COMMON; 2 Linux-base-for-Windows
├── input/     ← Linux (evdev)
├── mangohud/  ← Linux
├── audio/     ← COMMON (QtMultimedia)
├── qt/        ← mostly COMMON; 3 KDE/Wayland files; 3 /proc leaks
└── windows/   ← Windows (correctly placed)
```

---

## 2. Target structure

```
infrastructure/
├── kde/         ← KDE/Linux adapters (the Linux composition root's backend)
├── windows/     ← Windows adapters (already correct; minor cleanup)
└── common/      ← platform-neutral adapters + the shared Qt UI
    ├── qt/      ← desktop, overlays, ui, scheduler, icons, i18n
    ├── audio/   ← SoundFeedback
    └── catalog/ ← app_config / file_log_source / app_discovery
```

This mirrors the existing `domain` ⇄ `infrastructure` boundary inside
`infrastructure/` itself: `common/` is the shared adapter kernel, `kde/` and
`windows/` are the two platform plug-ins wired at the composition roots.

`infrastructure/system/` disappears entirely — every file gets a new home.

---

## 3. File-by-file move plan

### 3.1 → `infrastructure/kde/`

From `infrastructure/system/`:
| File | Target | Class(es) | Port(s) |
|---|---|---|---|
| `window_manager.py` | `kde/window_manager.py` | `KWinWindowManager`, `expand_pid_tree` | `WindowManager` |
| `power.py` | `kde/power.py` | `SystemdPowerControl` | `PowerControl` |
| `volume.py` | `kde/volume.py` | `PactlVolumeControl` | `VolumeControl` |
| `brightness.py` | `kde/brightness.py` | `Brightnessctl…`, `KdeBrightnessControl`, `select_brightness_control`, `NullBrightnessControl` | `BrightnessControl` |
| `kde_wallpaper.py` | `kde/wallpaper.py` | `KdeSystemWallpaper` | `SystemWallpaper` |
| `kde_notifications.py` | `kde/notifications.py` | `KdeNotificationMonitor` | `NotificationSource` |
| `network_manager.py` | `kde/network_manager.py` | `NMNetworkMonitor`, `NMNetworkControl` | `NetworkMonitor`, `NetworkControl` |
| `app_manager.py` | `kde/app_manager.py` | `AppManager` (POSIX process groups) | `ProcessManager` |
| `proc.py` | `kde/proc.py` | `parent_pid`, `process_name` (`/proc` readers) | (injected callables) |
| `log_viewer_launcher.py` | `kde/log_viewer_launcher.py` | `LogViewerLauncher` (strips Wayland env) | (ad hoc) |
| `app_pinning.py` | `kde/app_pinning.py` | `DesktopAppPinning` (XDG/freedesktop) | `AppPinning` |
| `app_discovery.py` | `kde/app_discovery.py` | `WhichAppDiscovery` | `AppDiscovery` |

From `infrastructure/input/`:
| File | Target | Class(es) | Port(s) |
|---|---|---|---|
| `gamepad_watcher.py` | `kde/gamepad_watcher.py` | `GamepadWatcher` (evdev) | `PadControl`, `GamepadSignals` |

From `infrastructure/mangohud/`:
| File | Target | Class(es) | Port(s) |
|---|---|---|---|
| `config.py` | `kde/mangohud.py` | `MangoHudControl` | `HudControl` |

From `infrastructure/qt/` (KDE/Wayland-specific bits hiding in the shared Qt layer):
| File | Target | Notes |
|---|---|---|
| `ui/layer_shell.py` | `kde/qt/ui/layer_shell.py` | ctypes bridge to `libLayerShellQtInterface.so.6`; safe no-op off-Wayland |
| `desktop/deferred_hide.py` | `kde/qt/desktop/deferred_hide.py` | `DeferredHide` polls KWin + reads `/proc`; Windows already sidesteps via `TimedLaunchHide` |
| `desktop/x11_icon.py` | `kde/qt/desktop/x11_icon.py` | `X11IconReader` reads `_NET_WM_ICON` via python-xlib (XWayland) |
| `desktop/surface.py::LayerShellSurface` | `kde/qt/desktop/surface.py` | KDE `DesktopSurface` impl; the `DesktopSurface` Protocol stays in `common/qt/desktop/surface.py` |

### 3.2 → `infrastructure/common/`

From `infrastructure/system/`:
| File | Target | Notes |
|---|---|---|
| `app_config.py` | `common/catalog/app_config.py` | Already has `os.name=="nt"` branch; imported by **both** roots |
| `file_log_source.py` | `common/log/file_log_source.py` | Pure `os.path`/`open` |
| `app_pinning_base.py` (NEW) | `common/catalog/pinning_base.py` | Extracted shared persistence mechanics — see coupling #4 |

From `infrastructure/audio/`:
| File | Target | Notes |
|---|---|---|
| `feedback.py` | `common/audio/feedback.py` | `SoundFeedback` over QtMultimedia |

From `infrastructure/qt/` (everything not moved to `kde/`):
| Path | Target | Notes |
|---|---|---|
| `scheduler.py` | `common/qt/scheduler.py` | `QtScheduler` |
| `icons.py` | `common/qt/icons.py` | `install_fontawesome5` + `shell_icon` (has Windows branch) |
| `i18n.py` | `common/qt/i18n.py` | `QtTranslator` + `install_translations` |
| `desktop/desktop.py` | `common/qt/desktop/desktop.py` | `Desktop` QWidget |
| `desktop/desktop_builder.py` | `common/qt/desktop/desktop_builder.py` | `build_desktop` (after coupling #1 fix) |
| `desktop/tile_bar.py` | `common/qt/desktop/tile_bar.py` | `TileBar` (after coupling #3 fix) |
| `desktop/topbar.py` | `common/qt/desktop/topbar.py` | |
| `desktop/app_tile.py` | `common/qt/desktop/app_tile.py` | |
| `desktop/window_icons.py` | `common/qt/desktop/window_icons.py` | Has platform branches |
| `desktop/surface.py` (Protocol only) | `common/qt/desktop/surface.py` | `DesktopSurface` Protocol; `LayerShellSurface` moves to `kde/` |
| `ui/top_surface.py` | `common/qt/ui/top_surface.py` | `promote_overlay_surface` — platform dispatcher |
| `ui/styles.py` | `common/qt/ui/styles.py` | |
| `ui/toggle_switch.py` | `common/qt/ui/toggle_switch.py` | |
| `ui/tray.py` | `common/qt/ui/tray.py` | `SystemTray` |
| `ui/log_viewer.py` | `common/qt/ui/log_viewer.py` | |
| `overlays/*.py` (13 files) | `common/qt/overlays/` | All cross-platform; use `promote_overlay_surface` |

### 3.3 → `infrastructure/windows/` (already placed; cleanup only)

Correctly placed (no move):
- `window_manager.py`, `app_manager.py`, `gamepad_watcher.py`, `wallpaper.py`,
  `volume.py`, `brightness.py`, `power.py`, `network.py`, `app_pinning.py`,
  `app_discovery.py`, `win_icons.py`, `qt/desktop_surface.py`, `windows_main.py`

Cleanup (delete or explicitly mark as dead):
- `windows/shell.py` — `WindowsShellManager`, `ShellWindow`, `get_windows_wallpaper`.
  Not imported by `windows_main.py`; `wallpaper.py` supersedes `get_windows_wallpaper`.
- `windows/desktop_shell.py` — `WindowsDesktopShell` stub ("not implemented in PoC").
  Not imported by `windows_main.py`.
- `windows/__init__.py` — stale exports of `WindowsShellManager`/`get_windows_wallpaper`
  from `shell.py`.

Subfolder `windows/qt/` currently holds only `desktop_surface.py`. After the split
it naturally parallels `kde/qt/` and `common/qt/`.

---

## 4. Cross-cutting couplings to sever BEFORE the physical move

The "common" Qt layer currently reaches into Linux `/proc` readers in **3 places**,
which silently no-op on Windows (return `None` on `OSError`). These couplings
must be severed before the split — otherwise `common/qt/` would import from
`kde/`, breaking the boundary.

### Coupling #1 — `qt/desktop/desktop_builder.py:44`

```python
from infrastructure.system.proc import parent_pid, process_name
```

Hardcoded Linux `/proc` readers injected into `ForegroundInspector`. The common
builder hardcodes Linux process-tree readers.

**Fix:** make `parent_of`/`process_name_of` injectable parameters of
`build_desktop`. `ForegroundInspector.__init__` already accepts them with
`lambda` defaults. Linux passes `kde/proc.py`'s functions; Windows passes its
own (or no-ops, since `descends_from_launcher` isn't meaningful there).

This is the **only** `infrastructure.system` import from the common Qt layer's
entry point — removing it is the highest-value fix.

### Coupling #2 — `qt/desktop/deferred_hide.py:14`

```python
from infrastructure.system.window_manager import expand_pid_tree
```

Already sidestepped by Windows (injects `TimedLaunchHide`).

**Fix:** move `DeferredHide` to `kde/qt/desktop/deferred_hide.py` outright.
The common `build_desktop` already accepts an injected `deferred_hide` and only
falls back to `DeferredHide` via a **lazy local import** precisely so platforms
without `QtDBus` can avoid it. Making that fallback KDE-only is exactly the split.

### Coupling #3 — `qt/desktop/tile_bar.py:33-42`

```python
def _get_ppid(pid):
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except (OSError, ValueError):
        return None
```

Inline `/proc` read, used by `resolve_recall_trigger`. On Windows returns `None`.

**Fix:** inject a `parent_of` callable into `TileBar` (or move recall-trigger
resolution into the lifecycle coordinator, which already has `parent_of`), and
move `_get_ppid` to `kde/proc.py`. This is the only `/proc` read not behind an
injected port.

### Coupling #4 — `windows/app_pinning.py:27`

```python
class WindowsAppPinning(DesktopAppPinning):
    from infrastructure.system.app_pinning import DesktopAppPinning
```

Windows class inherits from a KDE/XDG class. If `DesktopAppPinning` moves to
`kde/app_pinning.py`, Windows would import from `kde/` — breaking the boundary.

**Fix:** extract the shared `.desktop` persistence mechanics
(`_next_order`, `_unique_path`, `_slugify`, `_write_desktop` usage, the `unpin`
method) into a **common base** in `common/catalog/pinning_base.py`. Both
`kde/DesktopAppPinning` and `windows/WindowsAppPinning` subclass that common
base. The KDE-specific part is the XDG source-`.desktop` *lookup*; the
Windows-specific part is the Win32 version-info *resolution* — both belong in
their own platform package, sharing the persistence mechanics.

---

## 5. Composition roots after the split

### `src/main.py` (Linux/KDE)

Imports only from:
- `infrastructure.kde.*` — backends (window_manager, power, volume, brightness,
  wallpaper, notifications, network_manager, app_manager, proc, gamepad_watcher,
  mangohud, app_pinning, app_discovery, log_viewer_launcher)
- `infrastructure.common.*` — shared (build_desktop, overlays, SoundFeedback,
  app_config, QtScheduler, SystemTray, icons, i18n)
- `domain.*` + `application`

No `infrastructure.system` / `infrastructure.input` / `infrastructure.mangohud`
imports remain.

Passes `parent_of=parent_pid`, `process_name_of=process_name` (from `kde.proc`)
to `build_desktop`. Uses default `surface=LayerShellSurface` and
`deferred_hide=DeferredHide` (lazy-imported from `kde.qt`).

### `src/infrastructure/windows/windows_main.py`

Imports only from:
- `infrastructure.windows.*` — backends
- `infrastructure.common.*` — shared
- `domain.*` + `application`

After the split it touches **no KDE/Linux code** (its only current reach into
`infrastructure.system` is `app_config`, which becomes `common/catalog/app_config`).

Passes `surface=WindowsDesktopSurface`, `deferred_hide=TimedLaunchHide(...)`,
and (new, after coupling #1 fix) `parent_of=`/`process_name_of=` (no-ops or
Windows-specific) to the **common** `build_desktop`.

### `src/application.py`

Already fully platform-agnostic — imports only `domain.*`. Both roots
instantiate it identically. **No changes.**

---

## 6. Qt overlays — common or KDE-specific?

**Common.** Every overlay calls `promote_overlay_surface(...)` from
`qt/ui/top_surface.py`, which is a **platform dispatcher**:

- wayland → `make_layer_surface` from `layer_shell.py` (KDE-only, moves to `kde/`)
- windows → `Qt.WindowStaysOnTopHint`
- else → ordinary window

The KDE-specific mechanism (`layer_shell.py`) is the only KDE bit, already
isolated in one file that's a safe no-op off-Wayland. So:

- `qt/ui/top_surface.py` → `common/qt/ui/top_surface.py` (dispatcher stays common)
- `qt/ui/layer_shell.py` → `kde/qt/ui/layer_shell.py` (KDE impl moves)
- All overlays → `common/qt/overlays/` unchanged

The same pattern applies to `DesktopSurface`: Protocol → `common/qt/desktop/surface.py`;
`LayerShellSurface` → `kde/qt/desktop/surface.py`; `WindowsDesktopSurface` stays
in `windows/qt/desktop_surface.py`.

---

## 7. Migration order (lowest risk first)

1. **Cleanup legacy** — delete/marking `windows/shell.py`, `windows/desktop_shell.py`,
   stale `windows/__init__.py` exports. No behavior change; removes confusion.

2. **Fix coupling #1** — make `parent_of`/`process_name_of` injectable in
   `build_desktop`. Mechanical; `ForegroundInspector` already accepts them.
   Linux passes `kde/proc.py` functions; Windows passes no-ops.

3. **Fix coupling #3** — inject `parent_of` into `TileBar` (or move
   recall-trigger resolution to the lifecycle coordinator).

4. **Fix coupling #4** — extract common pinning base so
   `DesktopAppPinning` and `WindowsAppPinning` share a common base, not a
   KDE→Windows inheritance.

5. **Physical move** — relocate files to `kde/` and `common/` per §3. Update
   both composition roots' imports. `infrastructure/system/` disappears.

6. **Verify** — run full test suite on both platforms; smoke-test both
   composition roots.

Coupling #2 is implicitly resolved by step 5 (the file moves to `kde/`).

---

## 8. Risk assessment

- **Couplings #1, #3** — low risk. Mechanical injection; the receiving classes
  already accept callables with sensible defaults. Tests mock these anyway.
- **Coupling #4** — medium risk. Refactoring inheritance hierarchy; needs care
  that both subclasses still pass `test_app_pinning.py` / `test_app_config.py`.
- **Physical move** — low risk per file (just `git mv` + import updates), but
  high volume (~25 files). Best done as a single commit after the coupling
  fixes land. Test suite covers both platforms — the Linux `/proc` mocks in
  tests will surface any leftover coupling.
- **`windows/shell.py` deletion** — verify nothing else imports it first
  (`grep -r "WindowsShellManager\|shell.py" src/ tests/`).

---

## 9. Verification checklist after migration

- [ ] `grep -r "from infrastructure.system" src/` returns 0 matches
- [ ] `grep -r "from infrastructure.input" src/` returns 0 matches
- [ ] `grep -r "from infrastructure.mangohud" src/` returns 0 matches
- [ ] `grep -r "from infrastructure.kde" src/infrastructure/windows/` returns 0 matches
- [ ] `grep -r "from infrastructure.windows" src/infrastructure/kde/` returns 0 matches
- [ ] `grep -rn "/proc/" src/infrastructure/common/` returns 0 matches
- [ ] `pytest tests/ -q` passes on both platforms
- [ ] `./kasual.sh` smoke-test on Linux
- [ ] `./kasual.ps1` smoke-test on Windows
