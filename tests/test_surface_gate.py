"""Tests for the startup gate on the surface protocol.

Wayland places no client's top-level windows for it, so without layer-shell the
Desktop, the Home header and the hint bar land wherever the compositor puts them.
The gate exists so that arrives as an explanation rather than as a scattered UI.
"""

from domain.preflight.surface_gate import SurfaceGate


class FakeView:
    def __init__(self) -> None:
        self.blocked = 0
        self.on_continue = None
        self.on_quit = None

    def show_missing_layer_shell(self, on_continue, on_quit) -> None:
        self.blocked += 1
        self.on_continue = on_continue
        self.on_quit = on_quit


def _gate(available: bool):
    view, started, quit_calls = FakeView(), [], []
    gate = SurfaceGate(lambda: available, view, on_quit=lambda: quit_calls.append(1))
    return gate, view, started, quit_calls


class TestSurfaceGate:
    def test_starts_straight_away_when_layer_shell_is_there(self):
        gate, view, started, _ = _gate(True)
        gate.ensure(lambda: started.append(1))
        assert started == [1]
        assert view.blocked == 0

    def test_blocks_instead_of_starting_when_it_is_not(self):
        gate, view, started, _ = _gate(False)
        gate.ensure(lambda: started.append(1))
        assert started == []
        assert view.blocked == 1

    def test_continuing_starts_the_session_anyway(self):
        gate, view, started, _ = _gate(False)
        gate.ensure(lambda: started.append(1))
        view.on_continue()
        assert started == [1]

    def test_quitting_does_not_start_the_session(self):
        gate, view, started, quit_calls = _gate(False)
        gate.ensure(lambda: started.append(1))
        view.on_quit()
        assert quit_calls == [1]
        assert started == []

    def test_the_probe_is_asked_each_time(self):
        asked, view = [], FakeView()
        gate = SurfaceGate(lambda: asked.append(1) or False, view, on_quit=lambda: None)
        gate.ensure(lambda: None)
        gate.ensure(lambda: None)
        assert len(asked) == 2
