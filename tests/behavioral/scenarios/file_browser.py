"""Tile → File Browser → walk its folders → BTN_MODE → Close it → back on the Desktop.

The full life of a bundled app, and the one scenario where both ends of the pad's
journey can be read: Kasual Desktop says the press left its hands, the browser says it
arrived. Between them lies the exclusive grab and the `kasual-vpad` re-emitter, which
`steam_kcd` proves against a foreign application and this one against our own.

Closing goes through the Home menu, and closing is *asked about* — so the run reads the
confirmation and which way it is aimed before answering it.

The tile is the one that runs the repo's copy of the browser: the installed copy under
/usr/share is a different build, and only the repo's publishes the test API.
"""

from tests.behavioral.harness import file_browser, shell
from tests.behavioral.harness import requirements as require
from tests.behavioral.harness.file_browser import FileBrowserClient
from tests.behavioral.harness.session import Scenario, Session

TILE_ID = 'files'

CARDS = (shell.RETURN_TO_APP, shell.CLOSE_APP, shell.RETURN_TO_DESKTOP)


def _body(session: Session) -> None:
    kd, pad = session.kd, session.pad
    name = kd.tile_name(TILE_ID)

    shell.launch_tile(kd, pad, TILE_ID)

    browser = FileBrowserClient()
    session.record('file_browser_snapshots', browser.history)
    session.add_cleanup(lambda: file_browser.shut_down(browser))
    file_browser.expect_browser(browser)
    shell.check_kd_ceded(kd)
    shell.expect_foreground(kd, name)
    file_browser.browse_folders(browser, pad)

    shell.open_home_menu(kd, pad)
    # Over a running app the menu offers its own three cards, pre-focused on the one
    # that costs nothing — returning to the app.
    shell.expect_menu_offers(kd, CARDS, focused=shell.RETURN_TO_APP)
    shell.expect_no_hud_card(kd, name)
    shell.expect_foreground(kd, name)
    shell.close_from_open_menu(kd, pad, about=name)

    file_browser.expect_gone(browser)
    shell.expect_home_view_restored(kd)


SCENARIO = Scenario(
    name='file_browser',
    title='launch the File Browser, walk its folders, and close it from the Home menu',
    body=_body,
    requires=(
        require.tile(TILE_ID),
        require.manual('the File Browser the tile launches is current — it is the one '
                       'that has to publish the test API, so an installed copy under '
                       '/usr/share must be refreshed from apps/ first'),
    ),
)
