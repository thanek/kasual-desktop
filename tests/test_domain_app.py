"""Tests for the App domain value object and its freedesktop-entry factory."""

import pytest

from domain.catalog.app import App, ORDER_DEFAULT, _parse_env, _parse_exec


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
        assert app.categories == ()
        assert app.is_game is False

    def test_is_immutable(self):
        import dataclasses
        app = App(name="X", command="x")
        try:
            app.name = "Y"  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            return
        raise AssertionError("App should be frozen")


# ── Exec parsing (freedesktop Exec field codes) ──────────────────────────────

class TestExecParsing:
    def test_command_and_args(self):
        assert _parse_exec("steam steam://open/bigpicture") == (
            "steam", ["steam://open/bigpicture"]
        )

    def test_field_codes_stripped(self):
        assert _parse_exec("firefox --kiosk %U") == ("firefox", ["--kiosk"])

    def test_quoted_args(self):
        assert _parse_exec('app "a b" c') == ("app", ["a b", "c"])

    def test_escaped_percent(self):
        assert _parse_exec("app 50%%") == ("app", ["50%"])

    def test_empty(self):
        assert _parse_exec("   ") == (None, [])


# ── Env parsing (X-Kasual-Env extension) ─────────────────────────────────────

class TestEnvParsing:
    def test_basic(self):
        assert _parse_env("A=1;B=2") == {"A": "1", "B": "2"}

    def test_none_and_empty(self):
        assert _parse_env(None) == {}
        assert _parse_env("") == {}

    def test_ignores_malformed(self):
        assert _parse_env("A=1;garbage;B=2") == {"A": "1", "B": "2"}

    def test_value_keeps_equals(self):
        assert _parse_env("URL=http://x?a=b") == {"URL": "http://x?a=b"}


# ── from_desktop_entry (the freedesktop → App mapping rules) ─────────────────

class TestFromDesktopEntry:
    def test_maps_all_fields(self):
        order, app = App.from_desktop_entry({
            "Type": "Application",
            "Name": "Steam",
            "Exec": "steam steam://open/bigpicture",
            "X-Kasual-Icon": "fa5b.steam",
            "X-Kasual-Color": "#1b2838",
            "X-Kasual-RecallMenuTrigger": "BTN_MODE_HOLD_1S",
            "X-Kasual-HideGraceMs": "500",
            "X-Kasual-Env": "MANGOHUD=1",
            "X-Kasual-Order": "10",
            "Categories": "Game;ActionGame;",
        })
        assert order == 10
        assert app.name == "Steam"
        assert app.command == "steam"
        assert app.args == ("steam://open/bigpicture",)
        assert app.icon == "fa5b.steam"
        assert app.color == "#1b2838"
        assert app.recall_menu_trigger == "BTN_MODE_HOLD_1S"
        assert app.launch_hide_grace_ms == 500
        assert app.env == {"MANGOHUD": "1"}
        assert app.categories == ("Game", "ActionGame")
        assert app.is_game is True

    def test_defaults_and_order_default(self):
        order, app = App.from_desktop_entry(
            {"Type": "Application", "Name": "Min", "Exec": "min"}
        )
        assert order == ORDER_DEFAULT
        assert app.icon is None
        assert app.icon_theme is None
        assert app.color == "#2e3440"
        assert app.recall_menu_trigger == "BTN_MODE_CLICK"
        assert app.launch_hide_grace_ms == 0
        assert app.env == {}
        assert app.categories == ()
        assert app.is_game is False

    def test_icon_theme_used_without_kasual_icon(self):
        _, app = App.from_desktop_entry(
            {"Type": "Application", "Name": "T", "Exec": "t", "Icon": "org.kde.themed"}
        )
        assert app.icon is None
        assert app.icon_theme == "org.kde.themed"

    def test_reads_startupwmclass(self):
        _, app = App.from_desktop_entry({
            "Type": "Application", "Name": "Konsole", "Exec": "konsole",
            "StartupWMClass": "org.kde.konsole",
        })
        assert app.wm_class == "org.kde.konsole"
        assert "org.kde.konsole" in app.window_match_keys

    @pytest.mark.parametrize("entry", [
        {"Type": "Link", "Name": "L", "URL": "http://x"},
        {"Type": "Application", "Name": "N", "Exec": "n", "NoDisplay": "true"},
        {"Type": "Application", "Name": "H", "Exec": "h", "Hidden": "true"},
    ])
    def test_non_tiles_return_none(self, entry):
        assert App.from_desktop_entry(entry) is None

    @pytest.mark.parametrize("entry", [
        {"Type": "Application", "Name": "X"},              # no Exec
        {"Type": "Application", "Exec": "x"},              # no Name
        {"Type": "Application", "Name": "X", "Exec": "%U"},  # Exec only field codes
    ])
    def test_malformed_raises(self, entry):
        with pytest.raises(ValueError):
            App.from_desktop_entry(entry)


class TestToDesktopEntry:
    """The App→freedesktop renderer — inverse of from_desktop_entry."""

    def test_always_emits_type_name_exec_order(self):
        app = App(name="Min", command="min")
        entry = app.to_desktop_entry(order=5)
        assert entry["Type"] == "Application"
        assert entry["Name"] == "Min"
        assert entry["Exec"] == "min"
        assert entry["X-Kasual-Order"] == "5"

    def test_omits_unset_optional_keys(self):
        entry = App(name="Min", command="min").to_desktop_entry(order=1)
        for key in ("Icon", "X-Kasual-Icon", "X-Kasual-Color",
                    "X-Kasual-RecallMenuTrigger", "X-Kasual-HideGraceMs",
                    "X-Kasual-Env", "Categories"):
            assert key not in entry

    def test_emits_set_keys(self):
        app = App(
            name="Steam", command="steam", args=("steam://open/bigpicture",),
            icon="fa5b.steam", icon_theme="steam", color="#1b2838",
            recall_menu_trigger="BTN_MODE_HOLD_1S", launch_hide_grace_ms=500,
            env={"MANGOHUD": "1"}, categories=("Game",),
        )
        entry = app.to_desktop_entry(order=10)
        assert entry["Icon"] == "steam"
        assert entry["X-Kasual-Icon"] == "fa5b.steam"
        assert entry["X-Kasual-Color"] == "#1b2838"
        assert entry["X-Kasual-RecallMenuTrigger"] == "BTN_MODE_HOLD_1S"
        assert entry["X-Kasual-HideGraceMs"] == "500"
        assert entry["X-Kasual-Env"] == "MANGOHUD=1"
        assert entry["Categories"] == "Game;"

    def test_emits_startupwmclass(self):
        app = App(name="Konsole", command="konsole", wm_class="org.kde.konsole")
        assert app.to_desktop_entry(order=1)["StartupWMClass"] == "org.kde.konsole"

    def test_omits_startupwmclass_when_unset(self):
        assert "StartupWMClass" not in App(name="M", command="m").to_desktop_entry(order=1)

    def test_exec_requoting_survives_round_trip(self):
        app = App(name="X", command="/opt/my app/run.sh", args=("--flag", "a b"))
        entry = app.to_desktop_entry(order=1)
        order, parsed = App.from_desktop_entry(entry)
        assert parsed.command == "/opt/my app/run.sh"
        assert parsed.args == ("--flag", "a b")

    def test_round_trip_is_stable(self):
        app = App(
            name="Steam", command="steam", args=("steam://open/bigpicture",),
            icon="fa5b.steam", color="#1b2838",
            recall_menu_trigger="BTN_MODE_HOLD_1S", launch_hide_grace_ms=500,
            env={"MANGOHUD": "1"}, categories=("Game",),
        )
        order, parsed = App.from_desktop_entry(app.to_desktop_entry(order=10))
        assert order == 10
        assert parsed == app
