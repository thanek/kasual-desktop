"""Home menu → Minimize → the bare desktop → BTN_MODE → Return to Home screen.

The one path out of Kasual Desktop and back that uses no application at all, and the
one where being wrong is invisible from inside KD: a Desktop that believes it is
minimized while its chrome still floats over the DE looks perfectly fine to itself.
So the assertions are about *absence* — no tiles, no wallpaper, no header, no hint
bar, no menu — and then about all of it coming back.

BTN_MODE is what recalls the menu from a minimized KD; it is the only way back in.
"""

from tests.behavioral.harness import shell
from tests.behavioral.harness.session import Scenario, Session

CARDS = (shell.GAMEPAD_ACCESS, shell.HIDE_DESKTOP, shell.RETURN_TO_DESKTOP)


def _body(session: Session) -> None:
    kd, pad = session.kd, session.pad

    shell.open_home_menu(kd, pad)
    shell.expect_menu_offers(kd, CARDS, focused=shell.RETURN_TO_DESKTOP)
    shell.pick_menu_action(kd, pad, shell.HIDE_DESKTOP)
    shell.expect_minimized(kd)

    shell.open_home_menu(kd, pad)
    # Minimized, the menu pre-focuses Minimize instead — so the way back is a
    # deliberate move, and the run has to make it.
    shell.expect_menu_offers(kd, CARDS, focused=shell.HIDE_DESKTOP)
    shell.pick_menu_action(kd, pad, shell.RETURN_TO_DESKTOP)
    shell.expect_home_view_restored(kd)


SCENARIO = Scenario(
    name='minimize',
    title='minimize from the Home menu, and come back through it',
    body=_body,
)
