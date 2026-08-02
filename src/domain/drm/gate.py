"""Offers the DRM setup checklist when a chosen app needs a CDM the system lacks.

The gate never withholds ``on_done``: Widevine is optional, and a user who
declines it still reaches a working desktop with the app installed.
"""

from collections.abc import Callable

from domain.drm.plan import Readiness
from domain.drm.ports import DrmSetupView, PlaybackProbe
from domain.drm.readiness import DrmReadiness


class DrmSetupGate:
    def __init__(
        self,
        readiness: DrmReadiness,
        view: DrmSetupView,
        probe: PlaybackProbe | None = None,
    ) -> None:
        self._readiness = readiness
        self._view = view
        self._probe = probe

    def ensure(self, on_done: Callable[[], None]) -> None:
        report = self._readiness.report()
        if report.state is Readiness.READY:
            on_done()
            return
        self._view.present(
            report,
            on_recheck=self._readiness.report,
            on_done=on_done,
            on_verify=None if self._probe is None else self._probe.can_play_protected,
        )
