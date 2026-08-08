"""The steps that read and drive Kasual Desktop itself.

One half of the run's truth. The other half — every window we do not own — comes
from the compositor; KD's own surfaces cannot, because layer-shell surfaces never
appear in KWin's stacking order.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from tests.behavioral.harness import timeouts
from tests.behavioral.harness.kd_client import KasualDesktopUnavailable, KDClient
from tests.behavioral.harness.navigation import focus_tile
from tests.behavioral.harness.report import ScenarioAborted, report
from tests.behavioral.harness.virtual_pad import VirtualPad

if TYPE_CHECKING:
    from tests.behavioral.harness.game import SteamGame


# ── bring-up ─────────────────────────────────────────────────────────────────

def expect_home_view(kd: KDClient) -> None:
    """KD stays off the screen until a controller appears and surfaces the Home view
    when one does, so this waits out its device scan finding the virtual pad —
    pressing before it has been grabbed is a lost press."""
    try:
        kd.wait_until(
            lambda s: s['desktop_visible'] and s['home_header_mapped']
            and s['hint_bar_mapped'],
            timeouts.HOME_VIEW, 'KD on the Home view with the virtual pad grabbed')
    except TimeoutError as exc:
        s = kd.snapshot()
        report('KD on the Home view', 'FAIL',
               f'desktop={s["desktop_visible"]} header={s["home_header_mapped"]} '
               f'hintbar={s["hint_bar_mapped"]} — did KD grab the pad?')
        raise ScenarioAborted('KD never reached the Home view') from exc
    report('KD on the Home view', 'PASS', 'desktop, header and hint bar on screen')


def launch_tile(kd: KDClient, pad: VirtualPad, tile_id: str) -> None:
    # Focusing by pad and reading the focus back proves KD actually receives the
    # virtual pad — nothing else in the run does.
    snapshot = focus_tile(kd, pad, tile_id)
    report('focused the tile with the pad', 'PASS',
           f'{tile_id} at index {snapshot["focus"]["tile_index"]}')
    pad.confirm()
    report('A pressed on the tile', 'PASS', 'KD launches the app')


def restore_tile(kd: KDClient, pad: VirtualPad, tile_id: str) -> None:
    focus_tile(kd, pad, tile_id)
    pad.confirm()
    report('A pressed on the running tile', 'PASS', 'KD restores the app')
    expect_foreground(kd, kd.tile_name(tile_id))


# ── where KD is ──────────────────────────────────────────────────────────────

def _nothing_of_kd_above_plain_windows(s: dict) -> bool:
    """A launcher or splash is a plain window, which a Desktop left mapped on the
    TOP layer would cover. KD has two honest ways out — unmap the Desktop, or sink
    it below the app's windows — and the chrome must be off screen either way."""
    return (
        not s['home_header_mapped']
        and not s['hint_bar_mapped']
        and (not s['desktop_mapped'] or s['desktop_sunk'])
    )


def check_kd_below(kd: KDClient, what: str) -> None:
    """Nothing of KD may sit over a launcher or splash."""
    try:
        s = kd.wait_until(
            _nothing_of_kd_above_plain_windows, timeouts.CEDE,
            f'KD off the {what}: desktop unmapped or sunk, chrome off screen')
    except TimeoutError:
        s = kd.snapshot()
        report(f'no KD surface above the {what}', 'FAIL',
               f'mapped={s["desktop_mapped"]} sunk={s["desktop_sunk"]} '
               f'header={s["home_header_mapped"]} hintbar={s["hint_bar_mapped"]}')
        return
    report(f'no KD surface above the {what}', 'PASS',
           'desktop sunk' if s['desktop_sunk'] else 'desktop unmapped')


def note_kd_state(kd: KDClient, what: str) -> None:
    """Record where KD is while *what* is up, and pass no verdict.

    Whether a ceded-but-mapped Desktop actually covers a plain window is not
    decidable from KD's state on KWin: it depends on what else is stacked (a focused
    fullscreen window of the app — Steam's black launch screen — already outranks the
    TOP layer). Where the window must be *used*, the run asserts instead that it
    could be: an unreachable launcher fails the scenario by itself.
    """
    s = kd.snapshot()
    report(f'KD while the {what} is up', 'INFO',
           f'visible={s["desktop_visible"]} mapped={s["desktop_mapped"]} '
           f'sunk={s["desktop_sunk"]} header={s["home_header_mapped"]} '
           f'hintbar={s["hint_bar_mapped"]}')


def check_kd_ceded(kd: KDClient) -> None:
    try:
        kd.wait_until(
            lambda s: not s['desktop_visible'] and not s['home_header_mapped']
            and not s['hint_bar_mapped'],
            timeouts.CEDE, 'KD off screen under the running app')
    except TimeoutError:
        s = kd.snapshot()
        report('KD ceded the screen', 'FAIL',
               f'visible={s["desktop_visible"]} header={s["home_header_mapped"]} '
               f'hintbar={s["hint_bar_mapped"]}')
        return
    report('KD ceded the screen', 'PASS')


def expect_foreground(kd: KDClient, app: str) -> None:
    """KD reads the foreground from the *focused* window, and the menu's cards act on
    whatever it decides that is — so a launched app that never took focus makes "Close"
    close something else. It once closed the terminal the run was started from.
    """
    try:
        kd.wait_until(lambda s: s['foreground'] == app, timeouts.CEDE,
                      f'KD to have {app!r} in the foreground')
    except TimeoutError as exc:
        foreground = kd.snapshot()['foreground']
        report('KD has the launched app in front', 'FAIL',
               f'KD believes {foreground!r} is in front, not {app!r} — did the app take '
               'focus?')
        raise ScenarioAborted(
            f'KD would act on {foreground!r} — refusing to drive its menu') from exc
    report('KD has the launched app in front', 'PASS', repr(app))


def check_home_menu_over_game(kd: KDClient, pad: VirtualPad,
                              game: SteamGame) -> None:
    time.sleep(5)   # let the engine settle past the launcher
    pad.hold_home(1.2)
    try:
        # The Home menu is an overlay-layer surface: mapped ⇒ above the game.
        kd.wait_until(lambda s: s['home_menu']['open'], timeouts.HOME_MENU,
                      'Home menu open over the game')
    except TimeoutError:
        report('Home Menu above the game', 'FAIL',
               'Home held for 1.2 s, menu never opened')
        return
    report('Home Menu above the game', 'PASS', 'overlay-layer surface mapped')
    game.check_still_on_screen('Home menu')


# ── the Home menu ────────────────────────────────────────────────────────────

# The action keys KD reports for its menu cards.
GAMEPAD_ACCESS    = 'gamepad_access'
HIDE_DESKTOP      = 'hide_desktop'
RETURN_TO_DESKTOP = 'return_to_desktop'
RETURN_TO_APP     = 'return_to_app'
CLOSE_APP         = 'close_app'
TOGGLE_HUD        = 'toggle_hud'

QUICK   = 'quick'     # the sliders
ACTIONS = 'actions'   # the cards
HUD     = 'hud'       # the performance-HUD toggle, offered over a game and nowhere else


def _focused_item(snapshot: dict) -> dict | None:
    for section in snapshot['home_menu']['sections']:
        for item in section['items']:
            if item['focused']:
                return item
    return None


def _locate(snapshot: dict, action: str) -> tuple[int, int] | None:
    """Where a card sits: which section, and which slot in it."""
    for section_index, section in enumerate(snapshot['home_menu']['sections']):
        for index, item in enumerate(section['items']):
            if item['action'] == action:
                return section_index, index
    return None


def _columns(snapshot: dict, section_index: int) -> int:
    return max(1, snapshot['home_menu']['sections'][section_index]['columns'])


def _section(snapshot: dict, kind: str) -> dict | None:
    return next((s for s in snapshot['home_menu']['sections'] if s['kind'] == kind), None)


def open_home_menu(kd: KDClient, pad: VirtualPad, *, hold: bool = False) -> None:
    """BTN_MODE — the gesture that recalls KD wherever it is, minimized included.

    An app can claim the click for itself and leave KD the *hold* (a game does, so its
    own Guide button keeps working); over such an app a short press never reaches KD.
    """
    pad.hold_home(1.2) if hold else pad.home()
    try:
        kd.wait_until(lambda s: s['home_menu']['open'], timeouts.HOME_MENU,
                      'the Home menu open')
    except TimeoutError as exc:
        report('Home menu open', 'FAIL', 'BTN_MODE pressed, the menu never opened')
        raise ScenarioAborted('the Home menu never opened') from exc
    focused = _focused_item(kd.snapshot())
    report('Home menu open', 'PASS',
           f'focused on {focused["label"]!r}' if focused else 'nothing focused')


def expect_menu_offers(kd: KDClient, actions: tuple[str, ...], focused: str) -> None:
    """The menu must offer exactly *actions* as its cards, with *focused* pre-selected.

    The pre-focus is not a detail: it is what makes the menu usable in one press, and
    it differs by context — Minimize when KD is minimized, Return to Home otherwise.
    """
    snapshot = kd.snapshot()
    menu = snapshot['home_menu']
    cards = tuple(item['action'] for section in menu['sections']
                  if section['kind'] == ACTIONS for item in section['items'])
    sliders = [item['action'] for section in menu['sections']
               if section['kind'] == QUICK for item in section['items']]

    if cards != actions:
        report('the menu offers what it should', 'FAIL',
               f'expected {list(actions)}, found {list(cards)}')
        return
    if not sliders:
        report('the menu offers what it should', 'FAIL', 'no sliders section')
        return

    focused_item = _focused_item(snapshot)
    if focused_item is None or focused_item['action'] != focused:
        report('the menu offers what it should', 'FAIL',
               f'expected {focused!r} pre-focused, found '
               f'{focused_item["action"] if focused_item else None!r}')
        return
    report('the menu offers what it should', 'PASS',
           f'sliders: {sliders}, cards: {list(cards)}, focused: {focused!r}')


def focus_menu_action(kd: KDClient, pad: VirtualPad, action: str) -> dict:
    """Walk the menu to *action*, reading the focus back at every step.

    The menu is sections of grids, and up/down spills from one section into the next —
    so crossing sections and moving within one are the same two presses, taken in that
    order.
    """
    snapshot = kd.snapshot()
    target = _locate(snapshot, action)
    focused = _focused_item(snapshot)
    if target is None or focused is None:
        report(f'focused {action!r} in the menu', 'FAIL',
               'no such card, or nothing focused')
        raise ScenarioAborted(f'{action!r} is not on the menu')

    for _ in range(sum(len(s['items']) for s in snapshot['home_menu']['sections']) + 4):
        here = _locate(snapshot, focused['action'])
        if here == target:
            return focused
        before = focused['action']
        if here[0] != target[0]:
            pad.down() if here[0] < target[0] else pad.up()
        else:
            columns = _columns(snapshot, target[0])
            if here[1] // columns != target[1] // columns:
                pad.down() if here[1] < target[1] else pad.up()
            else:
                pad.right() if here[1] < target[1] else pad.left()
        try:
            snapshot = kd.wait_until(
                lambda s, b=before: (_focused_item(s) or {}).get('action') != b,
                timeouts.TILE_FOCUS, f'the menu focus to move off {before!r}')
        except TimeoutError as exc:
            report(f'focused {action!r} in the menu', 'FAIL',
                   f'the focus would not move off {before!r} — is KD reading the pad?')
            raise ScenarioAborted('the menu focus is stuck') from exc

        focused = _focused_item(snapshot)
        if focused is None:
            # A closed menu focuses nothing, which the wait above reads as "it moved".
            report(f'focused {action!r} in the menu', 'FAIL',
                   'the menu closed while the run was walking to it')
            raise ScenarioAborted('the Home menu closed on its own')

    report(f'focused {action!r} in the menu', 'FAIL', 'the focus never got there')
    raise ScenarioAborted(f'could not focus {action!r}')


def pick_menu_action(kd: KDClient, pad: VirtualPad, action: str) -> None:
    focused = focus_menu_action(kd, pad, action)
    pad.confirm()
    report(f'picked {action!r} in the menu', 'PASS', f'A pressed on {focused["label"]!r}')


# ── the performance HUD ──────────────────────────────────────────────────────

def expect_no_hud_card(kd: KDClient, what: str) -> None:
    """The HUD is a game's business. Over anything else the card must not be there —
    a silent regression nobody would notice until the menu grew a card that does
    nothing."""
    if _section(kd.snapshot(), HUD) is None:
        report(f'no HUD card over the {what}', 'PASS', 'the toggle is offered to games only')
        return
    report(f'no HUD card over the {what}', 'FAIL', 'the HUD toggle is on the menu')


def toggle_hud(kd: KDClient, pad: VirtualPad) -> None:
    """Flip the HUD from the menu, and check that KD's own state flipped with it."""
    snapshot = kd.snapshot()
    if _section(snapshot, HUD) is None:
        report('the menu offers the HUD toggle', 'FAIL', 'no HUD card over the game')
        raise ScenarioAborted('the HUD toggle is not on the menu')
    was = snapshot['hud']['enabled']
    report('the menu offers the HUD toggle', 'PASS',
           f'{_section(snapshot, HUD)["items"][0]["label"]!r} '
           f'(HUD is {"on" if was else "off"})')

    pick_menu_action(kd, pad, TOGGLE_HUD)
    try:
        kd.wait_until(lambda s: s['hud']['enabled'] != was, timeouts.CEDE,
                      f'the HUD to turn {"off" if was else "on"}')
    except TimeoutError:
        report('the HUD toggle takes effect', 'FAIL',
               f'still {"on" if was else "off"} after the press')
        return
    report('the HUD toggle takes effect', 'PASS',
           f'{"on" if was else "off"} → {"off" if was else "on"}')


# ── a tile's own popover ─────────────────────────────────────────────────────

LAUNCH   = 'launch'
RESTORE  = 'restore'
CLOSE    = 'close'
MOVE     = 'move'
SETTINGS = 'settings'
UNPIN    = 'unpin'


def expect_tile_running(kd: KDClient, tile_id: str, running: bool = True) -> None:
    tile = kd.tile(tile_id)
    if tile['running'] is running:
        report(f'the {tile_id!r} tile reads as {_running_word(running)}', 'PASS')
        return
    report(f'the {tile_id!r} tile reads as {_running_word(running)}', 'FAIL',
           f'KD says {_running_word(tile["running"])}')


def _running_word(running: bool) -> str:
    return 'running' if running else 'not running'


def _focused_tile_item(snapshot: dict) -> dict | None:
    return next((item for item in snapshot['tile_menu']['items'] if item['focused']),
                None)


def open_tile_menu(kd: KDClient, pad: VirtualPad, tile_id: str) -> None:
    focus_tile(kd, pad, tile_id)
    pad.tile_menu()
    try:
        kd.wait_until(lambda s: s['tile_menu']['open'], timeouts.HOME_MENU,
                      f'the popover of the {tile_id!r} tile')
    except TimeoutError as exc:
        report('tile menu open', 'FAIL', 'X pressed on the tile, no popover appeared')
        raise ScenarioAborted('the tile popover never opened') from exc
    focused = _focused_tile_item(kd.snapshot())
    report('tile menu open', 'PASS',
           f'focused on {focused["label"]!r}' if focused else 'nothing focused')


def expect_tile_menu_offers(kd: KDClient, actions: tuple[str, ...]) -> None:
    offered = tuple(item['action'] for item in kd.snapshot()['tile_menu']['items']
                    if item['action'] != 'separator')
    if offered != actions:
        report('the tile menu offers what it should', 'FAIL',
               f'expected {list(actions)}, found {list(offered)}')
        return
    report('the tile menu offers what it should', 'PASS', f'{list(offered)}')


def pick_tile_action(kd: KDClient, pad: VirtualPad, action: str) -> None:
    items = [item['action'] for item in kd.snapshot()['tile_menu']['items']]
    if action not in items:
        report(f'picked {action!r} in the tile menu', 'FAIL', f'not offered: {items}')
        raise ScenarioAborted(f'{action!r} is not in the tile menu')

    for _ in range(len(items) + 1):
        focused = _focused_tile_item(kd.snapshot())
        if focused is not None and focused['action'] == action:
            pad.confirm()
            report(f'picked {action!r} in the tile menu', 'PASS',
                   f'A pressed on {focused["label"]!r}')
            return
        before = focused['action'] if focused else None
        pad.down()
        try:
            kd.wait_until(
                lambda s, b=before: (_focused_tile_item(s) or {}).get('action') != b,
                timeouts.TILE_FOCUS, f'the popover cursor to move off {before!r}')
        except TimeoutError:
            report(f'picked {action!r} in the tile menu', 'FAIL',
                   f'the cursor would not move off {before!r}')
            raise ScenarioAborted('the tile popover cursor is stuck')

    report(f'picked {action!r} in the tile menu', 'FAIL',
           f'walked the whole popover without reaching {action!r}')
    raise ScenarioAborted(f'{action!r} never took the focus')


def close_from_open_menu(kd: KDClient, pad: VirtualPad, about: str) -> None:
    pick_menu_action(kd, pad, CLOSE_APP)
    expect_confirm(kd, about=about)
    confirm(kd, pad)


def expect_minimized(kd: KDClient) -> None:
    """Minimize means *gone*: no desktop, no wallpaper, no chrome, no menu — the DE
    underneath, as if KD were not running."""
    def off_screen(s: dict) -> bool:
        return not (s['desktop_visible'] or s['desktop_mapped']
                    or s['home_header_mapped'] or s['hint_bar_mapped']
                    or s['home_menu']['open'])

    try:
        kd.wait_until(off_screen, timeouts.CEDE, 'KD off the screen entirely')
    except TimeoutError:
        s = kd.snapshot()
        report('KD minimized', 'FAIL',
               f'desktop={s["desktop_visible"]} mapped={s["desktop_mapped"]} '
               f'header={s["home_header_mapped"]} hintbar={s["hint_bar_mapped"]} '
               f'menu={s["home_menu"]["open"]}')
        return
    report('KD minimized', 'PASS', 'desktop, wallpaper, chrome and menu all off screen')


def expect_home_view_restored(kd: KDClient) -> None:
    def home_view(s: dict) -> bool:
        return (s['desktop_visible'] and s['home_header_mapped']
                and s['hint_bar_mapped'] and not s['home_menu']['open'])

    try:
        kd.wait_until(home_view, timeouts.CEDE, 'the Home view back, the menu gone')
    except TimeoutError:
        s = kd.snapshot()
        report('back on the Home view', 'FAIL',
               f'desktop={s["desktop_visible"]} header={s["home_header_mapped"]} '
               f'hintbar={s["hint_bar_mapped"]} menu={s["home_menu"]["open"]}')
        return
    report('back on the Home view', 'PASS', 'tiles, header and hint bar back, menu closed')


def expect_confirm(kd: KDClient, about: str | None = None) -> None:
    """Closing an app is gated by a confirmation — and it is a *question*, so the run
    reads which answer A is aimed at, and what is being asked about, rather than
    pressing and finding out."""
    try:
        snapshot = kd.wait_until(lambda s: s['confirm']['open'], timeouts.CEDE,
                                 'the close confirmation')
    except TimeoutError as exc:
        report('closing asks first', 'FAIL', 'no confirmation appeared')
        raise ScenarioAborted('the close confirmation never appeared') from exc

    confirm = snapshot['confirm']
    if about is not None and about not in confirm['question']:
        report('closing asks first', 'FAIL',
               f'the question is about something else: {confirm["question"]!r}')
        raise ScenarioAborted(f'the confirmation does not name {about!r}')
    if not confirm['confirm_focused']:
        report('closing asks first', 'FAIL',
               f'{confirm["question"]!r} — but A would answer "no"')
        raise ScenarioAborted('the confirmation is not focused on Yes')
    report('closing asks first', 'PASS', f'{confirm["question"]!r}, with Yes focused')


def confirm(kd: KDClient, pad: VirtualPad) -> None:
    pad.confirm()
    try:
        kd.wait_until(lambda s: not s['confirm']['open'], timeouts.CEDE,
                      'the confirmation to close')
    except TimeoutError:
        report('confirmed', 'FAIL', 'the confirmation stayed on screen')
        return
    report('confirmed', 'PASS', 'A pressed on Yes')


# ── teardown ─────────────────────────────────────────────────────────────────

def await_no_foreground(kd: KDClient) -> None:
    """Wait until KD has *noticed* the app is gone. Killing its processes does not end
    KD's belief in it, and when that belief dies KD returns to the Home screen — inside
    the next scenario, if this one did not wait for it."""
    try:
        kd.wait_until(lambda s: s['foreground'] is None, timeouts.EXIT,
                      'Kasual Desktop to notice the app is gone')
    except TimeoutError:
        print(f'  Kasual Desktop still believes {kd.snapshot()["foreground"]!r} is '
              'running — the next scenario may be interrupted by its return',
              flush=True)
        return
    except KasualDesktopUnavailable as exc:
        print(f'  KD unreachable: {exc}', flush=True)
        return
    print('  KD has no app in the foreground', flush=True)


def await_minimized(kd: KDClient) -> None:
    """Unasserted, like the rest of the teardown — it only says what was left behind."""
    try:
        kd.wait_until(
            lambda s: not (s['desktop_visible'] or s['home_header_mapped']
                           or s['hint_bar_mapped']),
            timeouts.EXIT, 'KD fully off screen')
        print('  KD minimized', flush=True)
    except TimeoutError:
        s = kd.snapshot()
        print(f'  KD still partly on screen: desktop={s["desktop_visible"]} '
              f'header={s["home_header_mapped"]} hintbar={s["hint_bar_mapped"]}',
              flush=True)
    except KasualDesktopUnavailable as exc:
        print(f'  KD unreachable: {exc}', flush=True)
