"""The run every scenario is wrapped in: bring-up, teardown, artifact, exit code.

A scenario body starts with KD already on the Home view and the two sources of
truth already open, and it may give up at any point by raising ScenarioAborted —
the screen is still handed back the way it was found.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from PyQt6.QtCore import QCoreApplication

from tests.behavioral.harness import requirements, shell, timeouts
from tests.behavioral.harness.kd_client import KDClient
from tests.behavioral.harness.report import (
    ScenarioAborted, report, reset, results, summary,
)
from tests.behavioral.harness.requirements import Requirement
from tests.behavioral.harness.virtual_pad import VirtualPad
from tests.behavioral.harness.window_source import WindowSource, build_window_source

ARTIFACTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'artifacts')

_app: QCoreApplication | None = None


def _compositor_name() -> str:
    from infrastructure.linux.compositor import detect_compositor
    return detect_compositor().value


def _application() -> QCoreApplication:
    """One per process, and it must outlive every Session: a collected QCoreApplication
    takes Qt's D-Bus machinery with it, leaving interfaces cached across scenarios —
    KD's own GNOME helper client — pointing at deleted C++ objects."""
    global _app
    if _app is None:
        _app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    return _app


@dataclass(frozen=True)
class Scenario:
    """A scenario as the runner sees it: what it needs, and what it does."""

    name: str
    title: str
    body: Callable[['Session'], None]
    requires: tuple[Requirement, ...] = field(default_factory=tuple)

    def run(self) -> int:
        return Session(self).run()


class Session:
    """Owns the three channels a scenario talks through — the virtual pad, KD's test
    API, the compositor's window events."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.pad: VirtualPad
        self.kd: KDClient
        self.windows: WindowSource
        self._cleanups: list[Callable[[], None]] = []
        self._histories: dict[str, list[dict]] = {}

    def record(self, name: str, history: list[dict]) -> None:
        """Keep an app's own answers for the artifact, beside Kasual Desktop's."""
        self._histories[name] = history

    def add_cleanup(self, cleanup: Callable[[], None]) -> None:
        """Run *cleanup* on the way out, whatever happened. A scenario that leaves a
        game on the screen has already broken the next one."""
        self._cleanups.append(cleanup)

    def run(self) -> int:
        reset()
        print(f'\n{self.scenario.name}: {self.scenario.title}\n', flush=True)
        self._app = _application()

        try:
            requirements.check(requirements.BASE + self.scenario.requires, kd=None)
        except ScenarioAborted:
            return summary()

        self.pad = VirtualPad()
        report('virtual pad created', 'PASS', self.pad.device_path)
        self.kd = KDClient()
        self.windows = build_window_source()
        try:
            requirements.check(requirements.BASE + self.scenario.requires, kd=self.kd)
            self.windows.start(timeouts.WINDOW_SOURCE)
            report('window source installed', 'PASS',
                   f'{type(self.windows).__name__}, '
                   f'{len(self.windows.last_stack())} windows in the initial stack')
            shell.expect_home_view(self.kd)
            self.scenario.body(self)
        except ScenarioAborted as abort:
            report('scenario abandoned', 'INFO', str(abort))
        finally:
            self._tear_down()
        return summary()

    def _tear_down(self) -> None:
        print('\ncleanup:', flush=True)
        self.pad.back()   # drop the Home menu if it is still up
        for cleanup in reversed(self._cleanups):
            cleanup()
        shell.await_no_foreground(self.kd)
        # KD minimizes itself when its gamepad goes away, so unplugging the virtual
        # pad *is* the minimize — no command channel needed.
        self.pad.close()
        shell.await_minimized(self.kd)
        self._write_artifact()
        self.windows.stop()

    def _write_artifact(self) -> None:
        os.makedirs(ARTIFACTS, exist_ok=True)
        path = os.path.join(
            ARTIFACTS, f'{self.scenario.name}-{time.strftime("%Y%m%d-%H%M%S")}.json')
        with open(path, 'w') as f:
            json.dump({'scenario': self.scenario.name,
                       'compositor': _compositor_name(),
                       'results': results,
                       'presses': self.pad.presses,
                       'events': self.windows.events,
                       'kd_snapshots': self.kd.history,
                       **self._histories}, f, indent=1)
        print(f'\nevent log: {path} ({len(self.pad.presses)} presses, '
              f'{len(self.windows.events)} events, '
              f'{len(self.kd.history)} KD snapshots)', flush=True)
