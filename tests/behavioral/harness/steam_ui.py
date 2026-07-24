"""Steam's own UI, read through the debugger its Chromium exposes.

Big Picture is Chromium (CEF), and with the debug flag on it speaks the Chrome
DevTools Protocol — so a foreign, opaque application gains the one thing that makes
driving it honest: a read-back. Every pad press is checked against what Steam says
has the focus, exactly as `navigation.py` checks its presses against KD.

Four things are load-bearing, and none of them is a guess:

* `.Focusable` and `aria-label` survive Steam's updates. The class names beside them
  (`WYgDg9NyCcMIVuMyZ_NBC`) are per-build hashes and must never be matched against.
* Big Picture is not one page. Its main menu and quick-access panel are CEF targets
  of their own, so the focus has to be read from whichever page currently holds it —
  `document.hasFocus()` says which.
* The focus Steam reports is the one drawn on screen: the ring around the tile.
  Verified against a screenshot before this was trusted.
* A game is identified by its appid, never by its name. Steam hangs `data-id` on the
  tile's panel, above whatever the pad actually focused, and that number is the same in
  every language and every Steam build. The label is not: Big Picture localises it, so
  a run matching on the English name walks straight past `Wiedźmin 3: Dziki Gon` and
  reports the game as missing. Names are for the report; appids are for the decisions.
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

# Steam answers on the debugger while it is still logging in, and its loading
# screens carry a handful of focusables where the UI proper carries hundreds.
UI_IS_UP = 20

# Steam's UI is localised, and the button is read by its name.
PLAY_LABELS = frozenset({'graj', 'zagraj', 'play'})

# Steam swaps Play for one of these when the game is not ready, and read by name they
# are the difference between "the pad never reached Play" and "there was no Play to reach".
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
    // gpfocus is Steam's own marker for where the pad cursor sits; activeElement
    // agrees with it, and is the fallback when Steam has not set it.
    var el = document.querySelector('.gpfocus') || document.activeElement;
    var name = el ? (labelOf(el) || el.innerText) : '';
    // The appid sits on the tile's panel, several levels above what holds the focus.
    var appid = '';
    for (var node = el; node; node = node.parentElement) {
        var id = node.getAttribute ? node.getAttribute('data-id') : null;
        if (id && /^[0-9]+$/.test(id)) { appid = id; break; }
    }
    return JSON.stringify({
        hasFocus: document.hasFocus(),
        focusables: document.querySelectorAll('.Focusable').length,
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
    """Where Steam's pad cursor sits: the appid decides, the label describes.

    The label is whatever Steam calls it in the operator's language, so it belongs in
    reports and nowhere near a comparison.
    """
    label: str
    appid: str

    def __str__(self) -> str:
        if self.label and self.appid:
            return f'{self.label!r} (app {self.appid})'
        if self.appid:
            return f'an unlabelled tile (app {self.appid})'
        return repr(self.label)


def _pump(seconds: float) -> None:
    """Sleep without going deaf: the window source's events arrive on Qt's event loop,
    and a plain sleep here leaves its window snapshots stale."""
    QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    time.sleep(seconds)


class CefDebugging:
    """The debug flag, put there for the run and taken away after it.

    An open debug port lets any local process drive the user's Steam, so a run that
    turns it on owns turning it off again. One that was there already is left alone:
    it is not ours to remove.
    """

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

    Read-only on purpose. Steam could be driven from here — the protocol dispatches
    input, and `SteamClient` is right there — but then the run would prove something
    about Steam's DOM instead of about the pad Kasual Desktop re-emits, which is the
    only reason this scenario exists.
    """

    def __init__(self, endpoint: str = ENDPOINT) -> None:
        self._endpoint = endpoint
        self._connections: dict[str, websocket.WebSocket] = {}
        self._next_id = 0

    # ── the pages ────────────────────────────────────────────────────────────

    def _pages(self) -> list[dict]:
        # Toasts are pages too, and Steam reports them as focused while they are up —
        # "Podłączono kontroler…" would then answer for the focus behind it.
        try:
            with urllib.request.urlopen(f'{self._endpoint}/json/list', timeout=2) as reply:
                return [t for t in json.load(reply)
                        if t.get('type') == 'page'
                        and not t.get('title', '').startswith('notificationtoasts')]
        except (urllib.error.URLError, TimeoutError, OSError):
            return []

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
        """Wait for Big Picture's UI itself — not for the login and loading screens it
        shows first, which answer on the debugger just as readily and swallow a press
        that lands on them."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if any(self._probe(page)['focusables'] > UI_IS_UP for page in self._pages()):
                return
            _pump(1.0)
        raise SteamUnavailable(
            f'no Big Picture UI on {self._endpoint} after {timeout_s:.0f}s — was Steam '
            'started with the CEF debug flag already in place?')

    def _probe(self, page: dict) -> dict:
        try:
            return json.loads(self._evaluate(page, _FOCUS_JS))
        except (ValueError, OSError, websocket.WebSocketException):
            self._connections.pop(page['webSocketDebuggerUrl'], None)
            return {'hasFocus': False, 'focusables': 0, 'label': '', 'appid': ''}

    # ── what it has focused ──────────────────────────────────────────────────

    def focused(self) -> Focus:
        """What Steam has focused, in whichever of its pages holds the focus — the main
        menu is a page of its own.

        Empty when no page holds it, which means Steam does not have the window focus
        and is ignoring the pad. Answering from a page that merely *had* the focus is
        how a run comes to believe a press landed when it went nowhere.
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
        for page in self._pages():
            if self._probe(page)['focusables'] > UI_IS_UP:   # the UI, not a menu
                return self._evaluate(page, _WHERE_JS)
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

        Gives up as soon as the focus stops moving: the end of a row in Steam is
        silent, and a scan that presses on regardless is how a test comes to launch
        the wrong game.
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
    """Steam reads its gamepad only while its own window has the focus, so this is
    also the assertion that KD handed the screen over rather than keeping it."""
    if steam.wait_focus_gained(timeouts.CEDE):
        report('Steam has the window focus', 'PASS', 'KD handed it over')
        return
    report('Steam has the window focus', 'FAIL',
           'no Steam page holds the focus — the pad will not reach it')
    raise ScenarioAborted('Steam never got the window focus')


def focus_game(steam: SteamUI, pad: VirtualPad, appid: str, name: str) -> None:
    """Walk Big Picture's home page to the game, reading the focus back each press.

    This is what the scenario is *for*: the pad Kasual Desktop re-emits has to reach a
    foreign application, and every press has to land where we think it did.

    Where the focus starts depends on how Steam came up — on the games, or on the news
    row below them — and until a direction is pressed, the ring on screen is not yet a
    pad cursor: the first press only engages it. So the run engages it deliberately,
    down and back up, and only then trusts what it reads.

    The row opens on whichever game was played last, which the run before this one may
    well have changed, so the target can sit on either side of the start. Hence the
    sweep back: a failed rightward scan leaves the cursor at the far end of the row, and
    only a leftward one long enough to cross the whole row reaches what lies left of
    where the walk began.

    *name* never decides anything — it is what the failure says out loud. The tile is
    recognised by *appid*, which no translation of Steam's UI can move.
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
