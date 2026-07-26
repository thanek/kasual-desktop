"""Kasual Desktop → Steam → *through Steam's own UI* → Kingdom Come → the Home Menu.

Where `kcd` launches the game straight from its tile, this one goes the way a player
on a couch does: KD launches Big Picture, and the game is then started from inside
Steam — its home row is walked with the pad, the game's page is opened, Play is
pressed.

That detour is the point. Kasual Desktop grabs the physical pad exclusively and
re-emits it as `kasual-vpad`, and a tile launch proves nothing about where that pad
ends up: `kcd` hands the screen to a game and stays out of the way. Here every press
has to land in Steam, and Steam is asked after each one where its focus went — the same
read-back discipline `navigation.py` applies to KD, over the debugger Steam's Chromium
exposes. `steam_w3` walks the same UI and then has a launcher to drive; this one stops at a
game that needs no launcher, which makes it the shorter proof of the pad alone.

It is also the scenario that answers the question a tile launch cannot: whether KD
gives the window focus away at all. Steam reads its gamepad only while its own window
holds it.
"""

from tests.behavioral.harness import requirements as require
from tests.behavioral.harness import shell, steam_ui
from tests.behavioral.harness.game import SteamGame
from tests.behavioral.harness.session import Scenario, Session
from tests.behavioral.harness.steam_ui import CefDebugging, SteamUI

STEAM_TILE = 'steam'          # the KD tile, whose .desktop opens steam://open/bigpicture
GAME = 'Kingdom Come: Deliverance'
APPID = '379430'


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

    if game.wait_plain_window('splash') is not None:
        shell.check_kd_below(session.kd, 'splash')

    window = game.wait_fullscreen()
    game.check_process(window)
    shell.check_kd_ceded(session.kd)
    shell.check_home_menu_over_game(session.kd, session.pad, game)


SCENARIO = Scenario(
    name='steam_kcd',
    title='launch Kingdom Come through Steam\'s own UI, driven by the pad KD re-emits',
    body=_body,
    requires=(
        require.window_source(),
        require.command('steam'),
        require.not_running(
            'steam',
            'Steam is not running (the run starts it, and only a Steam started '
            'afterwards picks up the debug flag)',
            remedy='quit Steam (steam -shutdown) and run again'),
        require.manual('Steam is logged in, and Kingdom Come: Deliverance is installed'),
        require.manual(f'{GAME} is among the recent games on Big Picture\'s home page — '
                       'that is the row the run walks'),
        require.tile(STEAM_TILE),
    ),
)
