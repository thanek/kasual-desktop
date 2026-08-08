"""Tests for the one-time "Kasual runs in the background" hint."""

from domain.shell.background_hint import BackgroundHint


class FakeNotifier:
    def __init__(self):
        self.shown = []

    def notify(self, summary, body=""):
        self.shown.append((summary, body))


class FakeMemory:
    def __init__(self, shown=False):
        self.shown = shown

    def was_ever_shown(self):
        return self.shown

    def mark_shown(self):
        self.shown = True


class FakeDesktop:
    def __init__(self, visible=False):
        self.visible = visible

    def is_visible(self):
        return self.visible


class ManualScheduler:
    def __init__(self):
        self.pending = []

    def call_later(self, delay_ms, callback):
        self.pending.append((delay_ms, callback))

    def run_pending(self):
        for _delay, callback in self.pending:
            callback()
        self.pending = []


def build(notifier=None, memory=None, desktop=None, scheduler=None):
    return BackgroundHint(
        notifier or FakeNotifier(), memory or FakeMemory(),
        desktop or FakeDesktop(), scheduler or ManualScheduler(),
    )


def test_hint_appears_while_the_desktop_stays_off_screen():
    notifier, scheduler = FakeNotifier(), ManualScheduler()
    build(notifier=notifier, scheduler=scheduler).offer()

    scheduler.run_pending()

    (summary, body), = notifier.shown
    assert "background" in summary
    assert body


def test_hint_waits_before_speaking():
    notifier, scheduler = FakeNotifier(), ManualScheduler()
    build(notifier=notifier, scheduler=scheduler).offer()

    assert notifier.shown == []
    (delay_ms, _callback), = scheduler.pending
    assert delay_ms > 0


def test_a_desktop_that_surfaced_meanwhile_says_it_better():
    notifier, memory = FakeNotifier(), FakeMemory()
    desktop, scheduler = FakeDesktop(visible=False), ManualScheduler()
    build(notifier=notifier, memory=memory, desktop=desktop, scheduler=scheduler).offer()

    desktop.visible = True
    scheduler.run_pending()

    assert notifier.shown == []
    assert memory.was_ever_shown() is False


def test_the_hint_is_shown_once_in_a_lifetime():
    notifier, scheduler = FakeNotifier(), ManualScheduler()
    memory = FakeMemory()
    build(notifier=notifier, memory=memory, scheduler=scheduler).offer()
    scheduler.run_pending()

    build(notifier=notifier, memory=memory, scheduler=scheduler).offer()
    scheduler.run_pending()

    assert len(notifier.shown) == 1


def test_a_hint_never_shown_is_not_remembered_as_shown():
    memory = FakeMemory()
    build(memory=memory, desktop=FakeDesktop(visible=True)).offer()

    assert memory.was_ever_shown() is False
