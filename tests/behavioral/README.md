# Behavioral tests

End-to-end runs of the choreography Kasual Desktop is actually made of: KD
launches Steam, Steam launches the game, the Home Menu comes back over it. The
files are deliberately not named `test_*.py`, so pytest does not collect them —
this suite is run by hand against a live session before a release, not in CI. It
needs a Wayland session, a GPU and real games, and its scenarios may be hardcoded
to one developer machine's library.

It runs on every compositor Kasual Desktop supports — KDE, GNOME, Hyprland and
Sway — each proven on a live session, the whole suite green on all four. A scenario
names the windows it needs and the harness picks the backend for whatever is
running; see `PORTING.md` for how that was arrived at, down to the last product gap
it exposed (Sway would not focus a launcher behind a fullscreen window) and closed.

labwc and wayfire (Raspberry Pi OS) have a backend too — the same
wlr-foreign-toplevel connection the product uses — but no run on real hardware
yet. It reports no geometry, so there `covers_screen` is always False and only a
window that declares itself fullscreen counts as holding the screen.

## Why this exists

The unit suite covers KD's logic (parsing, filtering, command building, factory
wiring) and passes 1200+ tests. It does not cover what actually broke:

- **KD's surfaces stacked against windows we do not own.** Kingdom Come's splash
  and the Witcher 3's RED Launcher are ordinary, non-fullscreen windows that pop
  up over Steam and disappear once the engine takes the screen. They forced the
  ceding rework (`cede_depth`) on both GNOME and KDE.
- **Whether a piece of KD is really on screen.** A widget that is "shown" is not
  necessarily the current page of a stack; a surface that is mapped is not
  necessarily on top.
- **Whether the pad KD re-emits reaches the application in front.** KD grabs the
  physical pad exclusively and hands applications a `kasual-vpad` of its own making.
  Nothing about that is visible to a unit test, and a launch from a tile barely
  exercises it — `steam_kcd` navigates the whole of Steam's UI with it.
- **The choreography end to end**, across three processes we only partly control.

The point is to establish "X is on the screen right now" — including for windows
we do not own — and, as far as possible, **without looking at pixels**.

Three production bugs were found by this harness within a day of it working, each
one living in code the unit suite was happy with: the Home chrome left floating
after the controller was unplugged, the Desktop resurfacing itself with no
controller to drive it, and a domain port silently satisfied by an inherited Qt
method.

## Why not an off-the-shelf tool

- **Squish** — the commercial standard for Qt; introspects our own widgets, but is
  weak at driving foreign applications (Steam, the game). Expensive.
- **dogtail / AT-SPI** — introspection through accessibility; works for Qt
  (`QT_ACCESSIBILITY=1`), but games implement no accessibility. Brittle.
- **openQA** — conceptually the closest (it tests whole KDE/GNOME sessions in a
  VM with screenshots and "needles"), but it is heavy machinery, and a GPU-passthrough
  VM for games is a project of its own. We borrow its needle model, not the tool.
- **Playwright / Selenium** — web only. Worth noting as calibration: Playwright's
  `toBeVisible()` means "non-empty bounding box and not `display:none`" — it does
  not check occlusion by another window either. The confidence people are used to
  in HTML is reached structurally, not by magic.

So: a thin harness of our own. Two properties of KD make that cheap — it is driven
100% by gamepad (evdev), and it already ships IPC clients for the compositors in
`src/infrastructure/`.

## What "visible" means without a screenshot

### Layer 1 — the Qt tree (our own windows; the DOM equivalent)

Stacked-view questions are settled inside KD: `QWidget.isVisible()` gives
effective visibility, plus geometry, `visibleRegion()`, sibling z-order. Exposed
out of process by KD's **test API** — `ShellIntrospectionService`, a read-only
D-Bus endpoint behind `KD_TEST_API=1` that answers with the tiles, the focus, and
which shell surfaces are on screen. (For hands-on diagnosis there is also
**GammaRay**, KDAB's "DevTools for Qt".)

### Layer 2 — the compositor's scene (our windows and everyone else's)

- **KWin**: the scripting API (JS over D-Bus) gives `workspace.stackingOrder` with
  geometries, and per-window signals to drive an event watcher. **Caveat, learned
  the hard way: layer-shell surfaces do not appear there at all** — KWin's
  scripting API exposes toplevels only, so KD's own Desktop, header and hint bar
  are invisible to it. Their stacking can only come from KD itself (layer 1).
- **Hyprland**: `hyprctl layers -j` (layer-shell surfaces per output and layer)
  plus `hyprctl clients -j` (windows, fullscreen, workspace). The layer-shell
  protocol guarantees that the *overlay* layer renders above fullscreen, so
  "mapped on overlay ⇒ above the game" is a deductively sound inference.
- **GNOME**: the bundled Shell extension can read Clutter's actor tree — literally
  the compositor's scene graph (`global.get_window_actors()`, and per actor its
  visibility, opacity and paint order). The deepest introspection of the four; the
  extension can expose a test endpoint over D-Bus.
- **Sway**: `get_tree` has a `visible` field for toplevels, but barely exposes
  layer-shell — the shallowest of the four.

### Layer 3 — the protocol (the compositor admits it painted)

**wp_presentation** gives a client `presented` (with a vsync timestamp) or
`discarded` per frame, so KD could learn from the compositor that a frame of, say,
the Home Menu actually reached the screen. Weaker signals: frame callbacks
(`wl_surface.frame`, throttled for invisible surfaces) and xdg-shell's `suspended`
state (toplevels only, not layer-shell). Not built yet.

### Layer 4 — pixels (the last line, not the foundation)

Structurally we cannot establish: (a) that another surface *on the same layer* did
not come out on top; (b) that the pixels left the GPU unmangled (alpha=0, a black
frame); (c) **what is in a foreign window's frames** — a game's content exists only
as pixels.

When needed: capture from the compositor (it must include layer-shell!) — `grim` /
`wf-recorder` on wlroots, `spectacle -b -n -o` or the `org.kde.KWin.ScreenShot2`
D-Bus API on KDE, the Shell's D-Bus API on GNOME; universally, a PipeWire stream
through the ScreenCast portal. Assertions by template matching (OpenCV
`cv2.matchTemplate`, threshold ~0.95) against reference crops kept in the repo
(openQA's needle model). For fleeting things such as splashes, record the whole run
and analyse frames afterwards ("there exists a frame in which the needle matches"),
which doubles as a debugging artifact for every failure. Before building any of
this: sanity-check on each compositor that the capture really does include our
layers.

## Foreign applications (Steam, Proton/Wine games)

A *game* is a black box committing buffers, and the ceiling of inquiry there is layer
2 plus the graphics stack. **Steam is not.** Its Big Picture UI is Chromium (CEF), and
with `~/.local/share/Steam/.cef-enable-remote-debugging` in place before it starts, it
speaks the Chrome DevTools Protocol on `localhost:8080` — a real DOM, with the focus
in it. So the one foreign application we must *drive* is also the one that can be read
back, and `steam_kcd` checks every pad press against what Steam says it did.

The structural signals available for the rest:

- **Window identity and lifecycle**: a toplevel's `app_id` — Steam games get
  `steam_app_<appid>` (KCD: `steam_app_379430`, W3: `steam_app_292030`) — plus
  title, geometry, fullscreen. Event sources: KWin scripting signals (KDE),
  wlr-foreign-toplevel-management (wlroots), Mutter/Clutter signals in the
  extension (GNOME).
- **Proof of rendering**: MangoHud (already integrated in KD) sits in the game's
  render loop and logs FPS to CSV (`MANGOHUD_LOG`), so "the game has been rendering
  >0 FPS for ≥5 s" is assertable without a single pixel. Not wired into the harness
  yet — today a fullscreen window is taken as proof enough.
- **The launch pipeline**: the process tree (reaper → proton → wine), Steam's logs,
  `PROTON_LOG=1`. Each stage of failure — KD never started Steam, Steam never
  started the game, the game never mapped a window — has a different structural
  signature.

One of the three game scenarios launches through its KD tile, whose `.desktop` runs
`steam steam://rungameid/<appid>` — the shortest path, and the one a tile is for. The
other two (`steam_kcd`, `steam_w3`) go through Steam's UI on purpose, because that is the
only way to prove something no tile launch can: **that the pad Kasual Desktop re-emits
actually reaches a foreign application in the foreground.** KD grabs the physical pad
exclusively (`EVIOCGRAB`) and re-emits it as `kasual-vpad`; `kcd` hands the screen to a
game and stays out of the way, so nothing there exercises that path at all.

Driving Big Picture blind would indeed be the most brittle step imaginable. Driving it
with a read-back is not: Steam is asked after every press where its focus went, and a
press that lands nowhere fails the run on the spot instead of launching the wrong game.

## The splash / launcher case — what the right assertion is

A splash is a short-lived, non-fullscreen toplevel: it maps over Steam, lives for
a moment, disappears, and the game's fullscreen window takes the screen. Three
things follow.

1. **"The splash's toplevel mapped" is too weak an assertion.** It stays true even
   if the bug comes back and KD covers it. The real one is *"the splash is mapped
   AND nothing of KD is above it in the composition order"* — i.e. ceding worked.
2. **The window is short-lived, so the watcher must be event-driven** (subscribed
   to signals), never polling. A one-second poll can miss a splash entirely. This
   decides the architecture.
3. **A launcher is the sharper test, and it needs no structural assertion at all.**
   Where a splash is passive, the RED Launcher *waits to be activated*. A splash
   covered by KD is merely invisible; a launcher covered by KD is unclickable, and
   the run cannot go on. So reaching the game's fullscreen window is itself the
   proof that the ceded Desktop sank under it — a functional assertion that
   subsumes the structural one.

That third point is not just elegance. Whether a *ceded but still mapped* Desktop
covers a plain window turns out **not to be decidable from KD's state alone** on
KWin: a focused fullscreen window belonging to the app (Steam's black launch
screen) already outranks the TOP layer, so the answer depends on what else is in
the stack. Where a window must be used, we assert that it could be.

## The harness

```
tests/behavioral/
  run.py         the entry point: a scenario name, or --list
  scenarios/     one module per scenario — nothing but the run itself
  harness/       everything the scenarios are made of
  harness/sources/  one window backend per compositor
  artifacts/     one JSON per run: the steps, the window events, KD's own states
  PORTING.md     what is left before the suite runs on every supported compositor
```

Inside `harness/`:

- **Input driver** — `virtual_pad.py`: a virtual gamepad through `evdev.UInput`,
  shaped like an Xbox 360 pad, so it passes `GamepadWatcher._is_gamepad` and KD
  grabs it like a real one. No screen coordinates anywhere, and precise control of
  press duration (the >1 s Home hold and its 0.5 s counter-example).
- **Window source** — `window_source.py` and `sources/`: every window the run does
  not own. The port promises a *set* of windows — `{id, title, app_id, pid,
  fullscreen, covers_screen}` — and not their z-order, which Hyprland and Sway do
  not expose and no assertion here needs: "who covers whom" is answered from KD's
  own state (`desktop_sunk`, `desktop_mapped`), the same on every compositor.
  Events are pushed, never polled, so a window that lives for a moment — a splash —
  cannot be missed; `wait_for()` consumes them sequentially, which makes a chain of
  waits assert the *order* of what happened.
    - `sources/kwin.py` — a script injected into KWin's `/Scripting`, reporting the
      full `workspace.stackingOrder` on every window event.
    - `sources/gnome.py` — the Kasual Helper extension's `WindowsChanged` signal
      (Mutter offers clients no window API at all). The stream is off until the
      harness asks for it, so a normal session pays nothing for it.
    - `sources/hyprland.py` — Hyprland's `socket2` event stream; and
      `sources/sway.py` — `swaymsg -t subscribe -m`. On both the event carries no
      window list, so each lifecycle event resnapshots from `hyprctl -j clients` /
      `swaymsg -t get_tree`.
    - A compositor with no adapter: scenarios that read windows declare
      `require.window_source()` and refuse to run; the rest — the pad and KD's own
      state — run anywhere.
- **KD introspection** — `kd_client.py`: reads the shell's state from KD's test API
  (tiles, focus, surfaces, and the Home menu's sections, cards and cursor) and keeps
  every answer for the artifact. It also checks the shape of what comes back: a KD
  older than the harness is caught before the run, not by a `KeyError` halfway
  through it.
- **Navigation** — `navigation.py`: moves the tile focus with the pad, reading the
  focus back from KD after each step, so a dropped press fails loudly instead of
  launching the wrong tile.
- **Steps against KD** — `shell.py`: the Home view, launching a tile, where KD is
  while a splash or a game is up, and whether the Home Menu came back over it.
- **Steps against the game** — `game.py`: `SteamGame` — the windows of a
  `steam_app_<appid>`, the processes behind them, activating a launcher, and the
  way out. Building one registers its own shutdown with the session.
- **Steps against Steam's UI** — `steam_ui.py`: `SteamUI` reads Big Picture's focus
  over the DevTools Protocol, and `CefDebugging` puts the debug flag in place for the
  run and takes it away afterwards — an open debug port is not something to leave
  behind on someone's desktop. Read-only by design: Steam *could* be driven from here
  (the protocol dispatches input, and `SteamClient` is right there), but then the run
  would prove something about Steam's DOM instead of about KD's re-emitted pad.
- **Steps against the File Browser** — `file_browser.py`: `FileBrowserClient` reads the
  bundled browser's own test API (published only under `KD_TEST_API=1`, which it
  inherits from the KD that launched it) — where it is and what its cursor is on — so
  "I walked its folders" is a fact, not a guess at an unchanging window title.
- **The run** — `session.py`: bring-up, teardown, artifact, exit code. A scenario
  body starts with KD already on the Home view and both sources of truth open, and
  may give up anywhere by raising `ScenarioAborted` — the teardown still runs.
- **Preconditions** — `requirements.py` (see below).
- **Verdicts** — `report.py` (`PASS`/`FAIL`/`WARN`/`INFO`); every wait in the
  harness is a named constant in `timeouts.py`.
- **Live progress** — `progress.py`: the wait a step is in, its elapsed seconds and its
  budget, on one refreshing line — so a long silent wait (Steam coming up, shaders
  compiling) reads as progress, not a hang. `--notify` also raises a desktop
  notification for the long ones, the one message that carries past a fullscreen game.

Two sources of truth, deliberately: other applications' windows come from the
compositor, KD's own layer-shell surfaces come from KD.

### Writing a scenario

A module in `scenarios/` exporting a `SCENARIO`: what it needs, and what it does.
The runner discovers it by import — there is no registry to edit.

```python
TILE_ID = 'Kingdom Come Deliverance'
APPID = '379430'

def _body(session: Session) -> None:
    game = SteamGame(session, APPID)
    shell.launch_tile(session.kd, session.pad, TILE_ID)
    if game.wait_plain_window('splash') is not None:
        shell.check_kd_below(session.kd, 'splash')
    window = game.wait_fullscreen()
    game.check_process(window)
    shell.check_kd_ceded(session.kd)
    shell.check_home_menu_over_game(session.kd, session.pad, game)

SCENARIO = Scenario(
    name='kcd',
    title='launch Kingdom Come: Deliverance from its tile, recall the Home Menu over it',
    body=_body,
    requires=(
        require.window_source(),
        require.command('steam'),
        require.manual('Steam is logged in, and Kingdom Come: Deliverance is installed'),
        require.tile(TILE_ID),
    ),
)
```

A scenario must launch the app **through KD**, never through `steam://rungameid/…`
directly: the whole hide choreography (DeferredHide, CedeDepth) is armed only
inside `AppLifecycle.on_tile_activated`, so a launch from the side leaves the
HomeHeader and the hint bar sitting on top of Steam — which is exactly the bug the
first draft of this suite "passed" through.

### The scenarios

- **`minimize`** — the Home menu, Minimize, the bare desktop, BTN_MODE, and back. No
  application at all, and the only scenario whose subject is KD alone. What it guards
  is a failure invisible from inside KD: a Desktop that believes it is minimized while
  its chrome still floats over the DE looks perfectly fine to itself, so the assertions
  are about *absence* — no tiles, no wallpaper, no header, no hint bar, no menu.
- **`file_browser`** — tile → the bundled File Browser → walk its folders → Home menu
  → Close → back on the Desktop. The full life of a bundled app, and the one scenario
  that reads *both* ends of the pad's journey: KD says the press left its hands, the
  browser's own test API says it arrived. Closing goes through the Home menu's confirm,
  so the run reads the question and which way it is aimed before answering it.
- **`kcd`** — tile → a warmed Steam → the splash → the game → the Home Menu over it,
  where the in-game HUD toggle is exercised (the one place a game is already up to test
  it against). Launched from the game's own tile.
- **`kcd_cold`** — the same tile, but with Steam **cold**: the `steam://rungameid` URL
  opens Big Picture and drops the launch, so the run pushes the game through Steam's UI
  with the pad, then asserts the game reaches the screen and the Home Menu comes back
  over it as before.
- **`steam_kcd`** — tile → Big Picture → Steam's own UI, walked with the pad → the
  game. Proves KD's re-emitted pad reaches a foreign application.
- **`steam_w3`** — the same walk through Steam's UI, but the game stops at the RED Launcher,
  which has to be *used*: a window that maps after KD has ceded and must still be
  reachable by the pad.

## Preconditions

Scenarios **declare** what they need rather than documenting it, so the list below
is generated, not maintained: `python3 tests/behavioral/run.py --list` prints it,
and a requirement that can be checked is checked before the run touches the screen.
`[!]` marks the ones no code can confirm — a game being installed, a session being
logged in — which are printed and left to the person at the keyboard.

Every scenario needs:

- A Wayland session Kasual Desktop supports. The pad and KD's own state can be read
  anywhere; the windows of *other* apps need a backend for that compositor — KWin,
  Mutter, Hyprland and Sway each have one. On GNOME the
  Kasual Helper extension has to be enabled: without it KD has no window manager,
  and a run would not fail — it would pass against a KD that is not doing its job.
- `/dev/uinput` writable (the `input` group, or a udev rule) — as KD itself needs.
- **[!]** No physical gamepad connected: KD grabs the first pad it finds, and it
  must find the virtual one.
- Kasual Desktop already running, started with `KD_TEST_API=1` — checked from the
  single-instance lock (`~/.local/cache/kasual/kasual.lock`) and one call to the
  API. Both failures are told apart, because they need different fixes: KD is not
  running at all, or KD is running but was started without the test API — which a
  packaged, menu-launched instance always is, and which nothing about it betrays
  until you notice it never answers.

`file_browser` needs only a KD tile for `files` that launches the **repo's** copy of
the browser — the one that publishes the test API (an installed copy under `/usr/share`
does not).

`kcd` additionally needs:

- Steam installed, **[!]** logged in, with the game installed.
- A KD tile for the game (`TILE_ID` at the top of the scenario, matched against the
  `.desktop` stem or the displayed name; on a miss the error lists the tiles that
  exist).

`kcd_cold` needs the same tile and game, but with Steam **not running** (the cold start
is the whole point) and **[!]** the game among Big Picture's recent games — the row the
push walks when the cold start drops the launch.

`steam_kcd` and `steam_w3` need instead:

- A KD tile for Steam, whose `.desktop` opens `steam://open/bigpicture` — the desktop
  UI is not pad-navigable, and this scenario is about the pad.
- Steam **not running**: the debug flag is read at startup and only then, so the run
  has to be the one that starts it. (It puts the flag there itself, and removes it
  afterwards if it was not there already.)
- **[!]** The game among Big Picture's recent games on the home page — that is the row
  the run walks.

The list grows with the suite, and it grows in the scenarios: a YouTube scenario
will want a logged-in session in the YT app, and it will say so in its own
`requires`, not here.

## Running it (any supported compositor / Wayland)

`tests_behav.sh` is the one entry point, in two commands. In one terminal, `prepare`
seeds a throwaway config, points KD at it with `KD_CONFIG_DIR`, and launches KD with
the test API on — leave it there; with no controller connected it holds off the
screen, showing nothing:

```
./tests_behav.sh prepare           # --seed by default; --empty for the onboarding flow
```

The seed holds just the tiles the scenarios touch (plus YouTube), so they are
present whatever the machine's own catalog looks like, and KD's writes land in the
temp directory instead of your real config — `config_root()` honours `KD_CONFIG_DIR`
over `XDG_CONFIG_HOME`. (The steps are also runnable by hand:
`prepare_config.py` prints the `export KD_CONFIG_DIR=…` line, then `KD_TEST_API=1
./kasual.sh`.)

Then, in another terminal, `run` — its arguments pass straight to `run.py`:

```
./tests_behav.sh run                # all of them, one after another
./tests_behav.sh run kcd            # just this one
./tests_behav.sh run --list         # what there is and what it needs; runs nothing
```

The run's virtual pad is what brings KD up: it appears as a controller, KD's device
scan grabs it, and the Home view comes on screen. That is also the first thing the
run asserts.

Each scenario is a run of its own — its own pad, its own watcher, its own artifact —
so one that fails does not take the next one down with it; running them all ends
with a line per scenario, and a non-zero exit if any of them failed.

Output: `PASS/FAIL/WARN/INFO` steps on stdout, plus an artifact in
`artifacts/<scenario>-<date>.json` holding both the compositor's events and the
timeline of KD's own state — read them together; a failed stacking assertion is
only legible against what KD was doing at the time. On the way out, including after
a failure or a Ctrl+C, the run closes the game and Steam and lets KD minimize
itself, all **without asserting**: leaving an app cleanly is its own scenario, not
a coda to this one.

## Traps (every one of them cost a debugging session)

- A D-Bus slot **must not** be named `event`: it overrides `QObject.event()`, the
  very handler QtDBus delivers incoming calls through. The message arrives and is
  silently dropped.
- `QCoreApplication(sys.argv)` left unassigned is garbage-collected: the service
  name stays on the bus, the object path vanishes, and the watcher receives
  nothing — with no error anywhere.
- KWin 6.5 has no `workspace.stackingOrderChanged` (the signal is per-window). A
  JS error kills the whole script silently; the only trace is
  `journalctl --user -b | grep kwin_scripting`.
- `loadScript` answers `-1` as a **successful** reply when a script under that
  plugin name is still loaded after a crashed run — clear it with `qdbus6
  org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript behavioral_watcher`.
- A launcher is its own process and outlives the game: killing the game's pid
  leaves it running, and next run it is still on screen, ready to be mistaken for
  a fresh one.

And five paid for by `steam_kcd`, every one of them a press that vanished:

- **Steam ignores the pad unless its own window has the keyboard focus.** A test run
  from a terminal leaves the focus in that terminal — but that is a fact about the rig,
  not about KD, and it is not papered over: the scenario asserts that Steam *got* the
  focus, and a KD that fails to hand it over fails the run.
- **Big Picture answers the debugger while it is still logging in.** Its loading screens
  are pages like any other, and a press that lands on them is gone. The UI proper is
  told apart by weight: a handful of `.Focusable` elements against some two hundred.
- **The intro animation swallows the press that skips it** — and it plays on after the
  UI is up and answering. Waiting it out is the only fix; there is nothing to query.
- **Steam's menus, popups and toasts are CEF pages of their own.** Reading the focus
  from "the Big Picture page" answers for a page that merely *had* it: a closed menu
  will happily report its last focused item forever. Ask `document.hasFocus()` which
  page holds it, and treat "nobody" as an answer rather than as a reason to guess.
- **The CSS class names are per-build hashes** (`WYgDg9NyCcMIVuMyZ_NBC`). What survives
  Steam's updates is `.Focusable`, `.gpfocus` and the ARIA labels — the accessibility
  layer, not the styling one.

## Next steps

- **Tiles the run brings with it.** A scenario depends on the operator's catalog — a
  tile for `files`, for KCD, for Steam — and on which copy of a bundled app that tile
  happens to launch. Half the preconditions below are that dependency, and one of them
  has already cost a debugging session. Give Kasual Desktop an `--apps-dir` and the run
  can supply its own `.desktop` files, pointing at the repo's own builds: the tile
  requirements disappear, and so does "is /usr/share current?". (Swapping
  `XDG_CONFIG_HOME` would do it without touching Kasual Desktop, but it takes the
  preferences with it.)
- MangoHud FPS as proof the game actually renders; today a fullscreen window is
  taken as proof enough.
- **Shader-processing progress, from the same channel `steam_kcd` reads.** Between the
  press of Play and the game's first frame the screen sits black for minutes, and a
  player cannot tell a shader rebuild from a hang. Steam knows which it is — it is in
  the DOM the scenario already talks to — so KD could say so. A test-only channel that
  turns out to answer a product question is worth following.
- A `pytest-bdd` (Gherkin) layer, once there are enough scenarios for the repeated
  parts to be obvious. The split into `scenarios/` and `harness/` is the groundwork:
  a scenario body is already a sequence of named steps over a `Session`, so the step
  definitions a feature file needs are the functions in `shell.py` and `game.py`,
  and the scenarios in `test_scenarios.md` would rewrite nearly 1:1:

  ```gherkin
  Scenario: launching KCD from its tile and recalling the Home Menu
    Given KD is on the Home view                       # KD introspection
    When I press A on the Kingdom Come tile            # uinput
    Then a non-fullscreen steam_app_379430 toplevel appears   # watcher
    And no KD surface is above the splash              # KD introspection
    And the toplevel goes fullscreen within 60 s       # watcher
    And the game renders >0 FPS for 5 s                # MangoHud
    When I hold Home for 1.2 s                         # uinput
    Then the Home Menu is above the game               # KD introspection
  ```

  What Gherkin buys is a scenario readable by someone who does not read Python; what
  it costs is a layer of indirection between a failure and the code that produced it.
  Worth paying once the suite is large enough that scenarios are read more often than
  they are written — not before.

- An optional screen capture for what only pixels can answer (see Layer 4 above).
