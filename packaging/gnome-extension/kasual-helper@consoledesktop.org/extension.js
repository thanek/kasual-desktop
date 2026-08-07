import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const TAG = '[kasual-helper]';

const BUS_NAME = 'org.consoledesktop.GnomeHelper';
const OBJECT_PATH = '/org/consoledesktop/GnomeHelper';

const IFACE = `
<node>
  <interface name="org.consoledesktop.GnomeHelper">
    <method name="Ping">
      <arg type="s" direction="out" name="json"/>
    </method>
    <method name="Debug">
      <arg type="s" direction="out" name="json"/>
    </method>
    <method name="Snapshot">
      <arg type="s" direction="in" name="title"/>
      <arg type="s" direction="in" name="path"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="ListWindows">
      <arg type="s" direction="out" name="json"/>
    </method>
    <method name="ActivateWindow">
      <arg type="s" direction="in" name="id"/>
    </method>
    <method name="CloseWindow">
      <arg type="s" direction="in" name="id"/>
    </method>
    <method name="MinimizeWindowsForPids">
      <arg type="s" direction="in" name="pidsJson"/>
    </method>
    <method name="SetSurfaceRole">
      <arg type="s" direction="in" name="title"/>
      <arg type="i" direction="in" name="layer"/>
      <arg type="i" direction="in" name="anchors"/>
      <arg type="i" direction="in" name="keyboard"/>
    </method>
    <method name="ActivateSurface">
      <arg type="s" direction="in" name="title"/>
    </method>
    <method name="ShowOverlay">
      <arg type="s" direction="in" name="wmClass"/>
    </method>
    <method name="CedeOverlay">
      <arg type="s" direction="in" name="wmClass"/>
    </method>
    <method name="HideOverlay">
      <arg type="s" direction="in" name="wmClass"/>
    </method>
    <method name="IsSunk">
      <arg type="b" direction="out" name="sunk"/>
    </method>
    <method name="WatchWindows">
      <arg type="b" direction="in" name="enable"/>
    </method>
    <signal name="WindowsChanged">
      <arg type="s" name="reason"/>
      <arg type="s" name="json"/>
    </signal>
    <method name="SimulateUserActivity"/>
  </interface>
</node>`;

// The layer-shell vocabulary Kasual speaks (infrastructure/common/qt/ui/layer_shell.py).
const ANCHOR_TOP = 1, ANCHOR_BOTTOM = 2, ANCHOR_LEFT = 4, ANCHOR_RIGHT = 8;
const DEFAULT_LAYER = 3;
const OVERLAY_LAYER = 3;
const KEYBOARD_NONE = 0;

const FOCUS_RETRY_MS = 100;
const FOCUS_ATTEMPTS = 20;

// Mutter moved the unredirect toggle from Meta to global.compositor across 45–50.
function unredirectApi() {
    if (global.compositor && typeof global.compositor.disable_unredirect === 'function')
        return 'compositor';
    if (typeof Meta.disable_unredirect_for_display === 'function')
        return 'meta';
    return 'none';
}

function disableUnredirect(api) {
    if (api === 'compositor') global.compositor.disable_unredirect();
    else if (api === 'meta') Meta.disable_unredirect_for_display(global.display);
}

function enableUnredirect(api) {
    if (api === 'compositor') global.compositor.enable_unredirect();
    else if (api === 'meta') Meta.enable_unredirect_for_display(global.display);
}

// Mutter tells a focus request from a focus *steal* by its timestamp: older than
// last_focus_time and it refuses to focus, flagging the window as demanding attention
// instead ("Window is ready"). global.get_current_time() is the last input event's time,
// which inside a D-Bus call is whatever the user last did — stale, and refused.
function activationTime() {
    return global.display.get_current_time_roundtrip();
}

// Meta.Window.raise() became raise_and_make_recent() on newer Mutter.
function raiseWindow(w) {
    if (typeof w.raise_and_make_recent === 'function') w.raise_and_make_recent();
    else if (typeof w.raise === 'function') w.raise();
}

function lowerWindow(w) {
    if (typeof w.lower_with_transients === 'function')
        w.lower_with_transients(global.get_current_time());
    else if (typeof w.lower === 'function')
        w.lower();
}

let loggedNoSetType = false;

// Measured on Mutter 50: a DOCK window is not focused as it maps, a NORMAL one is.
function denyFocus(win) {
    if (win.get_window_type() === Meta.WindowType.DOCK)
        return;
    if (typeof win.set_type !== 'function') {
        if (!loggedNoSetType) {
            loggedNoSetType = true;
            console.log(`${TAG} Meta.Window.set_type is missing: overlays will take the focus`);
        }
        return;
    }
    win.set_type(Meta.WindowType.DOCK);
}

function mappedWindows() {
    return global.get_window_actors()
        .map(a => a.meta_window)
        .filter(w => w);
}

// XWayland reports its X11 WM_CLASS ("Bitwarden"), not the flatpak app id the
// tile matches on; the window→app id resolves it.
function appIdOf(win) {
    return Shell.WindowTracker.get_default().get_window_app(win)?.get_id() || '';
}

// The window as the behavioral tests read it (tests/behavioral/harness/window_source.py).
function windowRecord(win, area) {
    const geo = win.get_frame_rect();
    return {
        id: String(win.get_id()),
        title: win.get_title() || '',
        app_id: win.get_wm_class() || '',
        pid: win.get_pid(),
        focused: win.has_focus(),
        fullscreen: win.is_fullscreen(),
        covers_screen: geo.width >= area.width && geo.height >= area.height,
        minimized: win.minimized,
        desktop_file: appIdOf(win),
        layer: win.get_layer(),
        above: win.is_above(),
        geometry: [geo.x, geo.y, geo.width, geo.height],
    };
}

// get_window_actors() documents no order; this one is defined as ascending, so
// the first window is the lowest. Stacking decisions must not guess.
function stackedBottomToTop(windows) {
    return global.display.sort_windows_by_stacking(windows);
}

class Helper {
    constructor() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, OBJECT_PATH);
        this._ownerId = Gio.bus_own_name_on_connection(
            Gio.DBus.session, BUS_NAME, Gio.BusNameOwnerFlags.NONE, null, null);

        this._appClass = null;
        this._showRequested = false;
        this._ceded = false;
        this._sunk = false;
        this._windowWatch = false;
        this._virtualPointer = null;
        this._roles = new Map();
        this._pinned = new Set();
        this._unredirectApi = null;
        this._restackedId = 0;
        this._syncSourceId = 0;
        this._anchorSourceId = 0;
        this._anchorPending = new Set();
        this._restacking = false;
        this._pendingFocus = null;
        this._focusSourceId = 0;
        this._focusAttempts = 0;
        this._windowSignals = new Map();
        this._realGetRunning = null;

        this._hideFromAppLists();
        this._windowCreatedId = global.display.connect(
            'window-created', (_d, win) => this._trackWindow(win));
        this._suppressReadyBannerForOwnWindows();
        // A ceded Desktop's depth follows the focus (see _focusIsOrdinaryWindow).
        this._focusId = global.display.connect('notify::focus-window', () => {
            this._scheduleSync();
            this._emitWindows('activated');
        });
        for (const win of mappedWindows())
            this._trackWindow(win);

        console.log(`${TAG} exported ${BUS_NAME}; unredirect API = ${unredirectApi()}`);
    }

    destroy() {
        for (const id of [this._syncSourceId, this._anchorSourceId, this._focusSourceId])
            if (id)
                GLib.source_remove(id);
        this._syncSourceId = 0;
        this._anchorSourceId = 0;
        this._focusSourceId = 0;
        global.display.disconnect(this._windowCreatedId);
        this._restoreReadyBanner();
        global.display.disconnect(this._focusId);
        for (const [win, ids] of this._windowSignals)
            for (const id of ids)
                win.disconnect(id);
        this._windowSignals.clear();
        this._showFromAppLists();
        this._virtualPointer = null;
        this._appClass = null;
        this._sync();
        this._dbus.unexport();
        if (this._ownerId)
            Gio.bus_unown_name(this._ownerId);
        console.log(`${TAG} destroyed`);
    }

    // ── window bookkeeping ───────────────────────────────────────────────────

    // Kasual's overlays map long after ShowOverlay, so pinning cannot be a snapshot.
    _trackWindow(win) {
        if (this._windowSignals.has(win))
            return;
        // Only Kasual's own windows matter here; a terminal's spinner retitling
        // itself ten times a second must not restack the session.
        const syncIfOurs = () => {
            if (this._isOurs(win)) {
                // Not on the idle sync: Mutter focuses the window as it maps, next.
                this._applyFocusPolicy(win);
                this._scheduleSync();
            }
        };
        this._windowSignals.set(win, [
            // An XWayland window (every Steam game) is created before its WM_CLASS
            // arrives: this, not window-created, is where it becomes identifiable.
            win.connect('notify::wm-class', () => {
                this._suppressScanoutForOurs(win);
                this._applyFocusPolicy(win);
                this._scheduleSync();
                this._emitWindows('class');
            }),
            win.connect('notify::title', syncIfOurs),
            // Fullscreen toggles change what must sit over a ceded Desktop.
            win.connect('notify::fullscreen', () => {
                this._scheduleSync();
                this._emitWindows('fullscreen');
            }),
            win.connect('notify::minimized', () => this._emitWindows('minimized')),
            // Qt resizes the Home surface when its menu expands; re-anchor it.
            win.connect('size-changed', () => this._scheduleAnchor(win)),
            win.connect('position-changed', () => this._scheduleAnchor(win)),
        ]);
        this._windowSignals.get(win).push(win.connect('unmanaged', () => {
            for (const id of this._windowSignals.get(win) ?? [])
                win.disconnect(id);
            this._windowSignals.delete(win);
            this._pinned.delete(win);
            this._scheduleSync();
            this._emitWindows('removed');
        }));
        this._suppressScanoutForOurs(win);
        this._applyFocusPolicy(win);
        this._scheduleSync();
        this._emitWindows('added');
    }

    _isOurs(win) {
        return !!this._appClass && win.get_wm_class() === this._appClass;
    }

    // A gamepad shell is not an app you tab to. Mutter's skip-taskbar is read-only,
    // but the dash, the app switcher and the window list all draw their running-app
    // set from this one call.
    _hideFromAppLists() {
        const helper = this;
        const running = Shell.AppSystem.prototype.get_running;
        this._realGetRunning = running;
        Shell.AppSystem.prototype.get_running = function (...args) {
            return running.call(this, ...args)
                .filter(app => !app.get_windows().some(w => helper._isOurs(w)));
        };
    }

    _showFromAppLists() {
        if (!this._realGetRunning)
            return;
        Shell.AppSystem.prototype.get_running = this._realGetRunning;
        this._realGetRunning = null;
    }

    // Mutter decides to scan a fullscreen window straight out as it maps. Waiting
    // for the idle _sync() loses that race: it hands the Desktop the screen and
    // stops compositing Kasual's other surfaces, which then lose their frame
    // callbacks and go silent for good.
    _suppressScanoutForOurs(win) {
        if (this._isOurs(win))
            this._setUnredirectSuppressed(true);
    }

    // The "window is ready" banner. Bound to the Shell handler at its own
    // construction, so its connections are replaced, not the method overridden.
    _suppressReadyBannerForOwnWindows() {
        const banner = Main.windowAttentionHandler;
        const attentionSignals = [
            ['_windowDemandsAttentionId', 'window-demands-attention'],
            ['_windowMarkedUrgentId', 'window-marked-urgent'],
        ];
        if (banner && attentionSignals.every(([id]) => banner[id])) {
            this._bannerFilter = {banner, attentionSignals};
            for (const [id, signal] of attentionSignals) {
                global.display.disconnect(banner[id]);
                banner[id] = global.display.connect(signal, (display, window) => {
                    if (!(window && this._isOurs(window)))
                        banner._onWindowDemandsAttention(display, window);
                });
            }
            return;
        }
        // Shell internals moved: fall back to clearing the flag post-hoc.
        this._flagClearId = global.display.connect(
            'window-demands-attention', (_d, win) => {
                if (this._isOurs(win))
                    win.unset_demands_attention();
            });
    }

    _restoreReadyBanner() {
        if (this._flagClearId) {
            global.display.disconnect(this._flagClearId);
            this._flagClearId = 0;
            return;
        }
        const filter = this._bannerFilter;
        if (!filter)
            return;
        this._bannerFilter = null;
        for (const [id, signal] of filter.attentionSignals) {
            global.display.disconnect(filter.banner[id]);
            filter.banner[id] = global.display.connect(
                signal, filter.banner._onWindowDemandsAttention.bind(filter.banner));
        }
    }

    _roleOf(win) {
        return this._isOurs(win) ? this._roles.get(win.get_title()) : undefined;
    }

    _applyFocusPolicy(win) {
        const role = this._roleOf(win);
        if (role && role.keyboard === KEYBOARD_NONE)
            denyFocus(win);
    }

    // Wayland gives placement to the compositor and size to the client, so only
    // the position is ours: resizing here would hand Qt a buffer it never repaints.
    _applyAnchor(win) {
        const role = this._roleOf(win);
        if (!role || !role.anchors || win.is_fullscreen())
            return;

        const index = win.get_monitor();
        const monitor = global.display.get_monitor_geometry(
            index >= 0 ? index : global.display.get_primary_monitor());
        const frame = win.get_frame_rect();

        let x = monitor.x + Math.floor((monitor.width - frame.width) / 2);
        if (role.anchors & ANCHOR_LEFT) x = monitor.x;
        else if (role.anchors & ANCHOR_RIGHT) x = monitor.x + monitor.width - frame.width;

        let y = monitor.y + Math.floor((monitor.height - frame.height) / 2);
        if (role.anchors & ANCHOR_TOP) y = monitor.y;
        else if (role.anchors & ANCHOR_BOTTOM) y = monitor.y + monitor.height - frame.height;

        // Flagged as a user action, or Mutter clamps the strip inside the work
        // area — exactly the struts wlr-layer-shell's exclusive_zone=-1 ignores.
        if (frame.x !== x || frame.y !== y)
            win.move_frame(true, x, y);
    }

    // A frame rect read straight from 'size-changed' can still be the size we
    // requested rather than the one the client committed.
    _scheduleAnchor(win) {
        this._anchorPending.add(win);
        if (this._anchorSourceId)
            return;
        this._anchorSourceId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._anchorSourceId = 0;
            const pending = [...this._anchorPending];
            this._anchorPending.clear();
            for (const w of pending)
                if (this._windowSignals.has(w))
                    this._applyAnchor(w);
            return GLib.SOURCE_REMOVE;
        });
    }

    // 'unmanaged' fires before the actor leaves the stage; settle on idle.
    _scheduleSync() {
        if (this._syncSourceId)
            return;
        this._syncSourceId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._syncSourceId = 0;
            this._sync();
            return GLib.SOURCE_REMOVE;
        });
    }

    // Bottom-to-top, as the compositor stacks them.
    _ourWindows() {
        if (!this._appClass)
            return [];
        return stackedBottomToTop(
            mappedWindows().filter(w => w.get_wm_class() === this._appClass));
    }

    // Unredirect stays on (game keeps direct scanout) until a Kasual window maps.
    _sync() {
        const before = this._pinned.size;
        const wanted = this._ourWindows();

        for (const w of this._pinned)
            if (!wanted.includes(w))
                w.unmake_above();
        this._pinned = new Set(wanted);

        for (const w of wanted) {
            this._applyAnchor(w);
            this._applyFocusPolicy(w);
        }

        // Desktop above ordinary windows, below every fullscreen app. make_above
        // would lift the fullscreen Desktop to the TOP layer over the app (Mutter
        // keeps plain fullscreen windows in NORMAL), so drop ABOVE and re-raise
        // the apps instead; the last app unmapping leaves the Desktop topmost.
        if (this._ceded) {
            const overlays = wanted.filter(w => this._isOverlay(w));
            const desktop = wanted.filter(w => !this._isOverlay(w));
            for (const w of desktop)
                w.unmake_above();
            this._sunk = this._focusIsOrdinaryWindow();
            if (this._sunk)
                this._sinkUnderWindows(desktop);
            else
                this._floatOverWindows(desktop);
            this._pinOverApp(overlays);
            // Only an overlay needs the app redirected; the ceded Desktop is happy
            // to stay under a scanned-out game.
            this._setUnredirectSuppressed(overlays.length > 0);
            // A game that keeps the focus restacks itself; the overlays must go back up.
            this._setRestackGuard(overlays.length > 0);
            return;
        }

        this._sunk = false;
        this._focusPending();
        this._reassertStacking();

        // Kasual asks for the screen before its first window exists, so the count
        // alone would release the suppression right when it matters most.
        this._setUnredirectSuppressed(this._showRequested || wanted.length > 0);
        this._setRestackGuard(wanted.length > 0);

        if (wanted.length !== before) {
            const titles = wanted.map(w => `${w.get_title()}${w.is_fullscreen() ? '*' : ''}`);
            console.log(`${TAG} pinned ${wanted.length}: [${titles.join(' | ')}]`);
        }
    }

    // What the app puts on screen right now shows in the focus, not in the window
    // list: a game that opens a launcher (Witcher 3) or a splash (Kingdom Come)
    // hands focus to an ordinary window while its own fullscreen window lives on.
    _focusIsOrdinaryWindow() {
        const focus = global.display.focus_window;
        return !!focus && !this._isOurs(focus) && !focus.is_fullscreen();
    }

    // Mutter keeps such a window in NORMAL — exactly where a ceded Desktop raised
    // over ordinary windows sits — so the Desktop would bury it, and the game
    // behind it, and the launcher could never be clicked. Under every window the
    // Desktop still covers the DE's desktop: the wallpaper is no window.
    _sinkUnderWindows(ours) {
        // Lowering puts a window at the bottom, so go top-down to keep our own order.
        for (const w of [...ours].reverse())
            lowerWindow(w);
    }

    _floatOverWindows(ours) {
        for (const w of ours)
            raiseWindow(w);
        const apps = stackedBottomToTop(mappedWindows())
            .filter(w => !this._isOurs(w) && w.is_fullscreen());
        for (const a of apps)
            raiseWindow(a);
    }

    // Kasual's overlays — the Home menu, dialogs, the OSDs — are summoned *over* a
    // running app, so unlike the ceded Desktop they must outrank even a fullscreen
    // game. make_above lifts them to Mutter's TOP layer, which a fullscreen window
    // (NORMAL) cannot reach.
    _isOverlay(win) {
        const role = this._roleOf(win);
        if (role)
            return role.layer >= OVERLAY_LAYER;
        // Roles are registered as Kasual's surfaces are built, so reloading the
        // helper under a running Kasual leaves them behind: fall back on the shape,
        // where the Desktop is the fullscreen surface and the overlays are not.
        return !win.is_fullscreen();
    }

    _pinOverApp(overlays) {
        for (const w of overlays) {
            if (!w.is_above())
                w.make_above();
            raiseWindow(w);
        }
    }

    // Layer, not map order, decides: the Desktop must stay below the overlays even
    // when it is re-shown — and so re-mapped — after them. Ceded, only the overlays:
    // raising the Desktop there would bury the game.
    _reassertStacking() {
        if (this._restacking)
            return;
        const ours = this._ourWindows();
        if (!ours.length)
            return;

        const layerOf = w => this._roleOf(w)?.layer ?? DEFAULT_LAYER;
        const ordered = (this._ceded ? ours.filter(w => this._isOverlay(w)) : ours)
            .map((w, depth) => ({w, depth}))
            .sort((a, b) => layerOf(a.w) - layerOf(b.w) || a.depth - b.depth)
            .map(({w}) => w);
        if (!ordered.length)
            return;

        // Raising emits 'restacked', so without a fixpoint every pass feeds the next.
        const all = stackedBottomToTop(mappedWindows());
        const top = all.slice(all.length - ordered.length);
        if (ordered.every((w, i) => top[i] === w && w.is_above()))
            return;

        this._restacking = true;
        for (const w of ordered) {
            if (!w.is_above())
                w.make_above();
            raiseWindow(w);
        }
        this._restacking = false;
    }

    _setUnredirectSuppressed(suppressed) {
        if (suppressed && !this._unredirectApi) {
            this._unredirectApi = unredirectApi();
            disableUnredirect(this._unredirectApi);
        } else if (!suppressed && this._unredirectApi) {
            enableUnredirect(this._unredirectApi);
            this._unredirectApi = null;
        }
    }

    // A game raising itself restacks; put Kasual back on top.
    _setRestackGuard(guarding) {
        if (guarding && !this._restackedId) {
            this._restackedId = global.display.connect(
                'restacked', () => this._reassertStacking());
        } else if (!guarding && this._restackedId) {
            global.display.disconnect(this._restackedId);
            this._restackedId = 0;
        }
    }

    _normalWindows() {
        return mappedWindows().filter(w =>
            w.get_window_type() === Meta.WindowType.NORMAL && !w.is_skip_taskbar());
    }

    _byId(id) {
        return this._normalWindows().find(w => String(w.get_id()) === id) || null;
    }

    // ── D-Bus surface ────────────────────────────────────────────────────────

    Ping() {
        return JSON.stringify({
            unredirect: unredirectApi(),
            raise: (typeof Meta.Window.prototype.raise_and_make_recent === 'function')
                ? 'raise_and_make_recent' : 'raise',
            setType: typeof Meta.Window.prototype.set_type === 'function',
        });
    }

    Debug() {
        const primary = global.display.get_primary_monitor();
        const rect = r => ({x: r.x, y: r.y, width: r.width, height: r.height});
        return JSON.stringify({
            appClass: this._appClass,
            pendingFocus: this._pendingFocus,
            focusAttempts: this._focusAttempts,
            pinned: this._pinned.size,
            unredirect: this._unredirectApi,
            monitor: rect(global.display.get_monitor_geometry(primary)),
            // Struts (top bar, docks) shrink this; layer-shell ignores them, Mutter
            // clamps ordinary windows into it.
            workArea: rect(global.workspace_manager
                .get_active_workspace().get_work_area_for_monitor(primary)),
            roles: [...this._roles].map(([title, r]) => ({title, ...r})),
            // Bottom-to-top, the order that decides what covers what.
            stack: stackedBottomToTop(mappedWindows()).map((w, depth) => {
                const actor = w.get_compositor_private();
                return {
                    depth,
                    wm_class: w.get_wm_class() || '',
                    title: w.get_title() || '',
                    pid: w.get_pid(),
                    layer: w.get_layer(),
                    type: w.get_window_type(),
                    above: w.is_above(),
                    fullscreen: w.is_fullscreen(),
                    minimized: w.minimized,
                    hidden: w.is_hidden(),
                    showing: w.showing_on_its_workspace(),
                    focus: w.has_focus(),
                    frame: rect(w.get_frame_rect()),
                    // What Mutter actually has to paint, and whether it paints it.
                    buffer: rect(w.get_buffer_rect()),
                    actor: actor ? {
                        visible: actor.visible,
                        mapped: actor.mapped,
                        opacity: actor.opacity,
                        destroyed: actor.is_destroyed(),
                        hasTexture: !!actor.get_texture(),
                        x: actor.x, y: actor.y,
                        width: actor.width, height: actor.height,
                    } : null,
                };
            }),
        }, null, 1);
    }

    // The pixels Mutter actually holds for that window, past every status flag.
    // Looked up across every window, so an unpinned one can be measured too.
    Snapshot(title, path) {
        const win = mappedWindows().find(w => w.get_title() === title);
        const actor = win?.get_compositor_private();
        if (!actor)
            return `no window titled "${title}"`;
        const image = actor.get_image(null);
        if (!image)
            return `"${title}" has no image`;
        image.writeToPNG(path);
        const parent = actor.get_parent();
        return JSON.stringify({
            wrote: path,
            size: `${image.getWidth()}x${image.getHeight()}`,
            paintVisibility: actor.get_paint_visibility(),
            paintOpacity: actor.get_paint_opacity(),
            clip: actor.get_clip(),
            hasClip: actor.has_clip,
            parent: parent ? parent.name || parent.toString() : null,
        });
    }

    ListWindows() {
        const out = this._normalWindows().map(w => ({
            id: String(w.get_id()),
            title: w.get_title() || '',
            pid: w.get_pid(),
            wm_class: w.get_wm_class() || '',
            desktop_file: appIdOf(w),
            active: w.has_focus(),
            fullscreen: w.is_fullscreen(),
        }));
        return JSON.stringify(out);
    }

    ActivateWindow(id) {
        const w = this._byId(id);
        if (w) {
            w.unminimize();
            w.activate(activationTime());
        }
    }

    CloseWindow(id) {
        const w = this._byId(id);
        if (w)
            w.delete(global.get_current_time());
    }

    MinimizeWindowsForPids(pidsJson) {
        let pids;
        try {
            pids = new Set(JSON.parse(pidsJson));
        } catch (e) {
            console.log(`${TAG} MinimizeWindowsForPids: bad JSON: ${e}`);
            return;
        }
        for (const w of this._normalWindows())
            if (pids.has(w.get_pid()))
                w.minimize();
    }

    SetSurfaceRole(title, layer, anchors, keyboard) {
        this._roles.set(title, {layer, anchors, keyboard});
        for (const win of this._ourWindows())
            if (win.get_title() === title)
                this._applyFocusPolicy(win);
        this._scheduleSync();
    }

    // Qt cannot activate its own window without a Wayland token, and Kasual is
    // summoned from a gamepad; naming the surface keeps the rest of the stack put.
    // The call lands before Qt has mapped the window, so it may have to wait.
    ActivateSurface(title) {
        this._pendingFocus = title;
        this._focusAttempts = 0;
        this._focusPending();
    }

    _focusPending() {
        if (!this._pendingFocus)
            return;
        if (this._tryFocusPending())
            this._forgetPendingFocus();
        else
            this._retryFocusPending();
    }

    _tryFocusPending() {
        const win = this._ourWindows().find(w => w.get_title() === this._pendingFocus);
        if (!win)
            return false;
        win.unminimize();
        win.activate(activationTime());
        this._reassertStacking();
        return win.has_focus();
    }

    // Mutter hands out no focus while the surface is still being mapped, so the
    // first attempt lands too early and the request has to outlive it.
    _retryFocusPending() {
        if (this._focusSourceId)
            return;
        if (++this._focusAttempts >= FOCUS_ATTEMPTS) {
            this._forgetPendingFocus();
            return;
        }
        this._focusSourceId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT, FOCUS_RETRY_MS, () => {
                this._focusSourceId = 0;
                this._focusPending();
                return GLib.SOURCE_REMOVE;
            });
    }

    _forgetPendingFocus() {
        if (this._focusSourceId)
            GLib.source_remove(this._focusSourceId);
        this._focusSourceId = 0;
        this._pendingFocus = null;
    }

    // Focus is asked for by name (above): activating every pinned window here
    // raised whichever came last, burying the Desktop's header and hint bar.
    ShowOverlay(wmClass) {
        this._appClass = wmClass;
        this._showRequested = true;
        this._ceded = false;
        this._setUnredirectSuppressed(true);   // before the first window maps
        this._sync();
    }

    // Yield the screen to the app without unmapping, so closing it reveals the
    // still-drawn Desktop with no DE flash.
    CedeOverlay(wmClass) {
        if (this._appClass === wmClass) {
            this._forgetPendingFocus();
            this._ceded = true;
            this._sync();
        }
    }

    // Off by default: a session with nobody listening must not serialize the stack
    // on every window event.
    WatchWindows(enable) {
        this._windowWatch = enable;
        if (enable)
            this._emitWindows('init');
    }

    _emitWindows(reason) {
        if (!this._windowWatch)
            return;
        const area = global.display.get_monitor_geometry(
            global.display.get_primary_monitor());
        const stack = stackedBottomToTop(mappedWindows())
            .map(w => windowRecord(w, area));
        this._dbus.emit_signal('WindowsChanged',
            new GLib.Variant('(ss)', [reason, JSON.stringify(stack)]));
    }

    // Kasual cannot answer this itself: the sink/float decision is made here, from
    // the focus, and it changes without Kasual doing anything.
    IsSunk() {
        return this._sunk;
    }

    // Gamepad input never reaches Mutter (libinput ignores joysticks), so Kasual
    // reports pad activity here. A zero-delta virtual pointer event resets the
    // session idle time and fires user-active watches (screen wake, unblank)
    // without moving the cursor — see mutter's handle_idletime_for_event().
    SimulateUserActivity() {
        if (!this._virtualPointer) {
            const seat = Clutter.get_default_backend().get_default_seat();
            this._virtualPointer = seat.create_virtual_device(
                Clutter.InputDeviceType.POINTER_DEVICE);
        }
        this._virtualPointer.notify_relative_motion(Clutter.CURRENT_TIME, 0, 0);
    }

    // The class stays registered: an OSD mapped later, over a game, must pin too.
    HideOverlay(wmClass) {
        if (this._appClass === wmClass) {
            this._forgetPendingFocus();
            this._showRequested = false;
            this._ceded = false;
            this._sync();
        }
    }
}

export default class KasualHelperExtension extends Extension {
    enable() {
        this._helper = new Helper();
    }

    disable() {
        this._helper?.destroy();
        this._helper = null;
    }
}
