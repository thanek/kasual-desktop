"""Client for Kasual Desktop's test API (KD_TEST_API=1) — read the shell's state.

Layer-shell surfaces never appear in KWin's stackingOrder, so what KD has on
screen can only be learned from KD itself. The protocol makes the answers
conclusive: the Home menu is an `overlay`-layer surface, so mapped ⇒ above every
window, game included; the ceded Desktop sunk to `bottom` ⇒ below the app's
windows, splash included.
"""

import json
import os
import time

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QEventLoop, QLockFile
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

from tests.behavioral.harness import progress

_SVC  = 'org.consoledesktop.KasualDesktop'
_PATH = '/Shell'

# Where SingleInstanceGuard puts KD's lock (src/main.py logs next to it).
_LOCK = Path.home() / '.local' / 'cache' / 'kasual' / 'kasual.lock'


class KasualDesktopUnavailable(RuntimeError):
    pass


def running_pid() -> int | None:
    """The pid of a live Kasual Desktop, whatever built it — the packaged one too.

    Read from the single-instance lock, so a lock a crash left behind names a pid
    that is no longer there, and is not mistaken for a running KD.
    """
    readable, pid, _hostname, _appname = QLockFile(str(_LOCK)).getLockInfo()
    if not readable or not pid:
        return None
    return pid if os.path.isdir(f'/proc/{pid}') else None


# What the harness reads. A KD that answers with less than this is a KD older than
# the harness — the run would otherwise die of a KeyError halfway through a scenario.
_SNAPSHOT_KEYS = frozenset({
    'desktop_visible', 'desktop_mapped', 'desktop_sunk', 'home_header_mapped',
    'hint_bar_mapped', 'home_menu', 'tile_menu', 'confirm', 'hud', 'focus', 'tiles',
    'foreground',
})


def test_api_answers() -> bool:
    try:
        snapshot = KDClient().snapshot()
    except KasualDesktopUnavailable:
        return False
    return _SNAPSHOT_KEYS <= snapshot.keys()


class KDClient:
    def __init__(self) -> None:
        self._iface = QDBusInterface(
            _SVC, _PATH, '', QDBusConnection.sessionBus(),
        )
        # Every state KD reported, for the artifact: a failed stacking assertion
        # is only readable against what KD was doing at the time.
        self.history: list[dict] = []

    def snapshot(self) -> dict:
        reply = self._iface.call('Snapshot')
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            raise KasualDesktopUnavailable(
                f'no answer from {_SVC}: {reply.errorMessage()} — is Kasual Desktop '
                'running with KD_TEST_API=1?'
            )
        snap = json.loads(reply.arguments()[0])
        self.history.append({'at': time.time(), **snap})
        return snap

    def tile(self, app_id: str) -> dict:
        """Locate a tile by its id, or failing that by its displayed name — tiles
        KD provisioned itself carry the game's name as their id."""
        tiles = self.snapshot()['tiles']
        for key in ('app_id', 'name'):
            for tile in tiles:
                if tile[key] == app_id:
                    return tile
        known = ', '.join(f'{t["app_id"]!r}' for t in tiles)
        raise KeyError(f'no tile with app_id or name {app_id!r}; tiles: {known}')

    def tile_index(self, app_id: str) -> int:
        return self.tile(app_id)['index']

    def tile_name(self, app_id: str) -> str:
        return self.tile(app_id)['name']

    def wait_until(self, predicate: Callable[[dict], bool], timeout_s: float,
                   description: str) -> dict:
        """Poll the snapshot until *predicate* holds. Polling is fine here: unlike
        another app's splash, KD's own state is not short-lived — the test drives it."""
        deadline = time.monotonic() + timeout_s
        with progress.waiting(description, timeout_s) as bar:
            while True:
                snap = self.snapshot()
                if predicate(snap):
                    return snap
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f'timed out after {timeout_s}s waiting for: {description}'
                    )
                bar.tick()
                QCoreApplication.processEvents(
                    QEventLoop.ProcessEventsFlag.AllEvents, 50,
                )
                time.sleep(0.1)
