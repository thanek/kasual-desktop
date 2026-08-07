"""A keyboard moves the tile cursor, for as long as the Desktop is on screen.

The one failure a gamepad cannot see: Kasual Desktop reads the pad from evdev, which
reaches it whether the compositor focused its surface or not, so a Desktop that is
visible but unfocused drives perfectly from the pad while every keystroke goes to the
window underneath.

Pressing real keys and reading the cursor back therefore proves more than asking the
compositor who holds the focus — which only GNOME could answer anyway, the Desktop
being a layer-shell surface everywhere else.
"""

from __future__ import annotations

from tests.behavioral.harness import requirements as require
from tests.behavioral.harness import shell, timeouts
from tests.behavioral.harness.kd_client import KDClient
from tests.behavioral.harness.report import report
from tests.behavioral.harness.session import Scenario, Session
from tests.behavioral.harness.virtual_keyboard import VirtualKeyboard
from tests.behavioral.harness.window_source import WindowSource


def _where_the_keys_went(windows: WindowSource) -> str:
    holder = next((w for w in windows.last_stack() if w['focused']), None)
    if holder is None:
        return 'this compositor does not report which window holds the keyboard'
    return f'{holder["title"]!r} ({holder["app_id"]}) holds the keyboard instead'


def _focus_the_tiles(kd: KDClient, keyboard: VirtualKeyboard) -> dict:
    snapshot = kd.snapshot()
    if snapshot['focus']['zone'] == 'tiles':
        return snapshot
    keyboard.down()
    return kd.wait_until(lambda s: s['focus']['zone'] == 'tiles',
                         timeouts.TILE_FOCUS, 'the keyboard putting the focus on the tiles')


def expect_the_keyboard_moves_the_cursor(
    kd: KDClient, keyboard: VirtualKeyboard, windows: WindowSource, when: str,
) -> None:
    what = f'the keyboard moves the tile cursor {when}'
    try:
        snapshot = _focus_the_tiles(kd, keyboard)
    except TimeoutError:
        report(what, 'FAIL', f'the tiles never took the focus — {_where_the_keys_went(windows)}')
        return

    before = snapshot['focus']['tile_index']
    on_the_last_tile = before == len(snapshot['tiles']) - 1
    keyboard.left() if on_the_last_tile else keyboard.right()

    try:
        moved = kd.wait_until(lambda s: s['focus']['tile_index'] != before,
                              timeouts.TILE_FOCUS, 'the tile cursor to move')
    except TimeoutError:
        report(what, 'FAIL',
               f'the cursor stayed on tile {before} — {_where_the_keys_went(windows)}')
        return
    report(what, 'PASS', f'tile {before} → {moved["focus"]["tile_index"]}')


def _body(session: Session) -> None:
    kd, pad, windows = session.kd, session.pad, session.windows
    keyboard = VirtualKeyboard()
    session.add_cleanup(keyboard.close)
    session.record('keyboard', keyboard.presses)
    report('virtual keyboard created', 'PASS', keyboard.device_path)

    expect_the_keyboard_moves_the_cursor(kd, keyboard, windows, 'on the Home view')

    shell.open_home_menu(kd, pad)
    shell.pick_menu_action(kd, pad, shell.HIDE_DESKTOP)
    shell.expect_minimized(kd)

    shell.open_home_menu(kd, pad)
    shell.pick_menu_action(kd, pad, shell.RETURN_TO_DESKTOP)
    shell.expect_home_view_restored(kd)
    expect_the_keyboard_moves_the_cursor(
        kd, keyboard, windows, 'after being recalled from minimized')


SCENARIO = Scenario(
    name='keyboard-navigation',
    title='a keyboard drives the Desktop whenever it is on screen',
    body=_body,
    requires=(
        require.tiles(at_least=2),
    ),
)
