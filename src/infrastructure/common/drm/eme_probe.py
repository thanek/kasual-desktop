"""Child process of :class:`QtWebEnginePlaybackProbe`. Exits 0 when the CDM loads.

Run as ``python3 eme_probe.py <cdm-path>``. It lives in its own process because
Chromium reads ``QTWEBENGINE_CHROMIUM_FLAGS`` once, when Qt WebEngine
initializes, and a CDM that crashes the renderer must not take Kasual Desktop
with it.
"""

import os
import sys

_TIMEOUT_MS = 20000

_flags = [os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")]
if len(sys.argv) > 1:
    _flags.append(f"--widevine-path={sys.argv[1]}")
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(_flags).strip()

from PyQt6.QtCore import QTimer, QUrl                    # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView      # noqa: E402,F401
from PyQt6.QtWebEngineCore import QWebEnginePage         # noqa: E402
from PyQt6.QtWidgets import QApplication                 # noqa: E402

# Encrypted Media Extensions are gated on a secure context, hence the https base.
_ORIGIN = "https://localhost/"

_PROBE_PAGE = """<html><body><script>
navigator.requestMediaKeySystemAccess('com.widevine.alpha', [{
    initDataTypes: ['cenc'],
    videoCapabilities: [{contentType: 'video/mp4;codecs="avc1.42E01E"'}]
}]).then(function () { document.title = 'ok'; },
         function () { document.title = 'no'; });
</script></body></html>"""

_SUPPORTED = "ok"
_UNSUPPORTED = "no"


def main() -> int:
    app = QApplication(sys.argv)
    page = QWebEnginePage()
    outcome = [_UNSUPPORTED]

    def on_title(title: str) -> None:
        if title not in (_SUPPORTED, _UNSUPPORTED):
            return
        outcome[0] = title
        app.quit()

    page.titleChanged.connect(on_title)
    QTimer.singleShot(_TIMEOUT_MS, app.quit)
    page.setHtml(_PROBE_PAGE, QUrl(_ORIGIN))
    app.exec()
    return 0 if outcome[0] == _SUPPORTED else 1


if __name__ == "__main__":
    sys.exit(main())
