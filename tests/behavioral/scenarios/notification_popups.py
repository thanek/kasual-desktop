"""Notification popups never outstay a user who holds nothing but a gamepad."""

from tests.behavioral.harness import popups as popup
from tests.behavioral.harness import requirements as require
from tests.behavioral.harness import shell
from tests.behavioral.harness.popups import (
    CRITICAL, NORMAL, HandsOff, PopupSource, SentNotifications, build_popup_source,
)
from tests.behavioral.harness.session import Scenario, Session

ORDINARY        = 'KD test: ordinary'
CRITICAL_FIRST  = 'KD test: critical'
CRITICAL_SECOND = 'KD test: critical in the queue'


def _leave_the_screen_to_ordinary_popups(session: Session) -> None:
    shell.open_home_menu(session.kd, session.pad)
    shell.pick_menu_action(session.kd, session.pad, shell.HIDE_DESKTOP)
    shell.expect_minimized(session.kd)


def _come_back(session: Session) -> None:
    shell.open_home_menu(session.kd, session.pad)
    shell.pick_menu_action(session.kd, session.pad, shell.RETURN_TO_DESKTOP)
    shell.expect_home_view_restored(session.kd)


def _an_ordinary_popup_expires(popups: PopupSource, sent: SentNotifications) -> None:
    hands_off = HandsOff(popups)
    hands_off.await_idle()
    sent.send(ORDINARY, NORMAL)
    popup.expect_popup(popups, ORDINARY)
    popup.expect_popup_expires(popups, ORDINARY)
    hands_off.expect_kept()


def _critical_popups_stay(popups: PopupSource, sent: SentNotifications) -> None:
    sent.send(CRITICAL_FIRST, CRITICAL)
    popup.expect_popup(popups, CRITICAL_FIRST)
    sent.send(CRITICAL_SECOND, CRITICAL)
    popup.expect_popup_queued(popups, CRITICAL_SECOND)
    popup.expect_popup_stays(popups, CRITICAL_FIRST)


def _body(session: Session) -> None:
    kd, pad = session.kd, session.pad
    popups, sent = build_popup_source(), SentNotifications()
    session.add_cleanup(sent.withdraw)
    session.record('popups', popups.history)

    _leave_the_screen_to_ordinary_popups(session)
    popup.expect_no_popup(popups, 'before the run')
    _an_ordinary_popup_expires(popups, sent)
    _come_back(session)
    _critical_popups_stay(popups, sent)

    shell.open_notifications(kd, pad)
    popup.expect_no_popup(popups, 'once the notifications list is open')
    for summary in (ORDINARY, CRITICAL_FIRST, CRITICAL_SECOND):
        shell.expect_listed_once(kd, summary)

    shell.leave_notifications(kd, pad)
    shell.expect_home_view_restored(kd)


SCENARIO = Scenario(
    name='notification_popups',
    title='ordinary popups expire without input, opening the notifications dismisses the rest',
    body=_body,
    requires=(
        require.popup_source(),
        require.command('notify-send'),
        require.command('gdbus'),
        require.manual('Do Not Disturb is off, and nobody touches the mouse or the '
                       'keyboard during the run'),
    ),
)
