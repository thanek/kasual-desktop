# Kasual Desktop 🎮

Kasual Desktop is an interactive, graphical "launcher/desktop" interface, designed to be operated using a controller (gamepad). The project combines application management, system overlays, and advanced input handling to create a cohesive "console-like" environment for Linux systems. It is specifically designed to run within the **KDE Plasma 6** environment.

## ✨ Key Features

- **Gamepad-First Interface**: Full controller navigation support (via `evdev` and `gamepad_watcher`).
- **Dynamic Launcher**: Manage applications using a simple `apps.yaml` configuration file.
- **Overlay System**: Advanced support for system overlays (e.g., notifications, menus) that run on top of application windows.
- **System Integration**: Support for window management (KWin/Wayland) and integration with system notification services.
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
- **Python 3.10+** with `venv`.
- **System Qt + PyQt6 (not pip's bundled PyQt6).** The layer-shell integration
  plugin is version-locked to the system Qt build, so Kasual Desktop must run against the
  distribution's PyQt6 — pip's self-contained Qt cannot load it.

  On **Debian/Ubuntu**:
  ```bash
  sudo apt install python3-venv python3-dev \
      python3-pyqt6 python3-pyqt6.sip python3-pyqt6.qtmultimedia \
      layer-shell-qt qt6-wayland
  ```

  On **Arch Linux**:
  ```bash
  sudo pacman -S python python-pyqt6 layer-shell-qt qt6-wayland
  ```

  Other distros: install the equivalent of `python3-pyqt6` (incl. its
  `QtMultimedia` module), `layer-shell-qt` (LayerShellQt) and `qt6-wayland`.

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

1. Clone the repository:
   ```bash
   git clone https://github.com/thanek/kasual-desktop.git
   cd kasual-desktop
   ```

2. Create a virtual environment **with access to the system PyQt6**:
   ```bash
   python3 -m venv --system-site-packages venv
   source venv/bin/activate
   ```

3. Install the remaining (pure-Python) dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the application:
   ```bash
   ./kasual.sh
   ```
   `kasual.sh` selects the Wayland platform and the layer-shell integration and
   forces the system PyQt6 (`QT_QPA_PLATFORM=wayland`,
   `QT_WAYLAND_SHELL_INTEGRATION=layer-shell`, `PYTHONNOUSERSITE=1`).

## ⚙️ Configuration

The application is configured via a `apps.yaml` file located in the root directory. You can add or remove applications from your launcher by editing this file.

```yaml
apps:
  - name: "Browser"
    command: "firefox"
    icon: "browser_icon.png"
  - name: "Terminal"
    command: "konsole"
    icon: "terminal_icon.png"
```

## 📜 License

Kasual Desktop is free software licensed under the **GNU General Public License v3.0 or later**. See [LICENSE](LICENSE) for details.

## 🎵 Credits

This project uses the **Classic UI SFX** pack by `Chhoff`, which can be found [here](https://chhoffmusic.itch.io/classic-ui-sfx).

## 🤖 AI notice

This project was developed with the assistance of AI.
