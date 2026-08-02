"""Show the DRM setup card on its own, without starting Kasual Desktop.

Usage:
    python3 drm_card_preview.py [incomplete|unsupported|ready]

incomplete   pretends Widevine is missing (the wizard as a fresh user sees it)
unsupported  pretends an architecture no recipe covers
ready        uses this machine as it really is

In the pretending scenarios the CDM stays hidden until the marker file exists,
so "Check again" has something to discover: with the card open, run

    touch /tmp/kd-drm-test-cdm

and press Check again. "Verify playback" always runs the real probe against the
real module, and is clickable once the report turns READY.
"""

import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path("/home/xis/projekty/kasual-desktop")
sys.path.insert(0, str(REPO / "src"))

from PyQt6.QtWidgets import QApplication                                # noqa: E402

from domain.drm.readiness import DrmReadiness                           # noqa: E402
from infrastructure.common.drm.playback_probe import (                  # noqa: E402
    QtWebEnginePlaybackProbe,
)
from infrastructure.common.qt.i18n import install_translations          # noqa: E402
from infrastructure.common.qt.overlays.drm_setup_overlay import (       # noqa: E402
    QtDrmSetupView,
)
from infrastructure.linux.drm.facts import LinuxSystemFacts             # noqa: E402


MARKER = Path("/tmp/kd-drm-test-cdm")


class FakeFacts(LinuxSystemFacts):
    def __init__(self, *, hide_cdm: bool = False, arch: str = "") -> None:
        self._hide_cdm = hide_cdm
        self._arch = arch

    def cdm_path(self):
        if self._hide_cdm and not MARKER.exists():
            return None
        return super().cdm_path()

    def machine(self):
        real = super().machine()
        return replace(real, arch=self._arch) if self._arch else real


class StubPad:
    def push_handler(self, handler) -> None: ...
    def pop_handler(self, handler) -> None: ...


SCENARIOS = {
    "incomplete":  FakeFacts(hide_cdm=True),
    "unsupported": FakeFacts(hide_cdm=True, arch="riscv64"),
    "ready":       LinuxSystemFacts(),
}


def main() -> int:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "incomplete"
    if scenario not in SCENARIOS:
        print(f"unknown scenario {scenario!r}; pick one of {sorted(SCENARIOS)}")
        return 2

    facts = SCENARIOS[scenario]
    readiness = DrmReadiness(facts)
    report = readiness.report()
    print(f"scenario={scenario} state={report.state.value} "
          f"steps={[(s.step.title, s.done) for s in report.steps]}")
    print(f"CDM marker: {MARKER} ({'present' if MARKER.exists() else 'absent'})")

    app = QApplication(sys.argv)
    install_translations(app, str(REPO / "locale"))
    view = QtDrmSetupView(StubPad(), MagicMock())
    view.present(
        report,
        on_recheck=readiness.report,
        on_done=app.quit,
        on_verify=QtWebEnginePlaybackProbe(LinuxSystemFacts()).can_play_protected,
    )
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
