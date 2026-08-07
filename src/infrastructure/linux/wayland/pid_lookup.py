"""Which process owns a Wayland toplevel, worked out from its ``app_id``.

``wlr-foreign-toplevel-management`` names windows but never says whose process
they are, while ``Window.pid`` drives tile ownership, icon lookup and game
detection. So the app id is matched against what /proc says each process is
called, and an unmatched window keeps ``pid=0`` — which the window rules already
treat as "not attributable to any of our apps".

An ``app_id`` is a desktop-entry name, not a command: ``org.gnome.Nautilus`` runs
as ``nautilus``, ``firefox-esr.desktop`` as ``firefox-esr`` — so its last dotted
component is tried as well as the whole id.
"""

from __future__ import annotations

import os
import time

from pathlib import Path

_COMM_MAX = 15

MIN_NAME_LENGTH = 3
"""Below this a name says too little to match on loosely (``sh``, ``qt``)."""


def app_id_keys(app_id: str) -> list[str]:
    """The names a process could plausibly carry for *app_id*, best first."""
    base = app_id.lower().removesuffix(".desktop")
    keys = [base]
    _, _, last = base.rpartition(".")
    if last and last != base:
        keys.append(last)
    return keys


class ProcessNames:
    """What each live process is called, read from /proc once per scan."""

    def __init__(self, proc_root: str = "/proc") -> None:
        self._root = Path(proc_root)
        self.names: dict[int, set[str]] = {}

    def scan(self) -> None:
        self.names = {}
        for entry in self._pids():
            names = self._names_of(entry)
            if names:
                self.names[entry] = names

    def _pids(self) -> list[int]:
        try:
            return [int(p.name) for p in self._root.iterdir() if p.name.isdigit()]
        except OSError:
            return []

    def _names_of(self, pid: int) -> set[str]:
        directory = self._root / str(pid)
        names = {
            self._read(directory / "comm").strip(),
            os.path.basename(self._read(directory / "cmdline").split("\0")[0]),
            os.path.basename(self._link(directory / "exe")),
        }
        return {name.lower() for name in names if name}

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    @staticmethod
    def _link(path: Path) -> str:
        try:
            return os.readlink(path)
        except OSError:
            return ""


def match_pid(keys: list[str], names: dict[int, set[str]]) -> int:
    """The lowest pid whose name answers to one of *keys*, or 0.

    Exact matches win over a truncated ``comm`` and both over a substring, so
    ``steam`` never claims ``steamwebhelper`` while a real match exists. The
    lowest pid settles the rest: for a process that forks workers sharing one
    name, that is the parent.
    """
    for match in (_exact, _truncated, _substring):
        candidates = [pid for pid, names_of in sorted(names.items())
                      if match(keys, names_of)]
        if candidates:
            return candidates[0]
    return 0


def _exact(keys: list[str], names: set[str]) -> bool:
    return any(key in names for key in keys)


def _truncated(keys: list[str], names: set[str]) -> bool:
    return any(key[:_COMM_MAX] in names for key in keys if len(key) > _COMM_MAX)


def _substring(keys: list[str], names: set[str]) -> bool:
    return any(key in name or name in key
               for key in keys
               for name in names if len(name) >= MIN_NAME_LENGTH)


class AppIdPidResolver:
    """Resolves an ``app_id`` to a pid, and remembers the answer.

    A cached pid is dropped once its process is gone, so an app restarted under
    the same name resolves afresh. An id that matches nothing is not cached —
    the process may simply not have started yet — but the retry is rate-limited,
    so a window nothing ever matches does not walk /proc on every refresh.
    """

    def __init__(self, proc_root: str = "/proc", rescan_interval_s: float = 2.0) -> None:
        self._processes = ProcessNames(proc_root)
        self._proc_root = Path(proc_root)
        self._rescan_interval_s = rescan_interval_s
        self._cache: dict[str, int] = {}
        self._last_scan = 0.0

    def resolve(self, app_ids: list[str]) -> dict[str, int]:
        """Map every id in *app_ids* to a pid (0 where none was found)."""
        self._drop_dead()
        unresolved = [app_id for app_id in app_ids
                      if app_id and app_id not in self._cache]
        if unresolved and self._due_for_scan():
            self._processes.scan()
            for app_id in unresolved:
                pid = match_pid(app_id_keys(app_id), self._processes.names)
                if pid:
                    self._cache[app_id] = pid
        return {app_id: self._cache.get(app_id, 0) for app_id in app_ids}

    def _due_for_scan(self) -> bool:
        now = time.monotonic()
        if now - self._last_scan < self._rescan_interval_s:
            return False
        self._last_scan = now
        return True

    def _drop_dead(self) -> None:
        for app_id, pid in list(self._cache.items()):
            if not (self._proc_root / str(pid)).exists():
                del self._cache[app_id]
