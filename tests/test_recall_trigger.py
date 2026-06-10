"""Tests for RecallTrigger — the BTN_MODE CLICK/HOLD recall state machine.

Characterizes behaviour that previously lived inline (and untested) inside
GamepadWatcher._loop. The hold timer is a fake so we can fire/cancel it
deterministically; the menu-open is a recording callback.
"""

from domain.input.recall import RecallTrigger
from domain.input.vocabulary import Trigger


class FakeTimer:
    """Stand-in for threading.Timer — records start/cancel, fires on demand."""

    def __init__(self, seconds, callback):
        self.seconds   = seconds
        self.callback  = callback
        self.started   = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.callback()


def _make(hold_seconds=1.0):
    recalls = []
    timers  = []

    def factory(seconds, callback):
        t = FakeTimer(seconds, callback)
        timers.append(t)
        return t

    trig = RecallTrigger(
        on_recall=lambda: recalls.append(True),
        hold_seconds=hold_seconds,
        timer_factory=factory,
    )
    return trig, recalls, timers


# ── CLICK policy ────────────────────────────────────────────────────────────

class TestClick:
    def test_press_recalls_immediately(self):
        trig, recalls, timers = _make()
        trig.press(kasual_active=False, trigger=Trigger.CLICK)
        assert recalls == [True]
        assert timers == []          # no hold timer armed

    def test_release_after_click_does_not_forward(self):
        trig, _, _ = _make()
        trig.press(kasual_active=False, trigger=Trigger.CLICK)
        assert trig.release(suppressed=False) is False


# ── Kasual active overrides the policy ───────────────────────────────────────

class TestKasualActive:
    def test_hold_policy_recalls_immediately_when_kasual_active(self):
        trig, recalls, timers = _make()
        trig.press(kasual_active=True, trigger=Trigger.HOLD_1S)
        assert recalls == [True]
        assert timers == []


# ── HOLD_1S policy ───────────────────────────────────────────────────────────

class TestHold:
    def test_press_arms_timer_does_not_recall_yet(self):
        trig, recalls, timers = _make(hold_seconds=1.0)
        trig.press(kasual_active=False, trigger=Trigger.HOLD_1S)
        assert recalls == []
        assert len(timers) == 1
        assert timers[0].started is True
        assert timers[0].seconds == 1.0

    def test_held_past_threshold_recalls(self):
        trig, recalls, timers = _make()
        trig.press(kasual_active=False, trigger=Trigger.HOLD_1S)
        timers[0].fire()             # hold threshold elapsed
        assert recalls == [True]

    def test_short_release_cancels_timer_and_forwards(self):
        trig, recalls, timers = _make()
        trig.press(kasual_active=False, trigger=Trigger.HOLD_1S)
        forward = trig.release(suppressed=False)
        assert recalls == []         # never recalled
        assert timers[0].cancelled is True
        assert forward is True       # short press → forward to foreground app

    def test_release_after_hold_fired_does_not_forward(self):
        trig, recalls, timers = _make()
        trig.press(kasual_active=False, trigger=Trigger.HOLD_1S)
        timers[0].fire()
        assert trig.release(suppressed=False) is False


# ── Suppression (our UI in control) blocks the forward ───────────────────────

class TestSuppressed:
    def test_short_release_while_suppressed_does_not_forward(self):
        trig, _, timers = _make()
        trig.press(kasual_active=False, trigger=Trigger.HOLD_1S)
        assert trig.release(suppressed=True) is False
        assert timers[0].cancelled is True


# ── cancel() — refresh / disconnect ──────────────────────────────────────────

class TestCancel:
    def test_cancel_disarms_pending_timer(self):
        trig, recalls, timers = _make()
        trig.press(kasual_active=False, trigger=Trigger.HOLD_1S)
        trig.cancel()
        assert timers[0].cancelled is True

    def test_after_cancel_next_short_release_forwards(self):
        trig, _, timers = _make()
        trig.press(kasual_active=False, trigger=Trigger.HOLD_1S)
        trig.cancel()
        # a fresh press/release cycle behaves normally
        trig.press(kasual_active=False, trigger=Trigger.HOLD_1S)
        assert trig.release(suppressed=False) is True
