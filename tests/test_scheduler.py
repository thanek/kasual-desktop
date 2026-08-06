"""Tests for the Qt adapter of the Scheduler port."""

import gc

from infrastructure.common.qt.scheduler import QtScheduler


class Deferrable:
    """Reports through a list the caller owns, so the instance itself can be dropped."""

    def __init__(self, log):
        self._log = log

    def run(self):
        self._log.append("ran")


def test_callback_runs_after_the_delay(qapp, qtbot):
    ran = []
    target = Deferrable(ran)

    QtScheduler().call_later(10, target.run)

    qtbot.waitUntil(lambda: bool(ran), timeout=500)


def test_callback_survives_a_caller_that_kept_no_reference(qapp, qtbot):
    ran = []

    QtScheduler().call_later(10, Deferrable(ran).run)
    gc.collect()

    qtbot.waitUntil(lambda: bool(ran), timeout=500)
