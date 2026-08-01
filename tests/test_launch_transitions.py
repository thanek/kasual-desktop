"""The launch hand-off assembly: platform factories when given, null objects otherwise."""

from unittest.mock import MagicMock

from domain.lifecycle.launch_transitions import LaunchTransitions


def _callbacks():
    return dict(on_cede=MagicMock(), on_hide=MagicMock(),
                on_show=MagicMock(), on_sink=MagicMock())


class TestFallbacks:
    def test_hide_cedes_immediately(self):
        cb = _callbacks()
        LaunchTransitions.build(MagicMock(), MagicMock(), **cb).hide.arm(MagicMock())
        cb["on_cede"].assert_called_once()
        cb["on_hide"].assert_not_called()

    def test_show_and_cede_depth_are_inert(self):
        transitions = LaunchTransitions.build(MagicMock(), MagicMock(), **_callbacks())
        transitions.show.arm(MagicMock())
        transitions.cede_depth.arm(MagicMock())
        assert transitions.show.is_armed is False
        assert transitions.show.has_seen_window is False
        assert transitions.cede_depth.is_armed is False


class TestInjectedFactories:
    def test_hide_factory_gets_both_screen_callbacks(self):
        cb = _callbacks()
        wm, pm, hide_factory = MagicMock(), MagicMock(), MagicMock()
        transitions = LaunchTransitions.build(wm, pm, **cb, hide_factory=hide_factory)
        hide_factory.assert_called_once_with(wm, pm, cb["on_cede"], cb["on_hide"])
        assert transitions.hide is hide_factory.return_value

    def test_show_and_cede_depth_factories_are_used(self):
        cb = _callbacks()
        wm, pm = MagicMock(), MagicMock()
        show_factory, cede_factory = MagicMock(), MagicMock()
        transitions = LaunchTransitions.build(
            wm, pm, **cb, show_factory=show_factory, cede_depth_factory=cede_factory)
        show_factory.assert_called_once_with(wm, pm, cb["on_show"])
        cede_factory.assert_called_once_with(wm, pm, cb["on_sink"])
        assert transitions.show is show_factory.return_value
        assert transitions.cede_depth is cede_factory.return_value
