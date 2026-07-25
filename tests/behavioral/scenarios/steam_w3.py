"""Kasual Desktop → Steam → *through Steam's own UI* → The Witcher 3 → the RED Launcher
→ the game → the Home Menu.

Where Kingdom Come goes fullscreen on its own, the Witcher 3 stops at the RED Launcher
and waits: the game only starts once "Play" is activated there. That makes the launcher
the sharper test of ceding. A splash KD covers is merely invisible; a *launcher* KD
covers is unusable, and the run cannot get past it — so reaching the game's fullscreen
window is itself the proof that the ceded Desktop sank under it.

Two things have to hold at once here, and nothing else in the suite needs both. The pad
Kasual Desktop re-emits has to reach Steam, every press read back from Steam itself
(what `steam_kcd` proves); and then it has to reach a launcher that maps while Big
Picture is still on the screen — the harder half, because that window arrives after KD
has already ceded and stopped being asked for anything.
"""

import time

from tests.behavioral.harness import requirements as require
from tests.behavioral.harness import shell, steam_ui
from tests.behavioral.harness.game import SteamGame
from tests.behavioral.harness.report import ScenarioAborted
from tests.behavioral.harness.session import Scenario, Session
from tests.behavioral.harness.steam_ui import CefDebugging, SteamUI

STEAM_TILE = 'steam'          # the KD tile, whose .desktop opens steam://open/bigpicture
GAME = 'The Witcher 3: Wild Hunt'   # for the report only; the tile is found by APPID
APPID = '292030'
LAUNCHER = 'RED Launcher'


def _body(session: Session) -> None:
    # Steam reads the debug flag at startup only, so it goes in before KD starts it —
    # and comes out again on the way out, wherever the run ends.
    debugging = CefDebugging()
    session.add_cleanup(debugging.restore)
    debugging.enable()

    game = SteamGame(session, APPID)
    shell.launch_tile(session.kd, session.pad, STEAM_TILE)

    steam = SteamUI()
    session.add_cleanup(steam.close)
    steam_ui.expect_big_picture(steam)
    steam_ui.expect_window_focus(steam)
    shell.check_kd_ceded(session.kd)

    steam_ui.focus_game(steam, session.pad, APPID, GAME)
    steam_ui.open_game_page(steam, session.pad, GAME)
    steam_ui.press_play(session.pad)

    if game.wait_plain_window(LAUNCHER) is None:
        raise ScenarioAborted(f'the {LAUNCHER} never mapped')
    shell.note_kd_state(session.kd, LAUNCHER)

    time.sleep(2)   # let the launcher take focus before it is driven
    game.activate_launcher(LAUNCHER)

    window = game.wait_fullscreen()
    game.check_process(window)
    shell.check_kd_ceded(session.kd)
    shell.check_home_menu_over_game(session.kd, session.pad)


SCENARIO = Scenario(
    name='steam_w3',
    title='launch The Witcher 3 through Steam\'s own UI, past the RED Launcher, '
          'recall the Home Menu over it',
    body=_body,
    requires=(
        require.window_source(),
        require.command('steam'),
        require.steam_devtools_client(),
        require.not_running(
            'steam',
            'Steam is not running (the run starts it, and only a Steam started '
            'afterwards picks up the debug flag)',
            remedy='quit Steam (steam -shutdown) and run again'),
        require.manual('Steam is logged in, and The Witcher 3 is installed'),
        require.manual(f'{GAME} is among the recent games on Big Picture\'s home page — '
                       'that is the row the run walks'),
        require.tile(STEAM_TILE),
    ),
)
