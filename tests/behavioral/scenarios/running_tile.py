"""Tile → File Browser → back to the Home screen with it still running → close it
from the tile's own popover.

The other way out of an app, and the other way of ending one. `file_browser` never
leaves the app: it opens the Home Menu over it and closes it there. Here the player
walks away instead — "Return to Home screen" over a running app minimizes it and
brings Kasual Desktop back — and then meets the app again as what the Home screen
shows of it: a tile that knows it is running, whose popover offers Restore and Close
where a stopped one would offer Launch.

The File Browser rather than a game because none of this is about the application:
it starts in a second, and its own test API is what proves it really ended.
"""

from tests.behavioral.harness import file_browser, shell
from tests.behavioral.harness import requirements as require
from tests.behavioral.harness.file_browser import FileBrowserClient
from tests.behavioral.harness.session import Scenario, Session

TILE_ID = 'files'

RUNNING_TILE_OFFERS = (shell.RESTORE, shell.CLOSE,
                       shell.MOVE, shell.SETTINGS, shell.UNPIN)


def _leave_it_running(session: Session) -> None:
    shell.open_home_menu(session.kd, session.pad)
    shell.pick_menu_action(session.kd, session.pad, shell.RETURN_TO_DESKTOP)
    shell.expect_home_view_restored(session.kd)


def _close_it_from_its_tile(session: Session, name: str) -> None:
    shell.open_tile_menu(session.kd, session.pad, TILE_ID)
    shell.expect_tile_menu_offers(session.kd, RUNNING_TILE_OFFERS)
    shell.pick_tile_action(session.kd, session.pad, shell.CLOSE)
    shell.expect_confirm(session.kd, about=name)
    shell.confirm(session.kd, session.pad)


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

    _leave_it_running(session)
    shell.expect_tile_running(kd, TILE_ID)
    file_browser.expect_browser(browser)

    _close_it_from_its_tile(session, name)
    file_browser.expect_gone(browser)
    shell.expect_tile_running(kd, TILE_ID, running=False)
    shell.expect_home_view_restored(kd)


SCENARIO = Scenario(
    name='running_tile',
    title='leave the File Browser running, return to the Home screen, and close it '
          'from its own tile',
    body=_body,
    requires=(
        require.tile(TILE_ID),
        require.manual('the File Browser the tile launches is current — it is the one '
                       'that has to publish the test API, so an installed copy under '
                       '/usr/share must be refreshed from apps/ first'),
    ),
)
