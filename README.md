# Kasual Desktop 🎮

Kasual Desktop is an interactive, graphical "launcher/desktop" interface, designed to be operated using a controller (gamepad). The project combines application management, system overlays, and advanced input handling to create a cohesive "console-like" environment.

It runs on two platforms from a single shared core:

- **Linux / KDE Plasma 6** — the original target, rendering its UI as
  `wlr-layer-shell` overlays above applications (including fullscreen games).
- **Windows 10/11** — a newer port that runs the *same* UI as a desktop surface,
  currently a development build run from source.

The cross-platform domain logic and Qt UI are shared; only genuinely OS-specific
pieces (window management, app launching, gamepad, audio, notifications, the
in-game HUD, …) live behind platform adapters. See [Architecture](#-architecture).

## ✨ Key Features

- **Gamepad-First Interface**: Full controller navigation (Linux via `evdev`, Windows via `pygame`/XInput).
- **Dynamic Launcher**: Manage applications with simple `.desktop` files in your per-user config directory.
- **Overlay System**: Advanced support for system overlays (e.g., notifications, menus) that run on top of application windows.
- **System Integration**: Window management (KWin/Wayland on Linux, Win32 on Windows), system notifications, network, audio and brightness controls.
- **First-Run Onboarding**: A provisioning picker seeds your catalog from installed apps (curated starter set on Linux; Start-Menu scan on Windows).
- **In-Game HUD Toggle**: Show or hide the performance overlay for games straight from the controller menu — **[MangoHud](https://github.com/flightlessmango/MangoHud)** on Linux, **[RivaTuner Statistics Server](https://www.guru3d.com/page/rivatuner-rtss-overlay/)** (MSI Afterburner) on Windows. See [In-Game HUD](#-in-game-hud).
- **Advanced Audio System**: System sounds and audio feedback.

## 🏗️ Architecture

Kasual Desktop separates a platform-agnostic **core** from thin **platform
adapters**:

- `src/domain/` — pure problem-domain logic (no Qt, no I/O, no OS specifics).
- `src/infrastructure/common/` — the shared Qt UI (Desktop, overlays, tray) and
  cross-platform config, reused on both platforms via a `DesktopSurface` seam.
- `src/infrastructure/kde/` — Linux/KDE adapters (layer-shell, KWin, MangoHud, …).
- `src/infrastructure/windows/` — Windows adapters (Win32 WM, Core Audio, WinRT
  notifications, RTSS HUD, …).
- `src/main.py` — Linux entry point; `src/windows_main.py` — Windows entry point.

The Windows adapters never import from `kde/` (and vice-versa); the core never
imports either.

## 🛠️ Tech Stack

- **Python 3.11+** (uses `enum.StrEnum`)
- **PyQt6** + **qtawesome**, **PyQt6-WebEngine** (bundled YouTube app)
- **Linux**: KDE Plasma / KWin, `wlr-layer-shell` (LayerShellQt), `evdev`, `python-xlib`
- **Windows**: `pywin32` (Win32 API), `comtypes` (Core Audio), `psutil`, Microsoft `winrt-*` (Action Center notifications), `pygame` (gamepad)

---

# 🐧 Linux (KDE Plasma 6)

## 🚀 Getting Started

### Prerequisites

- **KDE Plasma 6 on Wayland.** Kasual Desktop renders its UI as `wlr-layer-shell`
  surfaces (overlays that sit above applications, including fullscreen games).
  This requires a compositor that supports the protocol — **KWin (KDE) or another
  wlroots-based compositor**. GNOME/Mutter does **not** support `wlr-layer-shell`.
- **Python 3.11+** (the codebase uses `enum.StrEnum`).
- **System Qt + PyQt6 (not pip's bundled PyQt6).** The layer-shell integration
  plugin is version-locked to the system Qt build, so Kasual Desktop must run against the
  distribution's PyQt6 — pip's self-contained Qt cannot load it. 

  On **Debian/Ubuntu**:
  ```bash
  sudo apt install python3-pyqt6 python3-pyqt6.sip python3-pyqt6.qtmultimedia \
      python3-pyqt6.qtwebengine python3-qtawesome python3-evdev python3-xlib \
      layer-shell-qt qt6-wayland
  ```

  On **Arch Linux**:
  ```bash
  sudo pacman -S python python-pyqt6 python-pyqt6-webengine python-qtawesome \
      python-evdev python-xlib layer-shell-qt qt6-wayland
  ```

  Other distros: install the equivalent of `python3-pyqt6` (incl. its
  `QtMultimedia` and `QtWebEngine` modules), `python3-qtawesome`, `python3-evdev`,
  `python3-xlib`, `layer-shell-qt` (LayerShellQt) and `qt6-wayland`. `QtWebEngine`
  is required by the bundled YouTube app.

### Gamepad permissions

Kasual Desktop reads gamepad input directly via `evdev`, which requires access to `/dev/input/*` devices. Without this, the application will not detect any controller.

Add your user to the `input` group:

```bash
sudo usermod -aG input $USER
```

Then log out and log back in (or reboot) for the change to take effect. You can verify it worked with:

```bash
groups | grep input
```

Alternatively, you can create a udev rule for a more targeted approach:

```bash
echo 'SUBSYSTEM=="input", GROUP="input", MODE="0664"' | sudo tee /etc/udev/rules.d/99-kasual-desktop.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### Installation

**From a package (recommended).** Grab the `.deb` or `.rpm` from the
[GitHub Releases](https://github.com/thanek/kasual-desktop/releases) page and
install it — the dependencies above are pulled in automatically:

```bash
sudo apt install ./kasual-desktop_*_all.deb          # Debian/Ubuntu
sudo dnf install ./kasual-desktop-*.noarch.rpm        # Fedora/openSUSE
sudo pacman -U ./kasual-desktop-*-any.pkg.tar.zst     # Arch Linux
```

This installs the launcher as `kasual-desktop` (also in the application menu);
the bundled File Browser and YouTube apps ship inside the same package.

**From source (development).**

1. Clone the repository:
   ```bash
   git clone https://github.com/thanek/kasual-desktop.git
   cd kasual-desktop
   ```

2. Install the system dependencies (and the dev/test stack):
   ```bash
   ./install.sh          # apt/dnf/pacman, auto-detected
   ```

3. Run the application:
   ```bash
   ./kasual.sh
   ```
   `kasual.sh` selects the Wayland platform and the layer-shell integration
   (`QT_QPA_PLATFORM=wayland`, `QT_WAYLAND_SHELL_INTEGRATION=layer-shell`) and
   forces the system PyQt6 via `PYTHONNOUSERSITE=1` — a pip-installed PyQt6 in
   `~/.local` ships a newer Qt without the layer-shell plugin, which otherwise
   fails with *"No shell integration named layer-shell found"*.

### Building packages

All three formats are produced from a single descriptor (`nfpm.yaml`) by
[`nfpm`](https://nfpm.goreleaser.com/). The package version comes from the git
tag (e.g. `v0.2.0` → `0.2.0`), falling back to `pyproject.toml` when there is no
tag; the same value is baked into the app so it reports its own version at
runtime. The only build-time tools needed are `make`, `rsync` and `nfpm` (PyQt6
etc. are *runtime* deps, not required to build).

1. Install `nfpm`. On **Debian/Ubuntu** use the goreleaser apt repo:
   ```bash
   echo 'deb [trusted=yes] https://repo.goreleaser.com/apt/ /' \
     | sudo tee /etc/apt/sources.list.d/goreleaser.list
   sudo apt update && sudo apt install nfpm
   ```
   On **Arch**: `nfpm` is in the AUR (`yay -S nfpm-bin`). Any platform with Go:
   `go install github.com/goreleaser/nfpm/v2/cmd/nfpm@latest`. See the
   [nfpm install docs](https://nfpm.goreleaser.com/docs/install/) for other options.

2. Build:
   ```bash
   make deb      # -> dist/kasual-desktop_<version>_all.deb
   make rpm      # -> dist/kasual-desktop-<version>.noarch.rpm
   make arch     # -> dist/kasual-desktop-<version>-1-any.pkg.tar.zst
   make all      # all three
   make clean    # remove build/ and dist/
   ```

   `make` first stages the runnable tree under `build/stage/` (what actually
   gets packaged — see `make stage`), then runs `nfpm` for each format. Output
   lands in `dist/`.

Publishing a GitHub Release triggers `.github/workflows/release.yml`, which runs
`make all` on a clean runner and attaches the resulting packages to the release.

---

# 🪟 Windows (10 / 11)

The Windows port runs the same shared UI as a desktop surface (no layer-shell —
that is Linux-only). It is currently a **development build run from source**;
there is no Windows installer yet.

## 🚀 Getting Started

### Prerequisites

- **Windows 10 or 11.**
- **Python 3.11+** (3.12 recommended). Unlike Linux, Windows uses pip's PyQt6
  (there is no layer-shell version lock), installed into a virtual environment.
- **A controller** recognised by Windows (Xbox, PlayStation, 8BitDo, …). Input is
  read cooperatively via `pygame`/XInput — no exclusive grab.
- **(Optional, for the HUD)** RivaTuner Statistics Server, typically installed
  with **MSI Afterburner**. See [In-Game HUD](#-in-game-hud).

### Installation

1. Clone the repository and create a virtual environment:
   ```powershell
   git clone https://github.com/thanek/kasual-desktop.git
   cd kasual-desktop
   python -m venv venv
   ```

2. Install the cross-platform and Windows-only dependencies into that venv:
   ```powershell
   .\venv\Scripts\pip install -r requirements.txt -r requirements-windows.txt
   ```
   `requirements-windows.txt` adds the Windows adapters' deps: `pywin32` (Win32
   window/app/brightness), `comtypes` (Core Audio volume), `psutil` (network /
   process discovery) and Microsoft's `winrt-*` projection (Action Center
   notifications).

3. Run the application:
   ```powershell
   .\kasual.ps1
   ```
   `kasual.ps1` clears the Python bytecode cache (handy during development) and
   launches `src\windows_main.py` with the venv's interpreter. Pass
   `--provisioning` to re-trigger first-run onboarding (see below).

### Tests

```powershell
.\test.ps1            # runs the pytest suite with the venv interpreter
```

---

## ⚙️ Configuration

The configuration model is shared across platforms; only the base directory
differs:

| | Linux | Windows |
|---|---|---|
| Config root | `~/.config/kasual-desktop` (or `$XDG_CONFIG_HOME`) | `%APPDATA%\kasual-desktop` |
| App tiles | `…/apps/*.desktop` | `…\apps\*.desktop` |
| Provisioning marker | `…/.provisioned` | `…\.provisioned` |

### First run (provisioning)

On its **first launch**, Kasual Desktop shows a provisioning dialog that seeds
your app catalog:

- **Linux** — a curated starter set (File Browser and YouTube, plus Steam and
  Heroic when installed).
- **Windows** — a screen-friendly list discovered by scanning the Start Menu for
  `.lnk` shortcuts (uninstallers, help/website links and duplicates filtered out).

Completing it writes a `.provisioned` marker in the config root, so the dialog
does not reappear (even if you pick nothing, or later remove every tile). To run
provisioning again:

```sh
./kasual.sh --provisioning          # Linux
```
```powershell
.\kasual.ps1 --provisioning         # Windows
```

Either removes the marker and relaunches; you can also delete the marker file
manually and start normally.

### App tiles

Launcher tiles are defined by freedesktop **`.desktop`** files placed in the
`apps/` directory under your config root (see the table above) — the **same
format on both platforms**. One file per app, using the standard
`[Desktop Entry]` section plus a few `X-Kasual-*` extensions:

```ini
[Desktop Entry]
Type=Application
Name=Steam
Exec=steam steam://open/bigpicture
X-Kasual-Icon=fa5b.steam            # qtawesome glyph (preferred)
X-Kasual-Color=#1b2838              # tile colour
X-Kasual-RecallMenuTrigger=BTN_MODE_HOLD_1S   # or BTN_MODE_CLICK (default)
X-Kasual-HideGraceMs=500            # delay before hiding KD after launch (ms)
X-Kasual-Order=10                   # tile order (ascending; ties → filename)
X-Kasual-Env=MANGOHUD=1;FOO=bar     # extra environment variables (optional)
```

| Key | Meaning |
|---|---|
| `Name` | Tile label (required) |
| `Exec` | Command + arguments (required; `%`-field codes are stripped). On Windows this is typically the path to a `.lnk` or executable. |
| `Icon` | Themed icon name, used when `X-Kasual-Icon` is absent |
| `Categories` | freedesktop categories; include `Game` to mark the tile as a game (enables the [in-game HUD toggle](#-in-game-hud)) |
| `X-Kasual-Icon` | [qtawesome](https://github.com/spyder-ide/qtawesome) glyph name (takes precedence over `Icon`) |
| `X-Kasual-Color` | Tile background colour (default `#2e3440`) |
| `X-Kasual-RecallMenuTrigger` | `BTN_MODE_CLICK` (default) or `BTN_MODE_HOLD_1S` |
| `X-Kasual-HideGraceMs` | Grace period before hiding the Desktop after launch (default `0`) |
| `X-Kasual-Env` | `KEY=val;KEY2=val2` — merged into the launched process environment |
| `X-Kasual-Order` | Integer sort key (default last; ties broken by filename) |

`NoDisplay=true`, `Hidden=true` and non-`Application` entries are ignored.

> **Bundled apps (`yt`, `file_browser`, Linux):** their launcher scripts live in
> the cloned repo, so `Exec` must be an **absolute** path (e.g.
> `Exec=/home/you/kasual-desktop/apps/yt/yt.sh`) — relative paths do not resolve
> from `~/.config`.

---

## 🎚️ In-Game HUD

Over a running **game**, the Home Overlay (opened with `BTN_MODE`) offers an
**Enable HUD / Disable HUD** entry that shows or hides the performance overlay.
The label always reflects the current state, so you know whether a press will
turn it on or off. The backend differs per platform:

| | Linux | Windows |
|---|---|---|
| Overlay | [MangoHud](https://github.com/flightlessmango/MangoHud) | [RivaTuner Statistics Server](https://www.guru3d.com/page/rivatuner-rtss-overlay/) (MSI Afterburner) |
| Mechanism | edits `no_display` in `MangoHud.conf` | flips RTSS's runtime OSD-visible flag |
| Gated on | the config file existing | RTSS running |

### When the toggle appears

Only over a **game** — never on the bare desktop or over ordinary apps. How a
foreground is recognised as a game differs per platform:

- **Linux** — its process descends from a known launcher/runtime (e.g. **Steam,
  Heroic, Lutris, Gamescope, Wine/Proton, Bottles**), so games launched through
  them are detected automatically; or its tile declares **`Categories=Game`**
  (use this for standalone game tiles not started through a launcher).
- **Windows** — **RTSS itself is the authority**: the toggle appears when RTSS is
  actively rendering its OSD into the foreground process (i.e. a hooked 3D app).
  No launcher list or `Categories=Game` is needed — if RTSS is drawing on the
  game, Kasual offers the toggle.

### Linux — MangoHud

**Requirements**

- **MangoHud installed** — the Vulkan/OpenGL overlay (v0.8.x recommended). The
  apt package is often too old; building from source may be necessary.
- **A MangoHud config file at `~/.config/MangoHud/MangoHud.conf`.** Its presence
  gates the whole feature — with no file, the toggle never appears (an empty
  file is enough). This is the file Kasual edits to show/hide the HUD.
- **MangoHud actually injected into your games**, via any of:
  - a global `MANGOHUD=1` in your environment (covers Vulkan games),
  - `mangohud %command%` in a game's **Steam** launch options,
  - the **Heroic**/**Lutris** "MangoHud" wrapper toggle,
  - or per-tile `X-Kasual-Env=MANGOHUD=1` in the app's `.desktop`.

  Note: `MANGOHUD=1` alone only injects into **Vulkan** apps; OpenGL games need
  the `mangohud` wrapper (`LD_PRELOAD`).

**How toggling works** — the toggle comments/uncomments the `no_display` line in
`~/.config/MangoHud/MangoHud.conf`. MangoHud watches this file (via `inotify`)
and reloads it on every change, so the HUD appears or disappears **immediately**
— on already-running games as well as newly-launched ones.

> **Caveat:** a per-game **FPS limit set in Steam** injects
> `MANGOHUD_CONFIG=...,no_display=1`. MangoHud re-applies `MANGOHUD_CONFIG` on
> each reload (it takes precedence over the file), so that override re-wins and
> can keep the HUD hidden regardless of this toggle.

### Windows — RivaTuner Statistics Server

**Requirements**

- **RTSS running.** It ships with (and is usually launched by) **MSI
  Afterburner**, which drives the OSD through RTSS. RTSS not running → the toggle
  never appears.
- **The OSD configured to show in your games** as you normally would in
  Afterburner/RTSS (monitoring graphs in the On-Screen Display).
- **No administrator rights required.**

**How toggling works** — Kasual calls the `SetFlags` export of RTSS's
`RTSSHooks64.dll` to read and flip the runtime *OSD-visible* flag — the exact
mechanism RTSS's own "Show On-Screen Display On/Off" hotkeys use. The change is
applied live to running games, needs no elevation, and writes no files. It
toggles the *runtime* visibility (like pressing the OSD hotkey) rather than any
persistent profile setting, which is exactly what an in-game toggle wants.

## 📜 License

Kasual Desktop is free software licensed under the **GNU General Public License v3.0 or later**. See [LICENSE](LICENSE) for details.

## 🎵 Credits

This project uses the **Classic UI SFX** pack by `Chhoff`, which can be found [here](https://chhoffmusic.itch.io/classic-ui-sfx).

## 🤖 AI notice

This project was developed with the assistance of AI.
