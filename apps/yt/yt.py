import sys
import time
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineScript
from evdev import InputDevice, ecodes, list_devices
import threading
from evdev import UInput, ecodes as e

from adblocker import AdBlocker, JS_PATCH

# Nazwa wirtualnego pada tworzonego przez kasual/gamepad_manager.py.
# Czytamy z niego zamiast z fizycznego urządzenia, bo:
#   1. Fizyczny pad jest grabowany przez desktop (ekskluzywny dostęp).
#   2. BTN_MODE jest filtrowany przez desktop – YT go nie widzi.
VIRTUAL_DEVICE_NAME = "kasual-vpad"
PHYSICAL_DEVICE_NAME = '8BitDo Ultimate Wireless / Pro 2 Wired Controller'


def find_pad(names: list[str], timeout: float = 10.0) -> InputDevice:
    """Waits for gamepad with given name appearance, max timeout seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for path in list_devices():
            try:
                d = InputDevice(path)
                if d.name in names:
                    return d
                d.close()
            except Exception:
                pass
        time.sleep(0.2)
    raise RuntimeError(f"Pad not found among: {names}")

ui = UInput()


def press(key):
    ui.write(e.EV_KEY, key, 1)
    ui.write(e.EV_KEY, key, 0)
    ui.syn()


class PadListener(threading.Thread):
    def __init__(self, gamepad: InputDevice, window=None):
        super().__init__(daemon=True)
        self._gamepad = gamepad
        self._window = window

    def run(self):
        for ev in self._gamepad.read_loop():
            if self._window is not None and not self._window.isActiveWindow():
                continue
            if ev.type == ecodes.EV_KEY:
                if ev.value == 1:   # wciśnięcie
                    if ecodes.BTN_SOUTH == ev.code:
                        press(e.KEY_ENTER)
                    elif ecodes.BTN_EAST == ev.code:
                        press(e.KEY_ESC)

            elif ev.type == ecodes.EV_ABS:
                if ev.code == ecodes.ABS_HAT0X:
                    if ev.value == -1:
                        press(e.KEY_LEFT)
                    elif ev.value == 1:
                        press(e.KEY_RIGHT)
                elif ev.code == ecodes.ABS_HAT0Y:
                    if ev.value == -1:
                        press(e.KEY_UP)
                    elif ev.value == 1:
                        press(e.KEY_DOWN)


# ── Entrypoint ─────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    window = QMainWindow()

    profile = QWebEngineProfile("youtube-tv", app)
    profile.setHttpUserAgent(
        "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Version/6.0 TV Safari/537.36"
    )
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
    )

    profile.setUrlRequestInterceptor(
        AdBlocker()
    )
    script = QWebEngineScript()
    script.setName("yt-adblock")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(True)
    script.setSourceCode(JS_PATCH)
    profile.scripts().insert(script)

    page = QWebEnginePage(profile, None)
    view = QWebEngineView()
    view.setPage(page)
    view.setUrl(QUrl("https://www.youtube.com/tv#"))
    window.setCentralWidget(view)
    window.showFullScreen()

    def _start_pad():
        try:
            gamepad = find_pad([VIRTUAL_DEVICE_NAME, PHYSICAL_DEVICE_NAME])
            PadListener(gamepad, window=window).start()
        except RuntimeError as exc:
            print(f"Warning: gamepad not found — {exc}", file=sys.stderr)

    threading.Thread(target=_start_pad, daemon=True).start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
