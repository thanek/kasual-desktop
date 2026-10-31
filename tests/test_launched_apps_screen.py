from domain.display.launched_apps_screen import RELAUNCH_GRACE_MS, LaunchedAppsFollowKasual
from domain.lifecycle.app_events import AppFinished, AppStarted
from domain.shared.event_emitter import EventEmitter


class FakeProcesses:
    def __init__(self):
        self.started = EventEmitter[AppStarted]()
        self.finished = EventEmitter[AppFinished]()

    def on_started(self, handler):
        return self.started.subscribe(handler)

    def on_finished(self, handler):
        return self.finished.subscribe(handler)


class FakePrimary:
    def __init__(self):
        self.calls = []

    def lend_to_kasual_screen(self):
        self.calls.append("lend")

    def reclaim(self):
        self.calls.append("reclaim")


class ManualScheduler:
    def __init__(self):
        self.pending = []

    def call_later(self, delay_ms, callback):
        self.pending.append((delay_ms, callback))

    def run_all(self):
        pending, self.pending = self.pending, []
        for _delay, callback in pending:
            callback()


def following():
    processes, primary, scheduler = FakeProcesses(), FakePrimary(), ManualScheduler()
    follow = LaunchedAppsFollowKasual(processes, primary, scheduler)
    return follow, processes, primary, scheduler


def test_a_launched_app_borrows_the_primary_screen():
    _follow, processes, primary, _scheduler = following()
    processes.started.emit(AppStarted("steam"))
    assert primary.calls == ["lend"]


def test_a_second_app_does_not_borrow_it_again():
    _follow, processes, primary, _scheduler = following()
    processes.started.emit(AppStarted("steam"))
    processes.started.emit(AppStarted("yt"))
    assert primary.calls == ["lend"]


def test_the_last_app_to_finish_gives_it_back_after_a_grace_period():
    _follow, processes, primary, scheduler = following()
    processes.started.emit(AppStarted("steam"))
    processes.started.emit(AppStarted("yt"))
    processes.finished.emit(AppFinished("steam"))
    assert scheduler.pending == []
    processes.finished.emit(AppFinished("yt"))
    assert primary.calls == ["lend"]
    assert [delay for delay, _ in scheduler.pending] == [RELAUNCH_GRACE_MS]
    scheduler.run_all()
    assert primary.calls == ["lend", "reclaim"]


def test_a_relaunch_within_the_grace_period_keeps_it_lent():
    _follow, processes, primary, scheduler = following()
    processes.started.emit(AppStarted("steam"))
    processes.finished.emit(AppFinished("steam"))
    processes.started.emit(AppStarted("steam"))
    scheduler.run_all()
    assert primary.calls == ["lend"]


def test_quitting_gives_it_back_at_once_even_with_an_app_running():
    follow, processes, primary, scheduler = following()
    processes.started.emit(AppStarted("steam"))
    follow.release()
    assert primary.calls == ["lend", "reclaim"]
    assert scheduler.pending == []


def test_after_giving_it_back_the_next_launch_borrows_again():
    _follow, processes, primary, scheduler = following()
    processes.started.emit(AppStarted("steam"))
    processes.finished.emit(AppFinished("steam"))
    scheduler.run_all()
    processes.started.emit(AppStarted("steam"))
    assert primary.calls == ["lend", "reclaim", "lend"]
