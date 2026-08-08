"""Kasual Desktop → tile → Steam → the KCD splash → the game → the Home Menu.

KD launches the game itself (pad → tile → A), so the run exercises the real
choreography — DeferredHide, CedeDepth — that a bare `steam://rungameid/…` would
bypass. Kingdom Come's splash is a plain window that comes and goes on its own, so
the scenario only has to assert that nothing of KD sits over it.

Steam is warmed up in the background first: a cold Steam started by the tile's URL
opens in Big Picture and drops the launch, so the tile would prove nothing until the
client is already up.
"""

from tests.behavioral.harness import requirements as require
from tests.behavioral.harness import shell, timeouts
from tests.behavioral.harness.game import SteamGame, warm_up_steam
from tests.behavioral.harness.session import Scenario, Session

TILE_ID = 'Kingdom Come Deliverance'
APPID = '379430'


def _body(session: Session) -> None:
    game = SteamGame(session, APPID)

    # A cold Steam started by the tile's steam://rungameid opens in Big Picture and
    # drops the launch; warming it first, off the screen, leaves KD on the Home view
    # to drive the tile from.
    warm_up_steam()
    shell.expect_home_view(session.kd)
    shell.launch_tile(session.kd, session.pad, TILE_ID)

    # The splash is passive — nobody has to click it — so KD's own state is the
    # only evidence that it was not buried under the shell.
    if game.wait_plain_window('splash', timeouts.GAME_LAUNCH) is not None:
        shell.check_kd_below(session.kd, 'splash')

    window = game.wait_fullscreen()
    game.check_process(window)
    game.check_hud_not_overridden(window)
    shell.check_kd_ceded(session.kd)

    # A game is the only context the HUD toggle exists in, and the menu is the only
    # way to it — so it is asserted here, where a game is already running, rather than
    # in a scenario of its own that would have to compile its shaders again to ask one
    # question. Picking a card collapses the menu, so flipping it back needs the hold
    # again: over a game, KD keeps the hold and leaves the click to the game.
    shell.check_home_menu_over_game(session.kd, session.pad, game)
    shell.toggle_hud(session.kd, session.pad)
    shell.open_home_menu(session.kd, session.pad, hold=True)
    shell.toggle_hud(session.kd, session.pad)


SCENARIO = Scenario(
    name='kcd',
    title='launch Kingdom Come from its tile straight into the game (Steam warmed in the '
          'background first), recall the Home Menu over it',
    body=_body,
    requires=(
        require.window_source(),
        require.command('steam'),
        require.mangohud_configured(),
        require.manual('Steam is logged in, and Kingdom Come: Deliverance is installed'),
        require.tile(TILE_ID),
    ),
)
