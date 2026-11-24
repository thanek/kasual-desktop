"""The popups the desktop environment shows for notifications, and the steps against them."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from typing import Protocol

from tests.behavioral.harness import progress, timeouts
from tests.behavioral.harness.report import ScenarioAborted, report

NORMAL   = 'normal'
CRITICAL = 'critical'

_POLL_S = 0.2
_IDLE_ENOUGH_TO_KEEP_A_POPUP_WAITING_S = 2.0
_IDLE_CLOCK_SLACK_S = 0.5


class PopupSource(Protocol):
    history: list[dict]

    def is_available(self) -> bool: ...
    def shown(self) -> str | None: ...
    def queued(self) -> list[str]: ...
    def keyboard_and_mouse_idle_s(self) -> float: ...


def build_popup_source() -> PopupSource | None:
    from infrastructure.linux.compositor import Compositor, detect_compositor
    if detect_compositor() is not Compositor.GNOME:
        return None
    from tests.behavioral.harness.sources.gnome_popups import GnomePopupSource
    return GnomePopupSource()


class SentNotifications:
    def __init__(self) -> None:
        self._ids: list[str] = []

    def send(self, summary: str, urgency: str) -> None:
        sent = subprocess.run(
            ['notify-send', '--print-id', '--app-name=Kasual behavioral tests',
             f'--urgency={urgency}', summary, 'sent by the behavioral tests'],
            capture_output=True, text=True, check=True)
        self._ids.append(sent.stdout.strip())

    def withdraw(self) -> None:
        for sent_id in self._ids:
            subprocess.run(
                ['gdbus', 'call', '--session', '--dest', 'org.freedesktop.Notifications',
                 '--object-path', '/org/freedesktop/Notifications', '--method',
                 'org.freedesktop.Notifications.CloseNotification', sent_id],
                capture_output=True)


def _wait_until(condition: Callable[[], bool], timeout_s: float, description: str) -> bool:
    deadline = time.monotonic() + timeout_s
    with progress.waiting(description, timeout_s) as bar:
        while not condition():
            if time.monotonic() >= deadline:
                return False
            bar.tick()
            time.sleep(_POLL_S)
    return True


def expect_no_popup(popups: PopupSource, when: str) -> None:
    def nothing_shown_or_queued() -> bool:
        return popups.shown() is None and not popups.queued()

    what = f'no popup on screen or waiting {when}'
    if _wait_until(nothing_shown_or_queued, timeouts.POPUP, what):
        report(what, 'PASS')
        return
    report(what, 'FAIL', f'shown: {popups.shown()!r}, queued: {popups.queued()}')
    raise ScenarioAborted('popups are in the way')


def expect_popup(popups: PopupSource, summary: str) -> None:
    if _wait_until(lambda: popups.shown() == summary, timeouts.POPUP, f'{summary!r} popping up'):
        report(f'{summary!r} popped up', 'PASS')
        return
    report(f'{summary!r} popped up', 'FAIL',
           f'shown: {popups.shown()!r}, queued: {popups.queued()} — is Do Not Disturb on?')
    raise ScenarioAborted(f'{summary!r} never popped up')


def expect_popup_queued(popups: PopupSource, summary: str) -> None:
    queued = _wait_until(lambda: summary in popups.queued(), timeouts.POPUP, f'{summary!r} queued')
    report(f'{summary!r} waits its turn', 'PASS' if queued else 'FAIL',
           '' if queued else f'queued: {popups.queued()}')


def expect_popup_expires(popups: PopupSource, summary: str) -> None:
    what = f'{summary!r} left on its own'
    started = time.monotonic()
    if not _wait_until(lambda: popups.shown() != summary, timeouts.POPUP_EXPIRES,
                       f'{summary!r} to leave on its own'):
        report(what, 'FAIL', f'still on screen after {timeouts.POPUP_EXPIRES:.0f}s')
        return
    report(what, 'PASS', f'after {time.monotonic() - started:.1f}s')


def expect_popup_stays(popups: PopupSource, summary: str) -> None:
    what = f'{summary!r} stayed on screen'
    started = time.monotonic()
    if _wait_until(lambda: popups.shown() != summary, timeouts.POPUP_STAYS,
                   f'{summary!r} staying on screen'):
        report(what, 'FAIL', f'gone after {time.monotonic() - started:.1f}s')
        return
    report(what, 'PASS', f'for {timeouts.POPUP_STAYS:.0f}s')


class HandsOff:
    def __init__(self, popups: PopupSource) -> None:
        self._popups = popups
        self._since = 0.0

    def await_idle(self) -> None:
        what = 'the mouse and the keyboard are left alone'
        if not _wait_until(self._idle_enough, timeouts.HANDS_OFF, f'{what} — hands off, please'):
            report(what, 'FAIL', 'they are in use — let go of them and run again')
            raise ScenarioAborted(what)
        self._since = time.monotonic()
        report(what, 'PASS')

    def expect_kept(self) -> None:
        what = 'no input reached the desktop meanwhile'
        untouched_for = time.monotonic() - self._since
        if self._popups.keyboard_and_mouse_idle_s() + _IDLE_CLOCK_SLACK_S >= untouched_for:
            report(what, 'PASS', f'{untouched_for:.1f}s')
            return
        report(what, 'FAIL', 'the mouse or the keyboard was used — run again, hands off')
        raise ScenarioAborted('input hides popups by itself, so this run proves nothing')

    def _idle_enough(self) -> bool:
        return (self._popups.keyboard_and_mouse_idle_s()
                >= _IDLE_ENOUGH_TO_KEEP_A_POPUP_WAITING_S)
