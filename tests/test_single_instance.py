"""Tests for the single-instance lock.

Refusing a second instance is the *quiet* path — it must not be the crashing one.
PyQt6's ``QLockFile.getLockInfo`` answers ``(ok, pid, hostname, appname)``, and
reading it as anything else turns "already running" into a traceback at startup.
"""

import pytest

from infrastructure.common.single_instance import SingleInstanceGuard


@pytest.fixture
def lock_dir(tmp_path):
    return tmp_path


class TestSingleInstanceGuard:
    def test_first_instance_takes_the_lock(self, lock_dir):
        assert SingleInstanceGuard(lock_dir).try_lock() is True

    def test_second_instance_is_refused_without_raising(self, lock_dir):
        first = SingleInstanceGuard(lock_dir)
        assert first.try_lock() is True
        assert SingleInstanceGuard(lock_dir).try_lock() is False

    def test_the_refusal_names_the_holder(self, lock_dir, caplog):
        holder = SingleInstanceGuard(lock_dir)   # held: QLockFile unlocks on GC
        holder.try_lock()
        with caplog.at_level("WARNING"):
            SingleInstanceGuard(lock_dir).try_lock()
        assert "already running" in caplog.text
        assert "PID" in caplog.text

    def test_releasing_lets_the_next_instance_in(self, lock_dir):
        first = SingleInstanceGuard(lock_dir)
        first.try_lock()
        first.release()
        assert SingleInstanceGuard(lock_dir).try_lock() is True
