"""Tests for the App domain value object."""

from domain.app import App


class TestCommandBasename:
    def test_strips_path_and_lowercases(self):
        app = App(name="Steam", command="/usr/bin/Steam")
        assert app.command_basename == "steam"

    def test_bare_command(self):
        app = App(name="Firefox", command="firefox")
        assert app.command_basename == "firefox"


class TestDefaults:
    def test_optional_fields_have_defaults(self):
        app = App(name="X", command="x")
        assert app.args == ()
        assert app.icon is None
        assert app.icon_theme is None
        assert app.color == "#2e3440"
        assert app.recall_menu_trigger == "BTN_MODE_CLICK"
        assert app.launch_hide_grace_ms == 0
        assert app.env == {}

    def test_is_immutable(self):
        import dataclasses
        app = App(name="X", command="x")
        try:
            app.name = "Y"  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            return
        raise AssertionError("App should be frozen")
