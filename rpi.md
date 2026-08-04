# Kasual Desktop on Raspberry Pi OS (labwc / wayfire) — implementation plan

## Context

Raspberry Pi OS (Pi 4/5, Trixie) renders its desktop on **labwc**, a wlroots
compositor with no IPC CLI in the manner of `swaymsg` / `hyprctl`. KD lands there
in `Compositor.UNKNOWN` → `NullWindowManager`: it starts and renders, but sees no
windows, switches no applications and minimizes nothing on the way back to Home
(README, the "Other wlroots (e.g. labwc) | Partial" row). Older Raspberry Pi OS
releases use wayfire — the same gap.

The only channel through which labwc and wayfire hand out the window list and
accept commands (`activate`, `close`, `set_minimized`) is the Wayland protocol
**`zwlr_foreign_toplevel_management_v1`** — the same one the `wf-panel-pi`
taskbar is built on. No Debian/Raspberry Pi OS package ships Python bindings or a
CLI for it (`pywayland`, `wlrctl`, `lswt` are all absent from the repos), and KD
deliberately has no pip dependencies. So the backend speaks the raw Wayland
protocol over its own socket, alongside Qt's connection.

The code is written blind — no hardware — so every piece has to be testable
without a compositor: the protocol codec as pure functions, the client against a
`socketpair()`, the window mapping against a fake proxy.

Outcome: KD on Raspberry Pi OS with full window switching, the wallpaper
inherited from the Raspberry Pi desktop, a verified package list, and a
behavioral scenario ready to run once the hardware is at hand.

## An accepted limitation: the window PID

`zwlr_foreign_toplevel_management_v1` carries no PID — it gives `app_id` and a
title. `Window.pid` drives a fair amount of KD (`external_windows`,
`is_game_pid`, icons, `minimize_windows_for_pids`). The answer: resolve the PID
heuristically from `/proc` by `app_id` (`comm`, the basename of `exe`,
`cmdline[0]`, and the reverse-DNS variant `org.gnome.Nautilus` → `nautilus`),
plus — for the operations that work on a process tree — match `app_id` against
the process names inside the launched application's subtree (`expand_pid_tree`
from `infrastructure/linux/proc.py`). Where nothing can be decided, `pid=0`: the
window shows up on the bar as a dynamic tile and nothing breaks.

## Changes

### 1. A generic Wayland client (DE-independent)

`src/infrastructure/linux/wayland/wire.py` (new) — the wire codec as pure
functions: `encode_request(object_id, opcode, args)`, `iter_messages(buf)`
(returns complete messages plus the remaining buffer), and decoders for the
`uint/int/fixed/string/array/object/new_id` argument types with the 4-byte
padding rule. No I/O — fully covered by tests.

`src/infrastructure/linux/wayland/client.py` (new) — `WaylandClient(QObject)`:
- connects to `$WAYLAND_SOCKET` (an fd) or `$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY`,
- object-ID allocator, `object_id → handler` dispatch table,
- `wl_display.get_registry` + `sync` → `roundtrip()` (blocking, startup only)
  collecting `globals: {interface: (name, version)}`,
- `has_global(iface)`, `bind(iface, version)`,
- a `QSocketNotifier` on readability → event dispatch with no thread and no
  polling,
- handling for `wl_display.error` (log + close) and `delete_id`,
- an idempotent `close()`.

### 2. The foreign-toplevel protocol proxy (wlroots)

`src/infrastructure/wlroots/wayland/foreign_toplevel.py` (new) —
`ForeignToplevelManager`: binds `zwlr_foreign_toplevel_manager_v1` (plus
`wl_seat`, which `activate` requires), accumulates `title`/`app_id`/`state` until
`done`, drops the handle on `closed`, exposes `snapshot() -> list[ToplevelInfo]`
(a frozen dataclass) and an `on_changed` callback. Operations: `activate`,
`close`, `set_minimized`, `unset_minimized`, `set_fullscreen`,
`unset_fullscreen`. Opcodes and the state enum (`maximized=0, minimized=1,
activated=2, fullscreen=3`) as named constants, with a comment pointing at
`wlr-protocols`.

### 3. Resolving the PID

`src/infrastructure/linux/wayland/pid_lookup.py` (new) — `AppIdPidResolver`: a
`/proc` index built lazily (only while some `app_id` is unresolved), an
`app_id → pid` cache invalidated once the process is gone, and matching in
order: exact → prefix (`comm` is kernel-truncated to 15 chars) → substring; ties
go to the oldest process. It reads `/proc` and nothing else, so tests can hand it
a fake tree in `tmp_path`.

### 4. The WindowManager backend

`src/infrastructure/wlroots/wm/base.py` (refactor) — split into
`PollingWindowManager` (cache, emitter, refresh, `_windows_for_pids`,
`raise_self`) and `WlrootsWindowManager(PollingWindowManager)` carrying the
`_run` / `_run_json` CLI helpers. Sway and Hyprland are left untouched (they
import the same name).

`src/infrastructure/wlroots/wm/foreign_toplevel.py` (new) —
`ForeignToplevelWindowManager(PollingWindowManager)`: `_enum_windows()` maps the
proxy snapshot onto `Window` (`id` = the object ID, `resource_class` = `app_id`,
`active` from the `activated` state, `fullscreen` from the state, `pid` from the
resolver); proxy events call `_request_list_refresh()`, so the list is
event-driven and the base timer stays as a safety net.
`minimize_windows_for_pids` → `set_minimized`, `activate_windows_for_pids` →
`unset_minimized` + `activate`, with the `app_id` matching described above
whenever the PID could not be resolved.

### 5. Compositor detection and the factories

`src/infrastructure/linux/compositor.py`:
- `Compositor.LABWC`, `Compositor.WAYFIRE`; detected by the substring `labwc` /
  `wayfire` in `XDG_CURRENT_DESKTOP` or `XDG_SESSION_DESKTOP` (Raspberry Pi OS
  sets `LXDE-pi-labwc` / `LXDE-pi-wayfire`), after the existing Sway/Hyprland
  socket checks,
- `WLROOTS = frozenset({SWAY, HYPRLAND, LABWC, WAYFIRE})` as the single source of
  truth for wlroots-family behaviour,
- `build_window_manager`: LABWC/WAYFIRE/**UNKNOWN** → try
  `ForeignToplevelWindowManager`; a missing global or a failed connection →
  `NullWindowManager` (today's behaviour). This also gives river, labwc outside
  Raspberry Pi, and unrecognised sessions real window management.
- `build_system_wallpaper`: LABWC/WAYFIRE/UNKNOWN → `PcmanfmWallpaper` →
  `StaticFileWallpaper`,
- `build_desktop_surface`: `cede_to_bottom` for the whole of `WLROOTS`.

`src/main.py` — `always_cede` computed from `WLROOTS` instead of the
`(HYPRLAND, SWAY)` pair.

### 6. The Raspberry Pi desktop wallpaper

`src/infrastructure/linux/display/wallpaper.py` — `PcmanfmWallpaper`: glob
`~/.config/pcmanfm/*/desktop-items-*.conf`, then `/etc/xdg/pcmanfm/...`; read the
`wallpaper=` key, skip it when `wallpaper_mode=color`; no hit → `None` (the chain
falls through to `StaticFileWallpaper`).

### 7. Packaging and documentation

- `install.sh` / `nfpm.yaml`: the deb list is already complete for Raspberry Pi
  OS (every package is `arch: any`, hence available on arm64); add labwc/wayfire
  to the package description and a sentence about Raspberry Pi.
- `README.md`: labwc and wayfire rows in the compositor table (Full, WM through
  `wlr-foreign-toplevel-management`, wallpaper from pcmanfm) replacing today's
  "Other wlroots — Partial", plus a **Raspberry Pi OS** section covering
  installation (`sudo apt install ...`), the current state, and the limitations:
  a heuristic window PID, no MangoHud on the Pi, QtWebEngine being heavy
  (YouTube/Netflix), no screensaver service to inhibit in the Raspberry Pi
  session, and X11 sessions (older models) being unsupported.

### 8. Unit tests (no compositor)

- `tests/test_wayland_wire.py` — codec round-trips, string/array padding, framing
  with a buffer cut mid-message.
- `tests/test_wayland_client.py` — the client on a `socket.socketpair()`: a fake
  compositor sends `wl_registry.global`, the test asserts `globals`, `bind`, the
  reaction to `wl_display.error` and to a disconnect.
- `tests/test_foreign_toplevel.py` — the proxy: `toplevel`/`title`/`app_id`/
  `state`/`done`/`closed` → snapshot; the bytes emitted by `activate` / `close` /
  `set_minimized`.
- `tests/test_foreign_toplevel_wm.py` — the mapping onto `Window`, operation
  routing, event-driven refresh (against a fake proxy).
- `tests/test_pid_lookup.py` — the resolver against a fake `/proc` in `tmp_path`.
- `tests/test_compositor.py` — labwc/wayfire detection (including
  `LXDE-pi-labwc`), backend selection, degradation to `NullWindowManager` with no
  global.
- `tests/test_wallpaper_adapters.py` — parsing `desktop-items-*.conf`.

### 9. The behavioral suite

`tests/behavioral/harness/sources/foreign_toplevel.py` (new) — a `WindowSource`
on the same client (its own connection, events rather than polling);
`window_source.py`: `_BACKENDS` += `labwc` / `wayfire`; `requirements.py`: a
labwc/wayfire session requirement. The scenarios (`minimize.py`,
`file_browser.py`) are compositor-neutral — once the source is wired they run on
the Pi unchanged. Noted in `tests/behavioral/PORTING.md`.

## Verification

Without hardware:
- `./test.sh` (or `pytest`) — the whole suite green, including the new test
  files.
- Layering check: `infrastructure/linux/wayland/` imports nothing from
  `wlroots/`, `kde/`, `gnome/`; the domain imports none of them.
- `tools/` gets a small spike script (`tools/spike_foreign_toplevel.py`, after
  `tools/spike_layershell.py`) that prints the toplevel list — one command to run
  on the Pi before starting all of KD.

On the Raspberry Pi (once there is access):
1. `sudo apt install` per the README, `./kasual.sh`.
2. `python3 tools/spike_foreign_toplevel.py` — whether labwc advertises the
   global at all and whether the open windows come with a sensible `app_id`.
3. KD: the tile bar shows open windows; launching an app from a tile, returning
   to Home (the app is minimized), going back in (the app is restored and
   focused), closing a window from the tile menu.
4. The Raspberry Pi desktop wallpaper visible under KD; overlays above
   `wf-panel-pi`.
5. `tests/behavioral/run.py minimize` on a live labwc session.
