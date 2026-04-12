"""
KWin D-Bus window management — Wayland-native, KDE Plasma 6.

Plasma 6 does not have activeWindow() / activateWindow() in /KWin.
Instead:
  - active window:  'active' field collected by _LIST_SCRIPT
  - activation:     one-shot KWin script (workspace.activeWindow = ...)
  - window list:    KWin script (workspace.windowList()) + ExportAllSlots

_WindowListHost registers the receive() slot directly via ExportAllSlots
(without a separate adaptor). The script calls callDBus with an empty interface —
Qt routes to the first matching slot by method name.
"""

import json
import logging
import os
import tempfile

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import (
    QDBusConnection, QDBusInterface, QDBusMessage,
)

logger = logging.getLogger(__name__)

_KWIN_SVC   = 'org.kde.KWin'
_KWIN_PATH  = '/KWin'
_KWIN_IFACE = 'org.kde.KWin'
_SCRI_PATH  = '/Scripting'
_SCRI_IFACE = 'org.kde.kwin.Scripting'

_WL_SVC   = 'org.consoledesktop.WindowList'
_WL_PATH  = '/WindowList'
_WL_IFACE = 'org.consoledesktop.WindowList'

# Window listing script. Filter: normalWindow + not desktop/dock.
# skipTaskbar is NOT filtered — fullscreen games may have it set.
_LIST_SCRIPT = """\
(function () {
    var aw = workspace.activeWindow;
    var awId = aw ? String(aw.internalId) : '';
    var ws = workspace.windowList();
    var out = [];
    for (var i = 0; i < ws.length; i++) {
        var w = ws[i];
        if (!w.skipTaskbar && w.normalWindow && !w.desktopWindow && !w.dock) {
            out.push({
                id:            String(w.internalId),
                title:         String(w.caption),
                pid:           parseInt(w.pid) || 0,
                active:        String(w.internalId) === awId,
                desktopFile:   String(w.desktopFileName || ''),
                resourceClass: String(w.resourceClass   || '')
            });
        }
    }
    callDBus('org.consoledesktop.WindowList', '/WindowList',
             '', 'receive',
             JSON.stringify(out));
})();
"""

# Window activation by UUID — '{uuid}' is replaced by format().
_ACTIVATE_SCRIPT = """\
(function () {{
    var target = '{uuid}';
    var ws = workspace.windowList();
    for (var i = 0; i < ws.length; i++) {{
        if (String(ws[i].internalId) === target) {{
            ws[i].minimized = false;
            workspace.activeWindow = ws[i];
            break;
        }}
    }}
}})();
"""

_CLOSE_SCRIPT = """\
(function () {{
    var target = '{uuid}';
    var ws = workspace.windowList();
    for (var i = 0; i < ws.length; i++) {{
        if (String(ws[i].internalId) === target) {{
            ws[i].closeWindow();
            break;
        }}
    }}
}})();
"""

_SCRIPT_TIMEOUT_MS = 5_000


class _WindowListHost(QObject):
    """
    Receives KWin script results via D-Bus.

    The receive() slot is registered via ExportAllSlots — does not require
    QDBusAbstractAdaptor. The KWin script calls callDBus with an empty interface,
    Qt routes by method name.
    """

    def __init__(self) -> None:
        super().__init__()
        self._callbacks: list = []

        bus = QDBusConnection.sessionBus()
        ok_obj = bus.registerObject(
            _WL_PATH, self,
            QDBusConnection.RegisterOption.ExportAllSlots,
        )
        ok_svc = bus.registerService(_WL_SVC)
        if not ok_obj or not ok_svc:
            logger.error('D-Bus registration failed: obj=%s svc=%s', ok_obj, ok_svc)
        else:
            logger.info('D-Bus WindowList registered (%s %s)', _WL_SVC, _WL_PATH)

    @pyqtSlot(str)
    def receive(self, json_str: str) -> None:
        logger.debug('D-Bus receive: %d chars', len(json_str))
        try:
            data = json.loads(json_str)
        except Exception as exc:
            logger.warning('WindowList JSON error: %s', exc)
            data = []
        self._on_receive(data)

    def add_callback(self, cb) -> None:
        self._callbacks.append(cb)

    def _on_receive(self, data: list[dict]) -> None:
        callbacks, self._callbacks = self._callbacks, []
        for cb in callbacks:
            cb(data)

    def cleanup(self) -> None:
        bus = QDBusConnection.sessionBus()
        bus.unregisterService(_WL_SVC)
        bus.unregisterObject(_WL_PATH)


class KWinWindowManager(QObject):
    """
    Manages windows via KWin D-Bus + one-shot KWin scripts.
    Wayland-native, no xdotool. Compatible with KDE Plasma 6.
    """

    windows_updated = pyqtSignal(list)   # list[dict]: id, title, pid

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        bus = QDBusConnection.sessionBus()
        self._kwin      = QDBusInterface(_KWIN_SVC, _KWIN_PATH, _KWIN_IFACE, bus)
        self._scripting = QDBusInterface(_KWIN_SVC, _SCRI_PATH, _SCRI_IFACE, bus)

        # Required in Plasma 6: start() activates the KWin scripting engine
        # before the first loadScript(). Safe to call multiple times.
        reply = self._scripting.call('start')
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            logger.warning('KWin scripting start() failed: %s', reply.errorMessage())
        else:
            logger.debug('KWin scripting engine started')

        self._host: _WindowListHost | None = None
        self._cache:            dict[str, dict] = {}
        self._active_window_id: str | None      = None
        self._loading  = False
        self._counter  = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._request_list_refresh)

        self._timeout_guard = QTimer(self)
        self._timeout_guard.setSingleShot(True)
        self._timeout_guard.timeout.connect(self._on_script_timeout)

    # ── Public API ─────────────────────────────────────────────────────────

    def start_periodic_refresh(self, interval_ms: int = 3000) -> None:
        self._ensure_host()
        self._request_list_refresh()
        self._timer.start(interval_ms)

    def stop_refresh(self) -> None:
        self._timer.stop()

    def refresh_now(self) -> None:
        """Forces an immediate refresh of the window list."""
        self._request_list_refresh()

    def get_active_window_id(self) -> str | None:
        """Returns the ID of the active window from the last list refresh."""
        return self._active_window_id

    def get_cached_title(self, window_id: str) -> str | None:
        entry = self._cache.get(window_id)
        return entry['title'] if entry else None

    def activate_window(self, window_id: str) -> None:
        """
        Activates a window via a one-shot KWin script.
        (Plasma 6 does not have activateWindow() in D-Bus /KWin.)
        """
        script = _ACTIVATE_SCRIPT.format(uuid=window_id.replace("'", "\\'"))
        self._run_fire_and_forget(script, tag='activate')

    def close_window(self, window_id: str) -> None:
        """Closes a window via a one-shot KWin script (closeWindow())."""
        script = _CLOSE_SCRIPT.format(uuid=window_id.replace("'", "\\'"))
        self._run_fire_and_forget(script, tag='close')

    def window_exists(self, window_id: str) -> bool:
        return window_id in self._cache

    def cached_windows(self) -> list[dict]:
        return list(self._cache.values())

    def close(self) -> None:
        self.stop_refresh()
        if self._host:
            self._host.cleanup()
            self._host = None

    # ── Internal: window list ──────────────────────────────────────────────

    def _ensure_host(self) -> None:
        if self._host is None:
            self._host = _WindowListHost()

    def _request_list_refresh(self) -> None:
        if self._loading:
            return
        self._ensure_host()

        path = self._write_script(_LIST_SCRIPT)
        if path is None:
            return

        self._counter += 1
        plugin = f'consoled_list_{os.getpid()}_{self._counter}'

        self._host.add_callback(
            lambda wins, p=path, pg=plugin: self._on_windows(wins, p, pg)
        )
        self._loading = True
        self._timeout_guard.start(_SCRIPT_TIMEOUT_MS)

        if not self._load_script(path, plugin):
            self._loading = False
            self._timeout_guard.stop()
            self._host._callbacks.clear()
            try:
                os.unlink(path)
            except Exception:
                pass

    def _on_windows(self, windows: list[dict], script_path: str, plugin: str) -> None:
        self._loading = False
        self._timeout_guard.stop()
        self._cleanup_script(script_path, plugin)

        our_pid = os.getpid()
        windows = [w for w in windows if w.get('pid') != our_pid]

        self._active_window_id = next(
            (w['id'] for w in windows if w.get('active')), None
        )
        self._cache = {w['id']: w for w in windows}
        self.windows_updated.emit(list(self._cache.values()))
        logger.debug('Windows list: %d, active: %s', len(self._cache), self._active_window_id)

    def _on_script_timeout(self) -> None:
        if self._loading:
            logger.warning(
                'Timeout (%dms): KWin script did not respond – resetting',
                _SCRIPT_TIMEOUT_MS,
            )
            self._loading = False

    # ── Internal: script helpers ───────────────────────────────────────────

    def _write_script(self, content: str) -> str | None:
        try:
            fd, path = tempfile.mkstemp(suffix='.js', prefix='consoled_')
            with os.fdopen(fd, 'w') as f:
                f.write(content)
            return path
        except Exception as exc:
            logger.error('Could not save script: %s', exc)
            return None

    def _load_script(self, path: str, plugin: str) -> bool:
        reply = self._scripting.call('loadScript', path, plugin)
        if reply.type() == QDBusMessage.MessageType.ReplyMessage:
            # In KWin 6, start() runs scripts loaded after the previous start().
            # Without this call, the script is loaded but never executed.
            self._scripting.call('start')
            logger.debug('loadScript OK: %s', plugin)
            return True
        logger.error('loadScript failed (%s): %s', plugin, reply.errorMessage())
        return False

    def _cleanup_script(self, path: str, plugin: str) -> None:
        try:
            os.unlink(path)
        except Exception:
            pass
        self._scripting.call('unloadScript', plugin)

    def _run_fire_and_forget(self, script: str, tag: str) -> None:
        """Loads a script without waiting for a result (window activation, etc.)."""
        path = self._write_script(script)
        if path is None:
            return
        self._counter += 1
        plugin = f'consoled_{tag}_{os.getpid()}_{self._counter}'
        if self._load_script(path, plugin):
            QTimer.singleShot(500, lambda: self._cleanup_script(path, plugin))
        else:
            try:
                os.unlink(path)
            except Exception:
                pass
