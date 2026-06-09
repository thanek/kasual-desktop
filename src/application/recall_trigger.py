"""The BTN_MODE recall policy: how the guide button summons the Kasual menu.

Two per-app policies (see domain.input.Trigger):
  • CLICK    — recall fires immediately on press.
  • HOLD_1S  — recall fires only if the button is held HOLD_SECONDS; a shorter
               press is *not* a recall.
When Kasual itself is in control (its UI on the input-focus stack), recall is
always immediate regardless of the app's policy.

A press that did NOT recall is a "short press": it is forwarded to the
foreground app as a synthetic press+release, so e.g. Steam still sees its guide
button. `release()` reports whether such a forward is due — the caller owns the
actual (virtual-gamepad) write.

Pure decision logic (application layer): no Qt, no evdev. The menu-open is an
injected `on_recall` callback; the hold timer is an injected factory
(`threading.Timer` by default, matching the .start()/.cancel() interface) so
tests can fire or cancel it deterministically.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from domain.input import Trigger

HOLD_SECONDS = 1.0   # how long BTN_MODE must be held for the menu, in HOLD_1S mode


class RecallTrigger:
    def __init__(
        self,
        on_recall: Callable[[], None],
        *,
        hold_seconds: float = HOLD_SECONDS,
        timer_factory: Callable[[float, Callable[[], None]], object] = threading.Timer,
    ) -> None:
        self._on_recall     = on_recall
        self._hold_seconds  = hold_seconds
        self._timer_factory = timer_factory
        self._timer         = None    # pending hold timer (HOLD_1S), if armed
        self._recalled      = False   # True once recall fired for the current press

    def press(self, *, kasual_active: bool, trigger: str) -> None:
        """BTN_MODE went down. Recall now (CLICK / Kasual active) or arm the hold."""
        self._recalled = False
        if kasual_active or trigger == Trigger.CLICK:
            self._fire_recall()
        else:
            self._timer = self._timer_factory(self._hold_seconds, self._fire_recall)
            self._timer.start()

    def release(self, *, suppressed: bool) -> bool:
        """BTN_MODE went up. Cancel any pending hold; report if a short-press
        forward to the foreground app is due (the press did not recall and our
        UI is not in control)."""
        self._disarm()
        return not self._recalled and not suppressed

    def cancel(self) -> None:
        """Abandon any in-flight press (e.g. on gamepad refresh/disconnect)."""
        self._disarm()
        self._recalled = False

    def _disarm(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _fire_recall(self) -> None:
        self._recalled = True
        self._on_recall()
