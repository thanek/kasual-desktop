# Kasual Desktop 🎮

Kasual Desktop is an interactive, graphical "launcher/desktop" interface, designed to be operated using a controller (gamepad). The project combines application management, system overlays, and advanced input handling to create a cohesive "console-like" environment for Linux systems. It is specifically designed to run within the **KDE Plasma 6** environment.

## ✨ Key Features

- **Gamepad-First Interface**: Full controller navigation support (via `evdev` and `gamepad_watcher`).
- **Dynamic Launcher**: Manage applications with simple `.desktop` files in `~/.config/kasual-desktop/apps/`.
- **Overlay System**: Advanced support for system overlays (e.g., notifications, menus) that run on top of application windows.
- **System Integration**: Support for window management (KWin/Wayland) and integration with system notification services.
- **In-Game HUD Toggle**: Show or hide the [MangoHud](https://github.com/flightlessmango/MangoHud) performance overlay for games, straight from the controller menu (see [In-Game HUD](#-in-game-hud-mangohud)).
- **Advanced Audio System**: Support for system sounds and audio feedback.
- **Seamless KDE Integration**: Optimized for use within the KDE Plasma ecosystem.

## 🛠️ Tech Stack

- **Python**
- **PyQt6**
- **KDE Plasma Ecosystem**

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

## ⚙️ Configuration

### First run (provisioning)

On its **first launch**, Kasual Desktop shows a provisioning dialog that lets you
pick from a curated starter set — File Browser and YouTube, plus Steam and Heroic
when they are installed — to seed your app catalog.

Completing it writes a marker at `~/.config/kasual-desktop/.provisioned`, so the
dialog does not reappear on later launches (even if you pick nothing, or later
remove every tile). To run provisioning again:

```sh
./kasual.sh --provisioning          # remove the marker, then relaunch
# — or remove it manually and start normally:
rm ~/.config/kasual-desktop/.provisioned
```

To add or customize tiles yourself, edit the `.desktop` files directly.

### App tiles

Launcher tiles are defined by freedesktop **`.desktop`** files placed in:

```
~/.config/kasual-desktop/apps/        # or $XDG_CONFIG_HOME/kasual-desktop/apps/
```

One file per app. Create the apps directory and add a `.desktop` file using the
standard `[Desktop Entry]` section plus a few `X-Kasual-*` extensions:

```sh
mkdir -p ~/.config/kasual-desktop/apps
$EDITOR ~/.config/kasual-desktop/apps/steam.desktop
```

For example:

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
| `Exec` | Command + arguments (required; `%`-field codes are stripped) |
| `Icon` | Themed icon name, used when `X-Kasual-Icon` is absent |
| `Categories` | freedesktop categories; include `Game` to mark the tile as a game (enables the [in-game HUD toggle](#-in-game-hud-mangohud)) |
| `X-Kasual-Icon` | [qtawesome](https://github.com/spyder-ide/qtawesome) glyph name (takes precedence over `Icon`) |
| `X-Kasual-Color` | Tile background colour (default `#2e3440`) |
| `X-Kasual-RecallMenuTrigger` | `BTN_MODE_CLICK` (default) or `BTN_MODE_HOLD_1S` |
| `X-Kasual-HideGraceMs` | Grace period before hiding the Desktop after launch (default `0`) |
| `X-Kasual-Env` | `KEY=val;KEY2=val2` — merged into the launched process environment |
| `X-Kasual-Order` | Integer sort key (default last; ties broken by filename) |

`NoDisplay=true`, `Hidden=true` and non-`Application` entries are ignored.

> **Bundled apps (`yt`, `file_browser`):** their launcher scripts live in the
> cloned repo, so `Exec` must be an **absolute** path (e.g.
> `Exec=/home/you/kasual-desktop/apps/yt/yt.sh`) — relative paths do not resolve
> from `~/.config`.

## 🎚️ In-Game HUD (MangoHud)

Over a running **game**, the Home Overlay (opened with `BTN_MODE`) offers an
**Enable HUD / Disable HUD** entry that shows or hides the
[MangoHud](https://github.com/flightlessmango/MangoHud) performance overlay. The
label always reflects the current state, so you know whether a press will turn
it on or off.

### Requirements

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

### When the toggle appears

Only over a **game** — never on the bare desktop or over ordinary apps. A
foreground counts as a game when either:

- its process descends from a known launcher/runtime — **Steam, Heroic, Lutris,
  Gamescope, Wine/Proton, Bottles** — so games launched through them are
  detected automatically; or
- its tile's `.desktop` declares **`Categories=Game`** — use this for standalone
  game tiles that are *not* started through one of those launchers.

### How toggling works

The toggle comments/uncomments the `no_display` line in
`~/.config/MangoHud/MangoHud.conf`. MangoHud watches this file (via `inotify`)
and reloads it on every change, so the HUD appears or disappears **immediately**
— on already-running games as well as newly-launched ones.

> **Caveat:** a per-game **FPS limit set in Steam** injects
> `MANGOHUD_CONFIG=...,no_display=1`. MangoHud re-applies `MANGOHUD_CONFIG` on
> each reload (it takes precedence over the file), so that override re-wins and
> can keep the HUD hidden regardless of this toggle.

## 📜 License

Kasual Desktop is free software licensed under the **GNU General Public License v3.0 or later**. See [LICENSE](LICENSE) for details.

## 🎵 Credits

This project uses the **Classic UI SFX** pack by `Chhoff`, which can be found [here](https://chhoffmusic.itch.io/classic-ui-sfx).

## 🤖 AI notice

This project was developed with the assistance of AI.
