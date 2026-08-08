"""Kasual Desktop → tile → Steam → the KCD splash → the game → the Home Menu.

KD launches the game itself (pad → tile → A), so the run exercises the real
choreography — DeferredHide, CedeDepth — that a bare `steam://rungameid/…` would
bypass. Kingdom Come's splash is a plain window that comes and goes on its own, so
the scenario only has to assert that nothing of KD sits over it.

Steam is warmed up in the background first: a cold Steam started by the tile's URL
opens in Big Picture and drops the launch, so the tile would prove nothing until the
client is already up. The warm client carries the HUD's environment, because it — not
the `steam://` forwarder KD spawns — is what starts the game.
"""

from tests.behavioral.harness import requirements as require
from tests.behavioral.harness import shell, timeouts
from tests.behavioral.harness.game import SteamGame, warm_up_steam
from tests.behavioral.harness.session import Scenario, Session

TILE_ID = 'Kingdom Come Deliverance'
APPID = '379430'


def _flip_the_hud_off_and_on_again(session: Session, game: SteamGame) -> None:
    shell.check_home_menu_over_game(session.kd, session.pad, game)
    shell.toggle_hud(session.kd, session.pad)
    shell.open_home_menu(session.kd, session.pad, hold=True)
    shell.toggle_hud(session.kd, session.pad)


def _body(session: Session) -> None:
    game = SteamGame(session, APPID)

    warm_up_steam()
    shell.expect_home_view(session.kd)
    shell.launch_tile(session.kd, session.pad, TILE_ID)

    if game.wait_plain_window('splash', timeouts.GAME_LAUNCH) is not None:
        shell.check_kd_below(session.kd, 'splash')

    window = game.wait_fullscreen()
    game.check_process(window)
    game.check_hud_attached(window)
    game.check_hud_not_overridden(window)
    shell.check_kd_ceded(session.kd)

    _flip_the_hud_off_and_on_again(session, game)


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
