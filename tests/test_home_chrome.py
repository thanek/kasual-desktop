"""Tests for HomeChrome — Home surface / hint bar visibility decisions, the
in-place BTN_MODE toggle, and the header's live status (pure domain)."""

from domain.navigation import hints as nav_hints
from domain.network.status import NetworkKind, NetworkStatus
from domain.notifications.center import NotificationCenter
from datetime import datetime

from domain.notifications.notification import Notification
from domain.shell.home_chrome import HomeChrome


class FakeHomeSurface:
    def __init__(self, expanded=False, on_demand=False):
        self.expanded = expanded
        self.on_demand = on_demand
        self.calls = []

    def is_expanded(self):
        return self.expanded

    def is_open(self):
        return self.expanded or self.on_demand

    def is_showing(self):
        return self.on_demand

    def expand(self):
        self.expanded = True
        self.calls.append("expand")

    def request_close(self):
        self.calls.append("request_close")

    def collapse_immediately(self):
        self.expanded = False
        self.on_demand = False
        self.calls.append("collapse_immediately")

    def show_collapsed(self):
        self.calls.append("show_collapsed")

    def hide(self):
        self.calls.append("hide")


class FakeHintBar:
    def __init__(self):
        self.hints = []
        self.calls = []

    def show_hints(self, hints):
        self.hints.append(hints)

    def show_at_bottom(self):
        self.calls.append("show_at_bottom")

    def hide(self):
        self.calls.append("hide")


class FakeHeader:
    def __init__(self):
        self.power_icons = []
        self.network_icons = []
        self.badges = []

    def set_power_icon(self, icon):
        self.power_icons.append(icon)

    def set_network_icon(self, glyph):
        self.network_icons.append(glyph)

    def set_notification_badge(self, count):
        self.badges.append(count)


class FakePowerPreference:
    def __init__(self, default="sleep"):
        self._default = default

    def default(self):
        return self._default


def _chrome(
    *,
    visible=True,
    surface=None,
    hintbar=None,
    header=None,
    notifications=None,
    power_preference=None,
):
    calls = []
    chrome = HomeChrome(
        is_desktop_visible=lambda: visible,
        home_surface=surface,
        hintbar=hintbar or FakeHintBar(),
        header=header or FakeHeader(),
        notifications=notifications or NotificationCenter(),
        render_screen_hints=lambda: calls.append("render"),
        dismiss_overlays=lambda: calls.append("dismiss"),
        show_notifications_view=lambda: calls.append("show_view"),
        power_preference=power_preference,
    )
    return chrome, calls


class TestSurfaceVisibilitySync:
    def test_desktop_up_shows_surface_collapsed(self):
        surface = FakeHomeSurface()
        chrome, _ = _chrome(visible=True, surface=surface)
        chrome.sync()
        assert surface.calls == ["show_collapsed"]

    def test_desktop_up_reclaims_on_demand_overlay_as_collapsed(self):
        surface = FakeHomeSurface(on_demand=True)
        chrome, _ = _chrome(visible=True, surface=surface)
        chrome.sync()
        assert surface.calls == ["collapse_immediately", "show_collapsed"]

    def test_desktop_down_hides_collapsed_surface(self):
        surface = FakeHomeSurface()
        chrome, _ = _chrome(visible=False, surface=surface)
        chrome.sync()
        assert surface.calls == ["collapse_immediately", "hide"]

    def test_desktop_down_leaves_on_demand_overlay_mapped(self):
        surface = FakeHomeSurface(on_demand=True)
        chrome, _ = _chrome(visible=False, surface=surface)
        chrome.sync()
        assert surface.calls == []

    def test_no_surface_is_fine(self):
        chrome, _ = _chrome(visible=True, surface=None)
        chrome.sync()   # must not raise

    def test_activation_lands_on_bare_chrome(self):
        surface = FakeHomeSurface(expanded=True)
        chrome, _ = _chrome(visible=True, surface=surface)
        chrome.on_desktop_activated()
        assert surface.calls[0] == "collapse_immediately"
        assert not surface.expanded


class TestHintBarVisibility:
    def test_bar_shows_while_desktop_visible(self):
        bar = FakeHintBar()
        chrome, _ = _chrome(visible=True, hintbar=bar)
        chrome.sync()
        assert bar.calls == ["show_at_bottom"]

    def test_bar_hides_when_desktop_down(self):
        bar = FakeHintBar()
        chrome, _ = _chrome(visible=False, hintbar=bar)
        chrome.sync()
        assert bar.calls == ["hide"]

    def test_overlay_ownership_keeps_bar_up_over_an_app(self):
        bar = FakeHintBar()
        chrome, _ = _chrome(visible=False, hintbar=bar)
        chrome.begin_overlay_hints()
        assert bar.hints == [nav_hints.OVERLAY_MENU]
        assert bar.calls == ["show_at_bottom"]

    def test_overlay_end_releases_bar_when_desktop_down(self):
        bar = FakeHintBar()
        chrome, calls = _chrome(visible=False, hintbar=bar)
        chrome.begin_overlay_hints()
        chrome.end_overlay_hints()
        assert bar.calls == ["show_at_bottom", "hide"]
        assert "render" not in calls

    def test_overlay_end_restores_screen_hints_when_desktop_up(self):
        chrome, calls = _chrome(visible=True)
        chrome.begin_overlay_hints()
        chrome.end_overlay_hints()
        assert "render" in calls

    def test_hint_swap_only_while_overlay_owns_the_bar(self):
        bar = FakeHintBar()
        chrome, _ = _chrome(visible=True, hintbar=bar)
        chrome.set_overlay_hints("zone-hints")
        assert bar.hints == []
        chrome.begin_overlay_hints()
        chrome.set_overlay_hints("zone-hints")
        assert bar.hints[-1] == "zone-hints"


class TestTryToggle:
    def test_unhandled_without_surface(self):
        chrome, _ = _chrome(visible=True, surface=None)
        assert chrome.try_toggle() is False

    def test_unhandled_when_desktop_down(self):
        chrome, _ = _chrome(visible=False, surface=FakeHomeSurface())
        assert chrome.try_toggle() is False

    def test_expands_and_supersedes_open_overlays(self):
        surface = FakeHomeSurface()
        chrome, calls = _chrome(visible=True, surface=surface)
        assert chrome.try_toggle() is True
        assert calls == ["dismiss"]
        assert surface.calls == ["expand"]

    def test_closes_an_expanded_menu(self):
        surface = FakeHomeSurface(expanded=True)
        chrome, calls = _chrome(visible=True, surface=surface)
        assert chrome.try_toggle() is True
        assert surface.calls == ["request_close"]
        assert calls == []


class TestHeaderStatus:
    def test_power_glyph_follows_persisted_default(self):
        header = FakeHeader()
        chrome, _ = _chrome(header=header, power_preference=FakePowerPreference("sleep"))
        chrome.refresh_power_default()
        from domain.system.actions import ACTIONS
        assert header.power_icons == [ACTIONS["sleep"].icon]

    def test_power_glyph_skipped_without_preference(self):
        header = FakeHeader()
        chrome, _ = _chrome(header=header, power_preference=None)
        chrome.refresh_power_default()
        assert header.power_icons == []

    def test_network_status_is_stored_and_reflected(self):
        header = FakeHeader()
        chrome, _ = _chrome(header=header)
        status = NetworkStatus(kind=NetworkKind.OFFLINE)
        chrome.update_network_status(status)
        assert chrome.network_status is status
        assert len(header.network_icons) == 1

    def test_offline_icon_remembers_the_last_link(self):
        header = FakeHeader()
        chrome, _ = _chrome(header=header)
        chrome.update_network_status(NetworkStatus(kind=NetworkKind.ETHERNET))
        chrome.update_network_status(NetworkStatus.offline())
        assert header.network_icons[-1] == "mdi.lan-disconnect"
        assert chrome.network_icon == "mdi.lan-disconnect"

    def test_offline_icon_is_generic_before_any_link(self):
        header = FakeHeader()
        chrome, _ = _chrome(header=header)
        chrome.update_network_status(NetworkStatus.offline())
        assert header.network_icons == ["mdi6.web-off"]

    def test_badge_mirrors_unread_count(self):
        header = FakeHeader()
        center = NotificationCenter()
        center.record(Notification(app_name="a", summary="s", timestamp=datetime.now()))
        chrome, _ = _chrome(header=header, notifications=center)
        chrome.refresh_notification_badge()
        assert header.badges == [1]


class TestOpenNotifications:
    def test_view_sees_the_unread_tally_before_it_clears(self):
        center = NotificationCenter()
        center.record(Notification(app_name="a", summary="s", timestamp=datetime.now()))
        header = FakeHeader()
        seen = []
        chrome, _ = _chrome(header=header, notifications=center)
        chrome._show_notifications_view = lambda: seen.append(center.unread_count)
        chrome.open_notifications()
        assert seen == [1]
        assert center.unread_count == 0
        assert header.badges == [0]
