"""Bundled Netflix app — QtWebEngine with the Widevine CDM.

Netflix has no public TV web UI (its TV apps use partner-only endpoints), so
this loads the desktop site with a Chrome-like user agent — Netflix rejects
unknown browsers — and enables Chromium spatial navigation so the D-pad can
move focus between tiles. Playback DRM is Widevine L3 (software), which caps
Netflix at ~720p.
"""

import glob
import os
import platform
import sys
import threading

# Kept in step with infrastructure/linux/drm/facts.py, which Kasual Desktop's
# readiness check uses: this app runs as a standalone process against the system
# Python and imports nothing from the main source tree.
_CDM_GLOBS = (
    "/var/lib/widevine/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    "/opt/google/chrome*/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    "/opt/microsoft/msedge*/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.config/google-chrome/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.config/chromium/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.config/BraveSoftware/Brave-Browser/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.var/app/com.google.Chrome/config/google-chrome/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.var/app/org.chromium.Chromium/config/chromium/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/snap/chromium/common/chromium/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "/usr/lib*/chromium*/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    "/opt/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    # Firefox's GMP updater downloads the same library. Whether Qt WebEngine
    # accepts that copy is unverified.
    "~/.mozilla/firefox/*/gmp-widevinecdm/*/libwidevinecdm.so",
)

# An architecture absent here gets the setup page instead of Netflix.
_ARCH_DIRS = {
    "aarch64": "linux_arm64",
    "arm64": "linux_arm64",
    "armv7l": "linux_arm",
    "x86_64": "linux_x64",
    "amd64": "linux_x64",
}


def _find_cdm() -> str | None:
    """Chrome files each component update under its own version directory, and
    those names do not sort: 4.10.9 sits above 4.10.10."""
    wanted = _ARCH_DIRS.get(platform.machine())
    if wanted is None:
        return None
    for pattern in _CDM_GLOBS:
        hits = [path for path in glob.glob(os.path.expanduser(pattern))
                if _is_module(path, wanted)]
        if hits:
            return max(hits, key=os.path.getmtime)
    return None


def _is_module(path: str, arch_dir: str) -> bool:
    """widevine-installer leaves an empty linux_x64 stub beside the real ARM
    module because Chromium insists on that path. A Firefox profile, in turn,
    holds one build under no architecture directory at all.

    Distro Chromium packages symlink into /var/lib/widevine, so a glob hit can
    be a link that leads nowhere until the installer has run.
    """
    if "_platform_specific" in path and arch_dir not in path:
        return False
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


DEBUG = bool(os.environ.get("KASUAL_NETFLIX_DEBUG"))

# Chromium reads QTWEBENGINE_CHROMIUM_FLAGS when Qt WebEngine initializes, so
# the CDM must be resolved before anything Qt is imported. On Windows Qt finds
# Chrome's CDM by itself; on Linux without a CDM the app still starts and shows
# setup instructions instead of Netflix.
_CDM = _find_cdm() if sys.platform != "win32" else None
# The app claims to be Firefox (see _user_agent), and Firefox has no client
# hints — so strip them entirely or the fingerprint contradicts itself. The
# base feature kills the Sec-CH-UA headers, the blink feature removes the
# navigator.userAgentData JS API (each flag only reaches its own layer).
_flags = [os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""),
          "--disable-features=UserAgentClientHint",
          "--disable-blink-features=UserAgentClientHint"]
if _CDM:
    _flags.append(f"--widevine-path={_CDM}")
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(_flags).strip()
if DEBUG:
    os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", "9222")

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings,
    qWebEngineChromiumVersion,
)

from keyinput import Key, press
from padbackend import (
    ABS_HAT0X, ABS_HAT0Y, BTN_EAST, BTN_SOUTH, PadListener as _PadListener,
    find_pad,
)

# On Linux, Kasual grabs the physical gamepad and exposes a virtual
# "kasual-vpad" device; the app reads from it because the physical pad is
# exclusive-grabbed and BTN_MODE is filtered. On Windows the controller is
# cooperative, so padbackend reads it directly via pygame.
APP_ID = "kasual-netflix"
VIRTUAL_DEVICE_NAME = "kasual-vpad"
PHYSICAL_DEVICE_NAME = '8BitDo Ultimate Wireless / Pro 2 Wired Controller'

NO_CDM_HTML = """
<html><body style="background:#141414;color:#e5e5e5;font-family:sans-serif;
display:flex;align-items:center;justify-content:center;height:100%">
<div style="max-width:40em">
<h1 style="color:#e50914">Widevine CDM not found</h1>
<p>Netflix needs the Widevine DRM module. On Fedora install it with:</p>
<pre style="background:#000;padding:1em">sudo dnf install widevine-installer
sudo widevine-installer</pre>
<p>then restart this app. On other distros, installing Google Chrome
provides the CDM.</p>
</div></body></html>
"""


# Debug aid (KASUAL_NETFLIX_DEBUG=1): log every fetch/XHR completion, fetch
# rejections, JS errors and a capability snapshot — DebugPage prints them all.
JS_NET_LOG = """
(function () {
    const origFetch = window.fetch;
    window.fetch = function (...args) {
        const url = (args[0] && args[0].url) || args[0];
        return origFetch.apply(this, args).then(resp => {
            console.error('[net] fetch ' + resp.status + ' (' + resp.type
                          + ') ' + resp.url);
            if (resp.url.includes('graphql')) {
                const op = args[1] && args[1].body
                    ? String(args[1].body).slice(0, 200) : '';
                resp.clone().text().then(t => console.error(
                    '[gql] req=' + op + ' resp=' + t.slice(0, 500)));
            }
            return resp;
        }, err => {
            console.error('[net] fetch FAILED ' + url + ' — ' + err);
            throw err;
        });
    };
    const origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
        this.addEventListener('loadend', function () {
            console.error('[net] xhr ' + this.status + ' ' + method + ' ' + url);
        });
        return origOpen.call(this, method, url, ...rest);
    };
    window.addEventListener('error',
        e => console.error('[err] ' + e.message + ' @' + e.filename + ':' + e.lineno));
    window.addEventListener('unhandledrejection',
        e => console.error('[err] unhandled rejection: ' + e.reason));
    if (window === window.top) {
        let webgl = 'no';
        try {
            const c = document.createElement('canvas');
            webgl = c.getContext('webgl2') ? 'webgl2'
                  : c.getContext('webgl') ? 'webgl1' : 'no';
        } catch (e) { webgl = 'error: ' + e; }
        console.error('[env] webgl=' + webgl
            + ' uaData=' + (navigator.userAgentData ? 'yes' : 'no')
            + ' cookies=' + navigator.cookieEnabled
            + ' webdriver=' + navigator.webdriver);
    }
})();
"""


class DebugPage(QWebEnginePage):
    """Prints the page's JS console to stderr — active only in debug mode."""

    def javaScriptConsoleMessage(self, level, message, line, source) -> None:
        print(f"[console] {message}  ({source}:{line})", file=sys.stderr)


class PadListener(_PadListener):
    """Netflix gamepad translator: A → Enter, B → Esc, D-pad → arrows."""

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


def _user_agent() -> str:
    override = os.environ.get("KASUAL_NETFLIX_UA")
    if override:
        return override
    chrome = qWebEngineChromiumVersion().split(".")[0]
    if _CDM and "arm64" in _CDM:
        # The aarch64 CDM is extracted from a ChromeOS image and its device
        # certificate identifies as ChromeOS; Netflix's license server
        # cross-checks that against the user agent and answers E100 to any
        # non-CrOS browser. Discovered by the Asahi folks:
        # https://www.da.vidbuchanan.co.uk/blog/netflix-on-asahi.html
        return (f"Mozilla/5.0 (X11; CrOS aarch64 16328.0.0) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{chrome}.0.0.0 Safari/537.36")
    # Netflix rejects unknown browsers, and claiming plain Chrome trips its
    # login fingerprinting: a real Chrome ships client hints, WebGL2 and
    # Google-only APIs that QtWebEngine lacks. Firefox has none of those, so
    # a Firefox UA is self-consistent — the same trick qutebrowser's site
    # quirks use. ESR keeps the claimed version plausible for years.
    return "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"


# ── Entrypoint ─────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    # Wayland takes the window's app_id from here; without it the window reports
    # "python3" and Kasual Desktop cannot tell its own app from a foreign one.
    app.setDesktopFileName(APP_ID)
    window = QMainWindow()
    window.setWindowTitle("Netflix")

    profile = QWebEngineProfile("netflix", app)
    profile.setHttpUserAgent(_user_agent())
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
    )

    if DEBUG:
        script = QWebEngineScript()
        script.setName("netflix-net-log")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(True)
        script.setSourceCode(JS_NET_LOG)
        profile.scripts().insert(script)

    page = (DebugPage if DEBUG else QWebEnginePage)(profile, None)
    settings = page.settings()
    # Spatial navigation lets the D-pad's arrow keys walk the desktop site's
    # tiles; the player itself handles arrows/Enter/Esc natively.
    settings.setAttribute(
        QWebEngineSettings.WebAttribute.SpatialNavigationEnabled, True)
    settings.setAttribute(
        QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
    settings.setAttribute(
        QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
    # The window is already fullscreen — just let the player think it got it.
    page.fullScreenRequested.connect(lambda request: request.accept())

    view = QWebEngineView()
    view.setPage(page)
    if sys.platform != "win32" and _CDM is None:
        print("Warning: Widevine CDM not found — showing setup instructions",
              file=sys.stderr)
        page.setHtml(NO_CDM_HTML)
    else:
        # /login shows the classic email+password form; the email-first landing
        # flow gates on invisible reCAPTCHA Enterprise, which fails under
        # QtWebEngine. Once authenticated, /login redirects to /browse itself.
        view.setUrl(QUrl("https://www.netflix.com/login"))
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
