"""Tests for the OpenOverlays registry — the on-screen overlay group.

Pure domain: drives fake overlays, so it needs no Qt. Characterizes that the
group pauses/resumes/cancels every registered member and never names a concrete
overlay kind (so a new one is covered just by registering).
"""

from domain.shell.open_overlays import OpenOverlays


class FakeOverlay:
    def __init__(self):
        self.paused = 0
        self.resumed = 0
        self.cancelled = 0

    def pause(self):
        self.paused += 1

    def resume(self):
        self.resumed += 1

    def cancel(self):
        self.cancelled += 1


class TestGroupActions:
    def test_pause_resume_reach_every_member(self):
        overlays = OpenOverlays()
        a, b = FakeOverlay(), FakeOverlay()
        overlays.register(a)
        overlays.register(b)

        overlays.pause()
        overlays.resume()

        assert (a.paused, a.resumed) == (1, 1)
        assert (b.paused, b.resumed) == (1, 1)

    def test_cancel_tears_down_and_empties_the_group(self):
        overlays = OpenOverlays()
        a, b = FakeOverlay(), FakeOverlay()
        overlays.register(a)
        overlays.register(b)

        overlays.cancel()

        assert a.cancelled == 1 and b.cancelled == 1
        # The group is now empty: a second cancel is a no-op.
        overlays.cancel()
        assert a.cancelled == 1 and b.cancelled == 1


class TestMembership:
    def test_forgotten_overlay_is_left_alone(self):
        overlays = OpenOverlays()
        a = FakeOverlay()
        overlays.register(a)
        overlays.forget(a)

        overlays.pause()
        overlays.cancel()

        assert a.paused == 0 and a.cancelled == 0

    def test_forget_unknown_overlay_is_harmless(self):
        overlays = OpenOverlays()
        overlays.forget(FakeOverlay())   # not registered — must not raise

    def test_cancel_tolerates_a_member_forgetting_itself(self):
        # An overlay whose cancel() deregisters itself (as the Qt closed signal
        # does) must not trip up the iteration.
        overlays = OpenOverlays()

        class SelfForgetting(FakeOverlay):
            def cancel(self):
                super().cancel()
                overlays.forget(self)

        a, b = SelfForgetting(), SelfForgetting()
        overlays.register(a)
        overlays.register(b)

        overlays.cancel()

        assert a.cancelled == 1 and b.cancelled == 1
