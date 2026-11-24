"""A color picked in a tile's settings shows on the tile at once, and B does not undo it."""

from domain.menu.palette import TILE_COLORS

from tests.behavioral.harness import requirements as require
from tests.behavioral.harness import shell
from tests.behavioral.harness.kd_client import KDClient
from tests.behavioral.harness.session import Scenario, Session

TILE_ID = 'files'


def _a_color_the_tile_does_not_have(kd: KDClient) -> str:
    current = kd.tile(TILE_ID)['color']
    return next(color.lower() for color in TILE_COLORS if color.lower() != current)


def _body(session: Session) -> None:
    kd, pad = session.kd, session.pad
    color = _a_color_the_tile_does_not_have(kd)

    shell.open_tile_menu(kd, pad, TILE_ID)
    shell.pick_tile_action(kd, pad, shell.SETTINGS)
    shell.expect_tile_settings_open(kd)

    shell.pick_tile_color(kd, pad, color)
    shell.expect_tile_color(kd, TILE_ID, color, when='with the settings still open')

    shell.leave_tile_settings(kd, pad)
    shell.expect_tile_color(kd, TILE_ID, color, when='after leaving with B')
    shell.expect_home_view_restored(kd)


SCENARIO = Scenario(
    name='tile_color',
    title='change a tile\'s color in its settings, and see it on the tile',
    body=_body,
    requires=(
        require.throwaway_config(),
        require.tile(TILE_ID),
    ),
)
