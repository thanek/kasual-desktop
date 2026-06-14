"""Turn a pull-only `NetworkProbe` into a `NetworkMonitor` — in the domain.

This is the reusable change-detection that lets *any* sampling backend (nmcli,
/sys, systemd-networkd) become a live monitor without re-implementing the diff:
it polls the probe on an interval through the injected `Scheduler` and emits
`on_changed` only when the sampled status actually differs (frozen-dataclass
equality). Pure application logic — no Qt, no timer of its own.

Event-driven backends (NetworkManager) don't need this; they implement
`NetworkMonitor` directly.
"""

from __future__ import annotations

from collections.abc import Callable

from domain.shared.event_emitter import EventEmitter, Unsubscribe
from domain.shared.scheduler import Scheduler
from domain.network.monitor import NetworkMonitor
from domain.network.probe import NetworkProbe
from domain.network.status import NetworkStatus

DEFAULT_INTERVAL_MS = 5000


class PollingNetworkMonitor(NetworkMonitor):
    """`NetworkMonitor` backed by periodic sampling of a `NetworkProbe`."""

    def __init__(
        self,
        probe: NetworkProbe,
        scheduler: Scheduler,
        interval_ms: int = DEFAULT_INTERVAL_MS,
    ) -> None:
        self._probe       = probe
        self._scheduler   = scheduler
        self._interval_ms = interval_ms
        self._emitter: EventEmitter[NetworkStatus] = EventEmitter()
        self._status      = probe.read()   # initial sample, so current() is valid
        self._running     = False

    # ── NetworkMonitor port ──────────────────────────────────────────────────

    def current(self) -> NetworkStatus:
        return self._status

    def on_changed(
        self, handler: Callable[[NetworkStatus], None]
    ) -> Unsubscribe:
        return self._emitter.subscribe(handler)

    # ── Lifecycle (driven by the composition root) ───────────────────────────

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._schedule()

    def stop(self) -> None:
        self._running = False

    # ── Internal ─────────────────────────────────────────────────────────────

    def _schedule(self) -> None:
        if self._running:
            self._scheduler.call_later(self._interval_ms, self._tick)

    def _tick(self) -> None:
        if not self._running:
            return
        sampled = self._probe.read()
        if sampled != self._status:
            self._status = sampled
            self._emitter.emit(sampled)
        self._schedule()
