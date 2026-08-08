"""Steam's own UI, read through the debugger its Chromium exposes, so every pad
press can be checked against what Steam says has the focus.

Load-bearing, none of it a guess:

* `.Focusable` and `aria-label` survive Steam's updates; the class names beside them
  are per-build hashes and must never be matched against.
* Big Picture is several CEF pages, so the focus is read from whichever holds it —
  `document.hasFocus()` says which.
* A game is identified by its appid, never its name: Big Picture localises labels,
  and a run matching English walks straight past `Wiedźmin 3: Dziki Gon`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import websocket
from PyQt6.QtCore import QCoreApplication, QEventLoop

from tests.behavioral.harness import timeouts
from tests.behavioral.harness.report import ScenarioAborted, report
from tests.behavioral.harness.virtual_pad import VirtualPad

ENDPOINT = 'http://localhost:8080'

MAX_HOME_ROW = 20   # games on Big Picture's home row before the run gives up

# There whenever Steam runs at all, Big Picture or no — so a page answering on the
# debugger cannot mean Big Picture is up. Big Picture brings pages of its own.
SHARED_CONTEXT = 'SharedJSContext'

# Even among those, Steam answers while it is still logging in, and its loading
# screens carry a handful of focusables where the UI proper carries hundreds — but a
# drawn Big Picture home has been seen carrying thirteen, so the count is only one way
# in. The other is a tile keyed by appid, which no loading screen has.
UI_IS_UP = 20

# Steam's UI is localised, and the button is read by its name.
PLAY_LABELS = frozenset({'graj', 'zagraj', 'play'})

# Steam swaps Play for one of these when the game is not ready: the difference
# between "the pad never reached Play" and "there was no Play to reach".
NOT_READY_LABELS = {
    'wstrzymaj': 'the game is downloading or updating',
    'pause': 'the game is downloading or updating',
    'wznów': 'the game download is paused',
    'resume': 'the game download is paused',
    'zainstaluj': 'the game is not installed',
    'install': 'the game is not installed',
    'aktualizuj': 'the game needs an update before it can start',
    'update': 'the game needs an update before it can start',
}

# Steam reads this at startup, and only then.
CEF_FLAG = Path.home() / '.local' / 'share' / 'Steam' / '.cef-enable-remote-debugging'

_FOCUS_JS = """
(function () {
    function labelOf(node) {
        if (!node) return '';
        var label = node.getAttribute('aria-label');
        if (label) return label;
        var ids = node.getAttribute('aria-labelledby');
        if (ids) {
            return ids.split(/\\s+/).map(function (id) {
                var target = document.getElementById(id);
                return target ? target.innerText : '';
            }).join(' ');
        }
        return '';
    }
    // gpfocus is Steam's own marker for the pad cursor; activeElement is the
    // fallback when Steam has not set it.
    var el = document.querySelector('.gpfocus') || document.activeElement;
    var name = el ? (labelOf(el) || el.innerText) : '';
    // The appid sits on the tile's panel, above what holds the focus.
    var appid = '';
    for (var node = el; node; node = node.parentElement) {
        var id = node.getAttribute ? node.getAttribute('data-id') : null;
        if (id && /^[0-9]+$/.test(id)) { appid = id; break; }
    }
    var tiles = 0;
    document.querySelectorAll('[data-id]').forEach(function (node) {
        if (/^[0-9]+$/.test(node.getAttribute('data-id'))) tiles++;
    });
    return JSON.stringify({
        hasFocus: document.hasFocus(),
        focusables: document.querySelectorAll('.Focusable').length,
        tiles: tiles,
        gpfocus: !!document.querySelector('.gpfocus'),
        label: String(name).replace(/\\s+/g, ' ').trim().slice(0, 120),
        appid: appid
    });
})()
"""


_WHERE_JS = """
(document.body.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 100)
"""


class SteamUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Focus:
    """Where Steam's pad cursor sits: the appid decides, the label only describes —
    it is localised, so it belongs in reports and nowhere near a comparison."""
    label: str
    appid: str

    def __str__(self) -> str:
        if self.label and self.appid:
            return f'{self.label!r} (app {self.appid})'
        if self.appid:
            return f'an unlabelled tile (app {self.appid})'
        return repr(self.label)


def _is_up(probe: dict) -> bool:
    return probe['focusables'] > UI_IS_UP or probe['tiles'] > 0


def _pump(seconds: float) -> None:
    """Sleep without going deaf: the window source's events arrive on Qt's event
    loop, and a plain sleep leaves its snapshots stale."""
    QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    time.sleep(seconds)


class CefDebugging:
    """The debug flag, put there for the run and taken away after it — an open debug
    port lets any local process drive Steam. One already there is not ours to
    remove."""

    def __init__(self) -> None:
        self._ours = False

    def enable(self) -> None:
        if CEF_FLAG.exists():
            return
        CEF_FLAG.parent.mkdir(parents=True, exist_ok=True)
        CEF_FLAG.touch()
        self._ours = True

    def restore(self) -> None:
        if self._ours and CEF_FLAG.exists():
            CEF_FLAG.unlink()
            self._ours = False
            print('  Steam CEF debug flag removed', flush=True)


class SteamUI:
    """Big Picture, over the DevTools Protocol: what has the focus, and nothing else.

    Read-only on purpose: driving Steam from here would prove something about its
    DOM instead of about the pad Kasual Desktop re-emits.
    """

    def __init__(self, endpoint: str = ENDPOINT) -> None:
        self._endpoint = endpoint
        self._connections: dict[str, websocket.WebSocket] = {}
        self._next_id = 0
        self._unreachable: Exception | None = None

    # ── the pages ────────────────────────────────────────────────────────────

    def _pages(self) -> list[dict]:
        # Toasts are pages too and report themselves focused while they are up.
        try:
            with urllib.request.urlopen(f'{self._endpoint}/json/list', timeout=2) as reply:
                pages = [t for t in json.load(reply)
                         if t.get('type') == 'page'
                         and not t.get('title', '').startswith('notificationtoasts')]
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self._unreachable = exc
            return []
        self._unreachable = None
        return pages

    def _own_pages(self) -> list[dict]:
        """Big Picture's pages: everything but the context Steam always has open."""
        return [p for p in self._pages() if p.get('title') != SHARED_CONTEXT]

    def _connection(self, page: dict) -> websocket.WebSocket:
        url = page['webSocketDebuggerUrl']
        connection = self._connections.get(url)
        if connection is None:
            connection = websocket.create_connection(url, timeout=5)
            self._connections[url] = connection
        return connection

    def _evaluate(self, page: dict, expression: str) -> str:
        connection = self._connection(page)
        self._next_id += 1
        request_id = self._next_id
        connection.send(json.dumps({
            'id': request_id, 'method': 'Runtime.evaluate',
            'params': {'expression': expression, 'returnByValue': True},
        }))
        while True:
            message = json.loads(connection.recv())
            if message.get('id') != request_id:
                continue   # an event, not our answer
            result = message.get('result', {}).get('result', {})
            return str(result.get('value', ''))

    def close(self) -> None:
        for connection in self._connections.values():
            try:
                connection.close()
            except OSError:
                pass
        self._connections.clear()

    # ── waiting for it ───────────────────────────────────────────────────────

    def connect(self, timeout_s: float = timeouts.STEAM_UI) -> None:
        """Wait for a page of Big Picture's own to render something navigable.

        Not for a count of focusables: how many a home page carries is a matter of
        the build and of what is on the row, so a threshold only guesses at someone
        else's DOM. That anything focusable exists is what says the pad can land.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if any(_is_up(self._probe(page)) for page in self._own_pages()):
                return
            _pump(1.0)
        raise SteamUnavailable(
            f'no Big Picture UI on {self._endpoint} after {timeout_s:.0f}s — '
            f'{self._diagnosis()}')

    def _diagnosis(self) -> str:
        """What the debugger was saying when the wait ran out — a silent port and a
        Steam short of its UI fail the same way here, and blaming the flag for both
        sends the next run after the wrong thing."""
        pages = self._pages()
        if self._unreachable is not None:
            return (f'the debugger does not answer ({self._unreachable}) — was Steam '
                    'started with the CEF debug flag already in place?')
        if not pages:
            return 'the debugger answers, but Steam has no page open at all'
        probed = sorted(((self._probe(page), page) for page in pages),
                        key=lambda pair: pair[0]['focusables'], reverse=True)
        seen = ', '.join(
            f'{page.get("title", "")!r}: {probe["focusables"]} focusable(s), '
            f'{probe["tiles"]} tile(s)'
            f'{", pad cursor" if probe["gpfocus"] else ""}'
            f'{", window focus" if probe["hasFocus"] else ""}'
            for probe, page in probed if probe['focusables'] or probe['tiles'])
        empty = sum(1 for probe, _ in probed
                    if not (probe['focusables'] or probe['tiles']))
        seen = ', '.join(filter(None, (seen, f'{empty} empty page(s)' if empty else '')))
        try:
            showing = self._evaluate(probed[0][1], _WHERE_JS)
        except (OSError, websocket.WebSocketException) as exc:
            showing = f'(unreadable: {exc})'
        return (f'the debugger answers and Steam has pages, but none carries a UI '
                f'(> {UI_IS_UP} focusables, or a tile to walk to) — {seen}; the '
                f'fullest one is showing {showing!r}')

    def _probe(self, page: dict) -> dict:
        try:
            return json.loads(self._evaluate(page, _FOCUS_JS))
        except (ValueError, OSError, websocket.WebSocketException):
            self._connections.pop(page['webSocketDebuggerUrl'], None)
            return {'hasFocus': False, 'focusables': 0, 'tiles': 0, 'gpfocus': False,
                    'label': '', 'appid': ''}

    # ── what it has focused ──────────────────────────────────────────────────

    def focused(self) -> Focus:
        """What Steam has focused, in whichever of its pages holds the focus.

        Empty when none does, which means Steam has not got the window focus and is
        ignoring the pad — answering from a page that merely *had* it is how a run
        comes to believe a press landed when it went nowhere.
        """
        for page in self._pages():
            probe = self._probe(page)
            if probe['hasFocus']:
                return Focus(probe['label'], probe.get('appid', ''))
        return Focus('', '')

    def focus(self) -> str:
        return self.focused().label

    def has_window_focus(self) -> bool:
        return any(self._probe(page)['hasFocus'] for page in self._pages())

    def where(self) -> str:
        """What the UI is showing, in its own words — for when a press went somewhere
        other than where the run believed."""
        for page in self._own_pages():
            if _is_up(self._probe(page)):   # the UI, not a menu or a loading screen
                return self._evaluate(page, _WHERE_JS) or '(no Steam UI)'
        return '(no Steam UI)'

    def wait_focus_gained(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.has_window_focus():
                return True
            _pump(0.5)
        return False

    def step(self, move: Callable[[], None]) -> Focus:
        """One press, and the focus it left behind."""
        move()
        _pump(0.4)   # the focus ring animates; read it once it has landed
        return self.focused()

    def wait_focus_in(self, wanted: frozenset[str], timeout_s: float) -> str | None:
        """Wait for the focus to land on one of *wanted*. Steam's pages animate in, so
        the first thing focused after a press is not always the last."""
        deadline = time.monotonic() + timeout_s
        while True:
            focused = self.focus()
            if focused.strip().casefold() in wanted:
                return focused
            if time.monotonic() >= deadline:
                return None
            _pump(0.3)

    def seek_app(self, appid: str, move: Callable[[], None], max_steps: int) -> bool:
        """Press *move* until the focused tile is *appid*, reading it back each time.

        Gives up once the focus stops moving: the end of a row is silent, and a scan
        that presses on regardless is how a test launches the wrong game.
        """
        seen = self.focused()
        if seen.appid == appid:
            return True
        stuck = 0
        for _ in range(max_steps):
            landed = self.step(move)
            if landed.appid == appid:
                return True
            stuck = stuck + 1 if landed == seen else 0
            if stuck >= 3:
                return False
            seen = landed
        return False


# ── steps ────────────────────────────────────────────────────────────────────

def expect_big_picture(steam: SteamUI) -> None:
    try:
        steam.connect()
    except SteamUnavailable as unavailable:
        report('Big Picture up', 'FAIL', str(unavailable))
        raise ScenarioAborted('Steam never showed its Big Picture UI') from unavailable
    # The UI answers before its intro animation has finished playing, and a press that
    # lands during the animation only skips it — it never reaches what is underneath.
    _pump(timeouts.STEAM_INTRO)
    report('Big Picture up', 'PASS', 'its UI answers, and the intro has played out')


def expect_window_focus(steam: SteamUI) -> None:
    """Steam reads its gamepad only while its window has the focus, so this also
    asserts that KD handed the screen over."""
    if steam.wait_focus_gained(timeouts.CEDE):
        report('Steam has the window focus', 'PASS', 'KD handed it over')
        return
    report('Steam has the window focus', 'FAIL',
           'no Steam page holds the focus — the pad will not reach it')
    raise ScenarioAborted('Steam never got the window focus')


def focus_game(steam: SteamUI, pad: VirtualPad, appid: str, name: str) -> None:
    """Walk Big Picture's home page to the game, reading the focus back each press.

    Down and back up first: until a direction is pressed the ring on screen is not
    yet a pad cursor. Then rightwards and, failing that, twice as far leftwards —
    the row opens on whichever game was played last, so the target can lie either
    side of the start, and a failed rightward scan ends at the far end of the row.
    """
    steam.step(pad.down)
    steam.step(pad.up)
    if (steam.seek_app(appid, pad.right, MAX_HOME_ROW)
            or steam.seek_app(appid, pad.left, 2 * MAX_HOME_ROW)):
        report('the pad reaches Steam', 'PASS', f'focus walked to {steam.focused()}')
        return
    report('the pad reaches Steam', 'FAIL',
           f'focus never reached {name} (app {appid}); it sits on {steam.focused()} — is '
           'the game among the recent games on Big Picture\'s home page?')
    raise ScenarioAborted(f'could not focus app {appid} ({name}) in Steam')


def open_game_page(steam: SteamUI, pad: VirtualPad, name: str) -> None:
    """Open the game's page, where Steam puts the focus on Play by itself."""
    pad.confirm()
    focused = steam.wait_focus_in(PLAY_LABELS, timeouts.STEAM_PAGE)
    if focused is not None:
        report(f'{name} page open in Steam', 'PASS', f'{focused!r} has the focus')
        return
    landed = steam.focus()
    reason = NOT_READY_LABELS.get(landed.strip().casefold())
    if reason is not None:
        report(f'{name} page open in Steam', 'FAIL',
               f'{reason} — Steam shows {landed!r} where Play would be; let it finish '
               'and run again')
        raise ScenarioAborted(f'{name} is not ready to play: {reason}')
    report(f'{name} page open in Steam', 'FAIL',
           f'Play never took the focus; it sits on {landed!r}')
    raise ScenarioAborted('the game page did not open with Play focused')


def press_play(pad: VirtualPad) -> None:
    pad.confirm()
    report('Play pressed in Steam', 'PASS', 'the game starts from Steam, not from a tile')
