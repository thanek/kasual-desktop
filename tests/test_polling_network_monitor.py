"""Tests for the domain PollingNetworkMonitor — the change-detection that lets
any pull-only backend (a NetworkProbe) become a live NetworkMonitor, without any
infrastructure. This is the seam that makes alternative implementations cheap.
"""

from domain.network.polling import PollingNetworkMonitor
from domain.network.status import NetworkKind, NetworkStatus


class FakeScheduler:
    """Captures the next scheduled callback so the test can fire ticks."""

    def __init__(self):
        self._pending = None

    def call_later(self, delay_ms, callback):
        self._pending = callback

    def fire(self):
        cb, self._pending = self._pending, None
        if cb:
            cb()


class FakeProbe:
    def __init__(self, statuses):
        self._statuses = list(statuses)
        self._i = 0

    def read(self):
        s = self._statuses[min(self._i, len(self._statuses) - 1)]
        self._i += 1
        return s


_OFF = NetworkStatus.offline()
_WIFI = NetworkStatus(NetworkKind.WIFI, name="Dom", signal=70)


class TestPollingNetworkMonitor:
    def test_initial_sample_is_current(self):
        mon = PollingNetworkMonitor(FakeProbe([_WIFI]), FakeScheduler())
        assert mon.current() == _WIFI

    def test_emits_only_on_change(self):
        sched = FakeScheduler()
        # construction consumes [0]=_OFF; ticks then read _OFF, _WIFI, _WIFI
        mon = PollingNetworkMonitor(FakeProbe([_OFF, _OFF, _WIFI, _WIFI]), sched)
        seen = []
        mon.on_changed(seen.append)
        mon.start()

        sched.fire()                 # _OFF == current → no emit
        assert seen == []
        sched.fire()                 # _WIFI → emit
        assert seen == [_WIFI]
        assert mon.current() == _WIFI
        sched.fire()                 # _WIFI again → no emit
        assert seen == [_WIFI]

    def test_stop_halts_polling(self):
        sched = FakeScheduler()
        mon = PollingNetworkMonitor(FakeProbe([_OFF, _WIFI]), sched)
        seen = []
        mon.on_changed(seen.append)
        mon.start()
        mon.stop()
        sched.fire()                 # tick after stop is a no-op
        assert seen == []
