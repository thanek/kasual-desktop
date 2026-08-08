"""Tests for SingleInstanceGuard, on a real QLockFile — a mocked `getLockInfo()`
is exactly the thing that broke.

PyQt6 answers `(ok, pid, hostname, appname)`; unpacking it as anything else turns
"already running" into a traceback at startup, so the refusal path is asserted on
the real thing.
"""

import logging
import os

import pytest

from infrastructure.common.single_instance import SingleInstanceGuard


class FakeNotifier:
    def __init__(self):
        self.shown = []

    def notify(self, summary, body=""):
        self.shown.append((summary, body))


@pytest.fixture
def guards(tmp_path):
    first, second = SingleInstanceGuard(tmp_path), SingleInstanceGuard(tmp_path)
    yield first, second
    first.release()
    second.release()


def test_second_instance_is_refused_without_raising(guards, caplog):
    first, second = guards
    assert first.try_lock() is True

    with caplog.at_level(logging.WARNING):
        assert second.try_lock() is False

    assert "already running" in caplog.text
    assert str(os.getpid()) in caplog.text


def test_lock_is_reusable_after_release(guards):
    first, second = guards
    assert first.try_lock() is True
    first.release()

    assert second.try_lock() is True


def test_second_instance_tells_the_user_on_screen(tmp_path):
    notifier = FakeNotifier()
    first = SingleInstanceGuard(tmp_path)
    second = SingleInstanceGuard(tmp_path, notifier)
    assert first.try_lock() is True

    try:
        assert second.try_lock() is False
    finally:
        first.release()

    (summary, body), = notifier.shown
    assert "Kasual Desktop" in summary
    assert str(os.getpid()) in body


def test_the_holder_of_the_lock_is_not_notified(tmp_path):
    notifier = FakeNotifier()
    guard = SingleInstanceGuard(tmp_path, notifier)

    assert guard.try_lock() is True
    guard.release()

    assert notifier.shown == []


def test_unwritable_lock_dir_reports_the_real_reason(tmp_path, caplog):
    lock_dir = tmp_path / "readonly"
    lock_dir.mkdir()
    lock_dir.chmod(0o500)
    guard = SingleInstanceGuard(lock_dir)

    try:
        with caplog.at_level(logging.ERROR):
            assert guard.try_lock() is False
    finally:
        lock_dir.chmod(0o700)

    assert "already running" not in caplog.text
    assert "Cannot acquire" in caplog.text
