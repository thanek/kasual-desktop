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

- **KDE Plasma 6** (Wayland or X11)
- **Python 3.10+**
- **pip** and **venv** (usually bundled with Python)
- System libraries required by PyQt6:

  On **Debian/Ubuntu**:
  ```bash
  sudo apt install python3-venv python3-dev libgl1 libegl1 libxcb-cursor0
  ```

  On **Fedora**:
  ```bash
  sudo dnf install python3-devel mesa-libGL mesa-libEGL libxcb
  ```

  On **Arch Linux**:
  ```bash
  sudo pacman -S python mesa libxcb
  ```

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
   git clone https://github.com/thanek/kasual.git
   cd kasual
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the application:
   ```bash
   python src/main.py
   ```

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
