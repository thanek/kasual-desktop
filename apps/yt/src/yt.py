import sys
import threading
import time
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineScript

from keyinput import Key, press
from padbackend import (
    ABS_HAT0X, ABS_HAT0Y, BTN_EAST, BTN_SOUTH, PadListener as _PadListener,
    find_pad,
)
from adblocker import AdBlocker, JS_PATCH

# On Linux, Kasual grabs the physical gamepad and exposes a virtual
# "kasual-vpad" device; the app reads from it because the physical pad is
# exclusive-grabbed and BTN_MODE is filtered. On Windows the controller is
# cooperative, so padbackend reads it directly via pygame.
VIRTUAL_DEVICE_NAME = "kasual-vpad"
PHYSICAL_DEVICE_NAME = '8BitDo Ultimate Wireless / Pro 2 Wired Controller'


class PadListener(_PadListener):
    """YouTube gamepad translator: A → Enter, B → Esc, D-pad → arrows."""

    def on_key(self, code: str) -> None:
        if   code == BTN_SOUTH: press(Key.KEY_ENTER)
        elif code == BTN_EAST:  press(Key.KEY_ESC)

    def on_axis(self, code: str, value, prev) -> None:
        if   code == ABS_HAT0X:
            if value < 0:
                press(Key.KEY_LEFT)
            elif value > 0:
                press(Key.KEY_RIGHT)
        elif code == ABS_HAT0Y:
            if value < 0:
                press(Key.KEY_UP)
            elif value > 0:
                press(Key.KEY_DOWN)


# ── Entrypoint ─────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("YouTube")

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
