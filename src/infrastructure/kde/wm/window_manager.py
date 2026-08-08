"""KWin D-Bus window management — Wayland-native, KDE Plasma 6.

Plasma 6 has no activeWindow()/activateWindow() in /KWin, so activation, the
window list, and the active window's id are all done via one-shot KWin scripts
(workspace.windowList() / workspace.activeWindow), with results returned over
D-Bus to _WindowListHost's receive() slot.
"""

import json
import logging
import os
import tempfile

from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSlot
from PyQt6.QtDBus import (
    QDBusConnection, QDBusInterface, QDBusMessage,
)

from domain.catalog.window import Window
from domain.lifecycle.window_manager import WindowManager
from domain.shared.event_emitter import EventEmitter, Unsubscribe
from infrastructure.common.qt._meta import ProtocolQtMeta
from infrastructure.linux.proc import expand_pid_tree

logger = logging.getLogger(__name__)


def to_window(d: dict) -> Window:
    """Adapt a KWin window-list entry (the dict shape produced by _LIST_SCRIPT)
    to a domain Window. Lives here, beside the script that defines that shape."""
    return Window(
        id=str(d.get('id', '')),
        title=str(d.get('title', '')),
        pid=int(d.get('pid', 0) or 0),
        active=bool(d.get('active', False)),
        fullscreen=bool(d.get('fullscreen', False)),
        covers_screen=bool(d.get('coversScreen', False)),
        desktop_file=d.get('desktopFile', '') or '',
        resource_class=d.get('resourceClass', '') or '',
    )

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
    var area = workspace.virtualScreenSize;
    var out = [];
    for (var i = 0; i < ws.length; i++) {
        var w = ws[i];
        if (!w.skipTaskbar && w.normalWindow && !w.desktopWindow && !w.dock) {
            var geo = w.frameGeometry;
            var covers = geo.width >= area.width && geo.height >= area.height;
            out.push({
                id:            String(w.internalId),
                title:         String(w.caption),
                pid:           parseInt(w.pid) || 0,
                active:        String(w.internalId) === awId,
                fullscreen:    Boolean(w.fullscreen),
                coversScreen:  covers,
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

# {pids}: JSON array of PIDs (incl. descendants). No skipTaskbar filter, so
# this also reaches fullscreen/kiosk apps invisible to the normal window list.
_MINIMIZE_BY_PIDS_SCRIPT = """\
(function () {{
    var pids = {pids};
    var ws = workspace.windowList();
    for (var i = 0; i < ws.length; i++) {{
        if (pids.indexOf(parseInt(ws[i].pid)) !== -1) {{
            ws[i].minimized = true;
        }}
    }}
}})();
"""

_ACTIVATE_BY_PIDS_SCRIPT = """\
(function () {{
    var pids = {pids};
    var ws = workspace.windowList();
    for (var i = 0; i < ws.length; i++) {{
        if (pids.indexOf(parseInt(ws[i].pid)) !== -1) {{
            ws[i].minimized = false;
            workspace.activeWindow = ws[i];
        }}
    }}
}})();
"""

# Like _ACTIVATE_BY_PIDS_SCRIPT but raiseWindow() instead of activeWindow, so
# it skips KWin's activation animation — use when focus isn't required.
_RAISE_BY_PIDS_SCRIPT = """\
(function () {{
    var pids = {pids};
    var ws = workspace.windowList();
    for (var i = 0; i < ws.length; i++) {{
        if (pids.indexOf(parseInt(ws[i].pid)) !== -1) {{
            ws[i].minimized = false;
            workspace.raiseWindow(ws[i]);
        }}
    }}
}})();
"""

# Persistent event hook: poke us over D-Bus whenever the window stack changes, so
# the list refreshes in ~150 ms instead of waiting for the 3 s poll — returning to
# the Desktop as an app's window disappears, and getting out of the way of a splash
# or a launcher (which only shows up as a focus change) as it appears.
_EVENTS_SCRIPT = """\
(function () {
    var poke = function (w) {
        callDBus('org.consoledesktop.WindowList', '/WindowList',
                 '', 'windowsChanged', String(w ? w.pid : 0));
    };
    workspace.windowRemoved.connect(poke);
    workspace.windowAdded.connect(poke);
    workspace.windowActivated.connect(poke);
})();
"""

_EVENTS_PLUGIN = 'consoled_window_events'

_SCRIPT_TIMEOUT_MS = 5_000
_CHANGED_DEBOUNCE_MS = 150


class _WindowListHost(QObject):
    """Receives KWin script results via D-Bus.

    receive() is registered via ExportAllSlots (no QDBusAbstractAdaptor needed);
    the KWin script calls callDBus with an empty interface and Qt routes by
    method name.
    """

    def __init__(self) -> None:
        super().__init__()
        self._callbacks: list = []
        self._changed_cb: Callable[[str], None] | None = None

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

    @pyqtSlot(str)
    def windowsChanged(self, pid: str) -> None:
        if self._changed_cb is not None:
            self._changed_cb(pid)

    def set_changed_callback(self, cb: Callable[[str], None]) -> None:
        self._changed_cb = cb

    def add_callback(self, cb) -> None:
        self._callbacks.append(cb)

    def clear_callbacks(self) -> None:
        self._callbacks.clear()

    def _on_receive(self, data: list[dict]) -> None:
        callbacks, self._callbacks = self._callbacks, []
        for cb in callbacks:
            cb(data)

    def cleanup(self) -> None:
        bus = QDBusConnection.sessionBus()
        bus.unregisterService(_WL_SVC)
        bus.unregisterObject(_WL_PATH)


class KWinWindowManager(QObject, WindowManager, metaclass=ProtocolQtMeta):
    """Implements the `WindowManager` port via KWin D-Bus + one-shot scripts."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._windows_emitter: EventEmitter[list[Window]] = EventEmitter()
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

        # Coalesces bursts (a closing app drops several windows; a launcher maps
        # a window and takes focus in the same breath).
        self._changed_debounce = QTimer(self)
        self._changed_debounce.setSingleShot(True)
        self._changed_debounce.setInterval(_CHANGED_DEBOUNCE_MS)
        self._changed_debounce.timeout.connect(self._request_list_refresh)
        self._events_path: str | None = None

    # ── Public API ─────────────────────────────────────────────────────────

    def start_periodic_refresh(self, interval_ms: int = 3000) -> None:
        self._ensure_host()
        self._install_event_script()
        self._request_list_refresh()
        self._timer.start(interval_ms)

    def stop_refresh(self) -> None:
        self._timer.stop()

    def refresh_now(self) -> None:
        self._request_list_refresh()

    def get_active_window_id(self) -> str | None:
        return self._active_window_id

    def get_cached_title(self, window_id: str) -> str | None:
        entry = self._cache.get(window_id)
        return entry['title'] if entry else None

    def activate_window(self, window_id: str) -> None:
        script = _ACTIVATE_SCRIPT.format(uuid=window_id.replace("'", "\\'"))
        self._run_fire_and_forget(script, tag='activate')

    def close_window(self, window_id: str) -> None:
        script = _CLOSE_SCRIPT.format(uuid=window_id.replace("'", "\\'"))
        self._run_fire_and_forget(script, tag='close')

    def minimize_windows_for_pids(self, pids: set[int]) -> None:
        """Minimize windows for *pids*/descendants, bypassing the window cache —
        works even for fullscreen/kiosk apps invisible to the normal list."""
        all_pids = expand_pid_tree(pids)
        if all_pids:
            script = _MINIMIZE_BY_PIDS_SCRIPT.format(pids=json.dumps(sorted(all_pids)))
            self._run_fire_and_forget(script, tag='minimize')

    def activate_windows_for_pids(self, pids: set[int]) -> None:
        all_pids = expand_pid_tree(pids)
        if all_pids:
            script = _ACTIVATE_BY_PIDS_SCRIPT.format(pids=json.dumps(sorted(all_pids)))
            self._run_fire_and_forget(script, tag='activate_pids')

    def activate_windows_for_pid_exact(self, pid: int) -> None:
        """Activate windows owned by *pid* exactly (no descendant expansion) —
        Wayland's focus-stealing prevention otherwise ignores Qt's
        raise_/activateWindow when another app holds focus."""
        script = _ACTIVATE_BY_PIDS_SCRIPT.format(pids=json.dumps([pid]))
        self._run_fire_and_forget(script, tag='activate_pid_exact')

    def raise_self(self) -> None:
        """Bring the Kasual Desktop's own window to the front (our process pid)."""
        self.raise_windows_for_pid_exact(os.getpid())

    def raise_windows_for_pid_exact(self, pid: int) -> None:
        """Like activate_windows_for_pid_exact but doesn't change focus, so KWin
        skips its window-activation animation — fine since input goes through
        our own gamepad handler stack, not system focus."""
        script = _RAISE_BY_PIDS_SCRIPT.format(pids=json.dumps([pid]))
        self._run_fire_and_forget(script, tag='raise_pid_exact')

    def window_exists(self, window_id: str) -> bool:
        return window_id in self._cache

    def cached_windows(self) -> list[Window]:
        """Last known window list as domain Windows (the KWin dict shape stays
        internal; callers in the application layer get the domain value object)."""
        return [to_window(w) for w in self._cache.values()]

    def on_windows_updated(
        self, handler: Callable[[list[Window]], None]
    ) -> Unsubscribe:
        return self._windows_emitter.subscribe(handler)

    def close(self) -> None:
        self.stop_refresh()
        if self._events_path is not None:
            self._cleanup_script(self._events_path, _EVENTS_PLUGIN)
            self._events_path = None
        if self._host:
            self._host.cleanup()
            self._host = None

    # ── Internal: window list ──────────────────────────────────────────────

    def _ensure_host(self) -> None:
        if self._host is None:
            self._host = _WindowListHost()

    def _install_event_script(self) -> None:
        """Load the persistent window-stack hook (idempotent). A fixed plugin
        name plus unload-before-load clears any copy left by a crashed run."""
        if self._events_path is not None:
            return
        self._scripting.call('unloadScript', _EVENTS_PLUGIN)
        path = self._write_script(_EVENTS_SCRIPT)
        if path is None:
            return
        self._host.set_changed_callback(self._on_windows_changed)
        if self._load_script(path, _EVENTS_PLUGIN):
            self._events_path = path
        else:
            try:
                os.unlink(path)
            except Exception as exc:
                logger.debug("Script cleanup failed (%s): %s", path, exc)

    def _on_windows_changed(self, _pid: str) -> None:
        self._changed_debounce.start()

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
            self._host.clear_callbacks()
            try:
                os.unlink(path)
            except Exception as exc:
                logger.debug("Script cleanup failed (%s): %s", path, exc)

    def _on_windows(self, windows: list[dict], script_path: str, plugin: str) -> None:
        self._loading = False
        self._timeout_guard.stop()
        self._cleanup_script(script_path, plugin)

        # Belt-and-braces: normally redundant with _LIST_SCRIPT's normalWindow
        # filter, but catches our own windows if make_layer_surface() ever falls
        # back to plain xdg toplevels (pip-bundled / non-system Qt).
        our_pid = os.getpid()
        windows = [w for w in windows if w.get('pid') != our_pid]

        self._active_window_id = next(
            (w['id'] for w in windows if w.get('active')), None
        )
        self._cache = {w['id']: w for w in windows}
        self._windows_emitter.emit(self.cached_windows())
        logger.debug('Windows list: %d, active: %s', len(self._cache), self._active_window_id)

    def _on_script_timeout(self) -> None:
        if self._loading:
            logger.warning(
                'Timeout (%dms): KWin script did not respond – resetting',
                _SCRIPT_TIMEOUT_MS,
            )
            self._loading = False
            # Drop the orphaned callback so a late reply doesn't fire it
            # alongside the next request's callback with that request's data.
            if self._host is not None:
                self._host.clear_callbacks()

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
        except Exception as exc:
            logger.debug("Script cleanup failed (%s): %s", path, exc)
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
            except Exception as exc:
                logger.debug("Script cleanup failed (%s): %s", path, exc)
