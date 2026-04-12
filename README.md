# Kasual 🎮

Kasual is an interactive, graphical "launcher/desktop" interface, designed to be operated using a controller (gamepad). The project combines application management, system overlays, and advanced input handling to create a cohesive "console-like" environment for Linux systems. It is specifically designed to run within the **KDE Plasma 6** environment.

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

Ensure you have Python installed on your system.

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/thanek/kasual.git
   cd kasual
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
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

Kasual is free software licensed under the **GNU General Public License v3.0 or later**. See [LICENSE](LICENSE) for details.

## 🤖 AI notice

This project was developed with the assistance of AI.
