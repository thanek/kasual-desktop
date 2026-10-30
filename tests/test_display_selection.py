"""Tests for choosing the screen Kasual Desktop runs on."""

from domain.display.display import SYSTEM_DECIDES, Display
from domain.display.relaunch import AnnouncedRelaunch
from domain.display.selection import DisplaySelection


class FakePreference:
    def __init__(self, preferred=None):
        self.stored = preferred

    def preferred(self):
        return self.stored

    def set_preferred(self, display_id):
        self.stored = display_id


class FakeDisplays:
    def __init__(self, *ids):
        self.ids = list(ids)

    def connected(self):
        return [Display(display_id, f"Monitor {display_id}") for display_id in self.ids]


class FakePlacement:
    def __init__(self, live=True):
        self.live = live
        self.aimed = []
        self.moved = []

    def aim_at(self, display_id):
        self.aimed.append(display_id)

    def move_to(self, display_id):
        self.moved.append(display_id)

    def moves_live(self):
        return self.live


def settled(preferred=None, connected=("DP-1", "HDMI-A-1"), live=True):
    preference = FakePreference(preferred)
    displays = FakeDisplays(*connected)
    placement = FakePlacement(live)
    selection = DisplaySelection(preference, displays, placement)
    selection.settle()
    return selection, preference, displays, placement


class TestStartup:
    def test_the_system_decides_until_the_user_picks(self):
        _selection, _preference, _displays, placement = settled()
        assert placement.aimed == [SYSTEM_DECIDES]

    def test_surfaces_open_on_the_chosen_screen(self):
        _selection, _preference, _displays, placement = settled(preferred="HDMI-A-1")
        assert placement.aimed == ["HDMI-A-1"]

    def test_an_absent_chosen_screen_falls_back_to_the_system(self):
        _selection, _preference, _displays, placement = settled(preferred="DP-3")
        assert placement.aimed == [SYSTEM_DECIDES]

    def test_falling_back_keeps_the_choice(self):
        _selection, preference, _displays, _placement = settled(preferred="DP-3")
        assert preference.stored == "DP-3"


class TestOptions:
    def test_lists_the_connected_screens(self):
        selection, *_ = settled()
        assert [display.id for display in selection.options()] == ["DP-1", "HDMI-A-1"]

    def test_lists_a_remembered_absent_screen_as_not_connected(self):
        selection, *_ = settled(preferred="DP-3")
        absent = selection.options()[-1]
        assert (absent.id, absent.connected) == ("DP-3", False)

    def test_reports_the_choice_even_while_its_screen_is_absent(self):
        selection, *_ = settled(preferred="DP-3")
        assert selection.chosen() == "DP-3"


class TestChoosing:
    def test_remembers_the_choice(self):
        selection, preference, _displays, _placement = settled()
        selection.choose("HDMI-A-1")
        assert preference.stored == "HDMI-A-1"

    def test_moves_the_shown_surfaces(self):
        selection, _preference, _displays, placement = settled()
        selection.choose("HDMI-A-1")
        assert placement.moved == ["HDMI-A-1"]

    def test_going_back_to_the_system_moves_too(self):
        selection, preference, _displays, placement = settled(preferred="HDMI-A-1")
        selection.choose(SYSTEM_DECIDES)
        assert (preference.stored, placement.moved) == (None, [SYSTEM_DECIDES])

    def test_choosing_where_it_already_is_moves_nothing(self):
        selection, _preference, _displays, placement = settled(preferred="DP-1")
        selection.choose("DP-1")
        assert placement.moved == []

    def test_leaving_an_absent_choice_for_the_system_moves_nothing(self):
        selection, preference, _displays, placement = settled(preferred="DP-3")
        selection.choose(SYSTEM_DECIDES)
        assert (preference.stored, placement.moved) == (None, [])

    def test_a_desktop_that_cannot_move_live_is_still_asked_to_move(self):
        selection, _preference, _displays, placement = settled(live=False)
        selection.choose("HDMI-A-1")
        assert placement.moved == ["HDMI-A-1"]


class TestScreenChanges:
    def test_the_chosen_screen_coming_back_takes_the_surfaces(self):
        selection, _preference, displays, placement = settled(
            preferred="DP-3", connected=("DP-1",))
        displays.ids.append("DP-3")
        selection.follow_screen_changes()
        assert placement.moved == ["DP-3"]

    def test_the_chosen_screen_leaving_hands_them_to_the_system(self):
        selection, _preference, displays, placement = settled(preferred="HDMI-A-1")
        displays.ids.remove("HDMI-A-1")
        selection.follow_screen_changes()
        assert placement.moved == [SYSTEM_DECIDES]

    def test_an_unrelated_change_moves_nothing(self):
        selection, _preference, displays, placement = settled(preferred="DP-1")
        displays.ids.append("DP-2")
        selection.follow_screen_changes()
        assert placement.moved == []

    def test_a_desktop_that_cannot_move_live_waits_for_the_next_start(self):
        selection, _preference, displays, placement = settled(
            preferred="DP-3", connected=("DP-1",), live=False)
        displays.ids.append("DP-3")
        selection.follow_screen_changes()
        assert placement.moved == []


class FakeNotifier:
    def __init__(self):
        self.shown = []

    def notify(self, summary, body=""):
        self.shown.append((summary, body))


class ManualScheduler:
    def __init__(self):
        self.pending = []

    def call_later(self, delay_ms, callback):
        self.pending.append((delay_ms, callback))

    def run_pending(self):
        for _delay, callback in self.pending:
            callback()
        self.pending = []


class FakeRestart:
    def __init__(self):
        self.restarts = 0

    def restart(self):
        self.restarts += 1


class TestAnnouncedRelaunch:
    def build(self):
        notifier, scheduler, restart = FakeNotifier(), ManualScheduler(), FakeRestart()
        return AnnouncedRelaunch(notifier, scheduler, restart), notifier, scheduler, restart

    def test_tells_the_user_before_restarting(self):
        relaunch, notifier, _scheduler, restart = self.build()
        relaunch.relaunch_onto_another_screen()
        assert (len(notifier.shown), restart.restarts) == (1, 0)

    def test_restarts_once_the_notice_had_time_to_be_read(self):
        relaunch, _notifier, scheduler, restart = self.build()
        relaunch.relaunch_onto_another_screen()
        (delay_ms, _callback), = scheduler.pending
        scheduler.run_pending()
        assert delay_ms > 0
        assert restart.restarts == 1
