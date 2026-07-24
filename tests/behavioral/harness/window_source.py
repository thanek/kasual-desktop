"""Every window the run does not own — the splash, the launcher, the game — and the
one place the harness has to know which compositor it is on.

A source promises a *set* of windows, `{id, title, app_id, pid, focused, fullscreen,
covers_screen}`, and not their z-order: Hyprland and Sway do not expose one, and no
assertion needs it — "who covers whom" is answered from KD's own state (`kd_client`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from PyQt6.QtCore import QCoreApplication, QEventLoop

from tests.behavioral.harness import progress
from tests.behavioral.harness.report import report


class WindowSource(Protocol):
    """Window events as the compositor announces them."""

    events: list[dict]

    def start(self, timeout_s: float) -> None:
        """Subscribe, and block until the first snapshot arrives."""

    def stop(self) -> None: ...

    def wait_for(self, predicate: Callable[[dict], bool], timeout_s: float,
                 description: str) -> dict: ...

    def last_stack(self) -> list[dict]: ...


class EventLog:
    """The waiting machinery every adapter shares. An event is
    `{reason, window, stack, received_at}`; each adapter only has to append them."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._cursor = 0

    def append(self, reason: str, window: str, stack: list[dict]) -> None:
        self.events.append({'reason': reason, 'window': window, 'stack': stack,
                            'received_at': time.time()})

    def wait_for(self, predicate: Callable[[dict], bool], timeout_s: float,
                 description: str) -> dict:
        """Return the first event *after the previous match* that satisfies
        *predicate*, so a chain of waits asserts the order events arrived in, not
        merely that they did."""
        deadline = time.monotonic() + timeout_s
        with progress.waiting(description, timeout_s) as bar:
            while True:
                while self._cursor < len(self.events):
                    event = self.events[self._cursor]
                    self._cursor += 1
                    if predicate(event):
                        return event
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f'timed out after {timeout_s}s waiting for: {description}')
                bar.tick()
                QCoreApplication.processEvents(
                    QEventLoop.ProcessEventsFlag.WaitForMoreEvents,
                    int(min(remaining, 0.2) * 1000),
                )

    def last_stack(self) -> list[dict]:
        return self.events[-1]['stack'] if self.events else []


class NullWindowSource(EventLog):
    """No backend for this compositor. Scenarios that read windows declare
    `require.window_source()` and never get here; the rest run anywhere."""

    def start(self, timeout_s: float) -> None:
        self.append('init', '', [])

    def stop(self) -> None:
        pass


def find(stack: list[dict], app_id: str | None = None,
         fullscreen: bool | None = None) -> list[dict]:
    out = stack
    if app_id is not None:
        out = [w for w in out if w['app_id'] == app_id]
    if fullscreen is not None:
        # A window that fills the screen without asking for the state is fullscreen to
        # the person looking at it.
        out = [w for w in out if (w['fullscreen'] or w['covers_screen']) == fullscreen]
    return out


_BACKENDS = {'kde': 'kwin', 'gnome': 'gnome', 'hyprland': 'hyprland', 'sway': 'sway',
             'cosmic': 'cosmic'}


def backend() -> str | None:
    """Which adapter this compositor gets — asked without building it, because
    building one claims a D-Bus name, and a discarded instance would keep it."""
    from infrastructure.linux.compositor import detect_compositor

    return _BACKENDS.get(detect_compositor().value)


def build_window_source() -> WindowSource:
    name = backend()
    if name == 'kwin':
        from tests.behavioral.harness.sources.kwin import KWinWindowSource
        return KWinWindowSource()
    if name == 'gnome':
        from tests.behavioral.harness.sources.gnome import GnomeWindowSource
        return GnomeWindowSource()
    if name == 'hyprland':
        from tests.behavioral.harness.sources.hyprland import HyprlandWindowSource
        return HyprlandWindowSource()
    if name == 'sway':
        from tests.behavioral.harness.sources.sway import SwayWindowSource
        return SwayWindowSource()
    if name == 'cosmic':
        from tests.behavioral.harness.sources.cosmic import CosmicWindowSource
        return CosmicWindowSource()
    report('window source', 'INFO',
           'no window backend for this compositor — a scenario that reads windows '
           'will not run here (see tests/behavioral/PORTING.md)')
    return NullWindowSource()
