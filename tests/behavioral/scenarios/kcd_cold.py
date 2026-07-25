"""Kasual Desktop → KCD tile → a cold Steam → Big Picture → the game → the Home Menu.

The companion to `kcd`, which warms Steam first so the tile runs the game straight. Here
Steam is not running when the tile fires `steam://rungameid/…`: the URL cold-starts Steam,
which comes up in Big Picture rather than running the game. So this is the path where the
tile puts a player in front of Steam's own UI, not the game.

KD launched the *game*, not Steam, so it does not recognise Big Picture as the app it is
waiting for — it keeps the Home surface mapped, below Steam, and cedes only once the game
itself takes the screen. The scenario gives the cold start a moment to run the game on its
own, and if it does not, pushes it from Big Picture the way a player would: the pad KD
re-emits walks the home row to the game and presses Play. The game must reach the screen
either way.
"""

from tests.behavioral.harness import requirements as require
from tests.behavioral.harness import shell, steam_ui, timeouts
from tests.behavioral.harness.game import SteamGame
from tests.behavioral.harness.session import Scenario, Session
from tests.behavioral.harness.steam_ui import CefDebugging, SteamUI

TILE_ID = 'Kingdom Come Deliverance'
GAME = 'Kingdom Come: Deliverance'
APPID = '379430'


def _body(session: Session) -> None:
    # Steam reads the debug flag at startup only, so it goes in before the tile starts
    # Steam — and comes out again on the way out, wherever the run ends.
    debugging = CefDebugging()
    session.add_cleanup(debugging.restore)
    debugging.enable()

    game = SteamGame(session, APPID)
    shell.launch_tile(session.kd, session.pad, TILE_ID)

    steam = SteamUI()
    session.add_cleanup(steam.close)
    steam_ui.expect_big_picture(steam)

    # The cold start may run the game on its own; only if it does not is Steam's UI
    # driven — and only then does Steam need the window focus for the pad to reach it.
    if not game.launched(timeouts.GAME_LAUNCH):
        steam_ui.expect_window_focus(steam)
        steam_ui.focus_game(steam, session.pad, APPID, GAME)
        steam_ui.open_game_page(steam, session.pad, GAME)
        steam_ui.press_play(session.pad)

    if game.wait_plain_window('splash') is not None:
        shell.check_kd_below(session.kd, 'splash')

    window = game.wait_fullscreen()
    game.check_process(window)
    shell.check_kd_ceded(session.kd)
    shell.check_home_menu_over_game(session.kd, session.pad)


SCENARIO = Scenario(
    name='kcd_cold',
    title='launch Kingdom Come from its tile with Steam cold, pushing it through Big '
          'Picture if the cold start drops the launch',
    body=_body,
    requires=(
        require.window_source(),
        require.command('steam'),
        require.steam_devtools_client(),
        require.not_running(
            'steam',
            'Steam is not running (a cold start is the whole point, and only a Steam '
            'started afterwards picks up the debug flag)',
            remedy='quit Steam (steam -shutdown) and run again'),
        require.manual('Steam is logged in, and Kingdom Come: Deliverance is installed'),
        require.manual(f'{GAME} is among the recent games on Big Picture\'s home page — '
                       'the row the push walks'),
        require.tile(TILE_ID),
    ),
)
