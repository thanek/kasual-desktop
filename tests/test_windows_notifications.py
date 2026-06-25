"""Tests for WindowsNotificationSource (the WinRT Action Center poller).

Exercises the pure parse/diff helpers with fake WinRT ``UserNotification``
stand-ins and the source's priming behaviour. The WinRT projection is imported
lazily inside the poll loop, so importing the module — and these tests — triggers
no WinRT load and runs cross-platform. Emission is tested via the source's signal,
which delivers synchronously here (same-thread emit → direct connection).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from infrastructure.windows.notifications.listener import (
    WindowsNotificationSource,
    partition_new,
    _to_notification,
)


# ── fake WinRT UserNotification ────────────────────────────────────────────────

def _binding(texts):
    """A NotificationBinding stand-in, or None when there is no toast binding."""
    if texts is None:
        return None
    return SimpleNamespace(
        get_text_elements=lambda: [SimpleNamespace(text=t) for t in texts]
    )


class _RaisingAppInfo:
    """app_info whose display_info access blows up (mirrors a missing projection)."""
    @property
    def display_info(self):
        raise RuntimeError("display_info unavailable")


def _fake_un(nid, app="App", texts=("Title", "Body"), when=None, app_raises=False):
    visual = SimpleNamespace(
        get_binding=lambda name: _binding(texts) if name == "ToastGeneric" else None
    )
    app_info = _RaisingAppInfo() if app_raises else SimpleNamespace(
        display_info=SimpleNamespace(display_name=app)
    )
    return SimpleNamespace(
        id=nid,
        app_info=app_info,
        notification=SimpleNamespace(visual=visual),
        creation_time=when or datetime(2026, 6, 24, 12, 0, 0),
    )


# ── _to_notification ───────────────────────────────────────────────────────────

class TestToNotification:
    def test_first_text_is_summary_rest_is_body(self):
        n = _to_notification(_fake_un(1, app="Steam", texts=("Update", "L1", "L2")))
        assert n.app_name == "Steam"
        assert n.summary == "Update"
        assert n.body == "L1\nL2"
        assert n.icon is None
        assert n.timestamp == datetime(2026, 6, 24, 12, 0, 0)

    def test_single_text_has_empty_body(self):
        n = _to_notification(_fake_un(1, texts=("Only",)))
        assert n.summary == "Only"
        assert n.body == ""

    def test_no_texts_returns_none(self):
        assert _to_notification(_fake_un(1, texts=())) is None

    def test_no_toast_binding_returns_none(self):
        assert _to_notification(_fake_un(1, texts=None)) is None

    def test_blank_app_name_falls_back(self):
        assert _to_notification(_fake_un(1, app="")).app_name == "?"

    def test_app_info_error_falls_back(self):
        assert _to_notification(_fake_un(1, app_raises=True)).app_name == "?"

    def test_aware_utc_timestamp_becomes_naive_local(self):
        # WinRT hands back tz-aware UTC; the rest of the app subtracts it from a
        # naive datetime.now(), so the stored timestamp must be naive (and the
        # comparison must not raise an offset-naive/aware TypeError).
        aware = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone(timedelta(hours=2)))
        n = _to_notification(_fake_un(1, when=aware))
        assert n.timestamp.tzinfo is None
        # 12:00 at +02:00 == 10:00 UTC, rendered in the local zone.
        expected = aware.astimezone().replace(tzinfo=None)
        assert n.timestamp == expected
        # Sanity: the value object now subtracts cleanly against naive now().
        (datetime.now() - n.timestamp)


# ── partition_new ──────────────────────────────────────────────────────────────

class TestPartitionNew:
    def test_first_poll_suppresses_backlog(self):
        notes = [_fake_un(1), _fake_un(2)]
        fresh, seen, primed = partition_new(notes, set(), primed=False)
        assert fresh == []            # nothing emitted on the priming pass
        assert seen == {1, 2}         # but the backlog seeds the seen-set
        assert primed is True

    def test_emits_only_unseen_after_priming(self):
        notes = [_fake_un(2), _fake_un(3), _fake_un(4)]
        fresh, seen, primed = partition_new(notes, {1, 2, 3}, primed=True)
        assert [un.id for un in fresh] == [4]
        assert seen == {2, 3, 4}
        assert primed is True

    def test_seen_tracks_current_so_dismissed_ids_can_re_emit(self):
        # id 2 fell out of the Action Center → dropped from seen; a later re-post
        # would then count as new again.
        _, seen, _ = partition_new([_fake_un(1)], {1, 2, 3}, primed=True)
        assert seen == {1}


# ── WindowsNotificationSource (priming + emission) ─────────────────────────────

class TestSourceEmission:
    def test_priming_then_new_notification(self, qapp):
        source = WindowsNotificationSource()
        received = []
        source.on_notification(received.append)

        # First poll = priming: existing toasts are swallowed.
        source._process([_fake_un(1, app="A"), _fake_un(2, app="B")])
        assert received == []

        # Next poll: only the genuinely new id (3) is published.
        source._process([_fake_un(2, app="B"), _fake_un(3, app="C", texts=("Hi",))])
        assert len(received) == 1
        assert received[0].app_name == "C"
        assert received[0].summary == "Hi"

    def test_start_is_idempotent(self, qapp, monkeypatch):
        source = WindowsNotificationSource()
        started = []
        monkeypatch.setattr(
            source, "_run", lambda: started.append(True)
        )
        # Patch Thread to call target synchronously so we can assert single-start.
        import infrastructure.windows.notifications.listener as mod

        class _ImmediateThread:
            def __init__(self, target, **kw):
                self._target = target
            def start(self):
                self._target()

        monkeypatch.setattr(mod.threading, "Thread", _ImmediateThread)
        source.start()
        source.start()  # second call must be a no-op (already running)
        assert started == [True]
