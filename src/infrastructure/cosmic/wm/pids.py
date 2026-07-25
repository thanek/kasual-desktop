"""Best-effort PID for a COSMIC toplevel.

No toplevel protocol carries one and a Wayland client cannot ask who owns someone
else's surface, so two sources recover it: ``_NET_WM_PID`` on the XWayland window
of the same class (:mod:`.xwayland`), and the process table matched by app_id.

The answer is a *set*, because app_id cannot separate two instances of one program.
That answers what the lifecycle asks — "is this window one I just launched?" — and
where a single number is unavoidable an unresolvable set collapses to 0, which the
domain reads as "not one of ours". A wrong PID would be worse than none.
"""

from __future__ import annotations

import logging
import os

from collections.abc import Iterable, Sequence

from domain.catalog.window_rules import walk_parent_chain
from infrastructure.cosmic.wm.toplevels import Toplevel
from infrastructure.cosmic.wm.xwayland import X11Window, XWaylandWindows, match
from infrastructure.linux.proc import parent_pid

logger = logging.getLogger(__name__)

_COMM_MAX = 15


class WindowPidResolver:
    """Resolves toplevels to the PIDs that could own them, keyed by identifier.

    The X11 table is passed in where a caller already scanned it, so a refresh
    costs one scan; otherwise this takes its own.
    """

    def __init__(self, xwayland: XWaylandWindows | None = None) -> None:
        self._xwayland = xwayland or XWaylandWindows()

    def resolve(self, toplevels: Sequence[Toplevel],
                x11: Sequence[X11Window] | None = None) -> dict[str, frozenset[int]]:
        candidates: dict[str, frozenset[int]] = {}
        unresolved: list[Toplevel] = []
        x11 = self._xwayland.snapshot() if x11 is None else x11
        for toplevel in toplevels:
            window = match(x11, toplevel)
            if window is not None and window.pid:
                candidates[toplevel.identifier] = frozenset({window.pid})
            else:
                unresolved.append(toplevel)
        if unresolved:
            processes = _process_table()
            for toplevel in unresolved:
                named = _named_processes(processes, toplevel.app_id)
                if named:
                    candidates[toplevel.identifier] = named
        return candidates


def representative_pid(candidates: frozenset[int]) -> int:
    """The one PID that stands for a window, or 0 when the candidates disagree.

    A client with a process per window (cosmic-term) offers several candidates for
    one toplevel; the ancestor they all descend from is the one a launch started.
    Separate instances have no such root and stay unattributed rather than guessed.
    """
    for pid in candidates:
        if all(pid in walk_parent_chain(other, parent_pid) for other in candidates):
            return pid
    return 0


# ── process table ──────────────────────────────────────────────────────────

def _named_processes(processes: dict[str, set[int]], app_id: str) -> frozenset[int]:
    """Every process running under *app_id*, or under its last reverse-DNS segment
    (``com.system76.CosmicTerm`` → the ``CosmicTerm`` binary)."""
    for key in (app_id, app_id.rsplit(".", 1)[-1]):
        candidates = processes.get(_normalise(key))
        if candidates:
            return frozenset(candidates)
    return frozenset()


def _process_table() -> dict[str, set[int]]:
    """Normalised process names to the PIDs answering to them."""
    table: dict[str, set[int]] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        for name in _process_names(pid):
            table.setdefault(_normalise(name), set()).add(pid)
    return table


def _process_names(pid: int) -> Iterable[str]:
    names = []
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8") as f:
            comm = f.read().strip()
        # Truncated comm matches the wrong app_id outright: cosmic-settings-daemon
        # arrives as "cosmic-settings". The sources below are untruncated.
        if len(comm) < _COMM_MAX:
            names.append(comm)
    except OSError:
        pass
    try:
        names.append(os.path.basename(os.readlink(f"/proc/{pid}/exe")))
    except OSError:
        pass
    try:
        with open(f"/proc/{pid}/cmdline", encoding="utf-8", errors="replace") as f:
            argv0 = f.read().split("\0")[0]
        if argv0:
            names.append(os.path.basename(argv0))
    except OSError:
        pass
    return [n for n in names if n]


def _normalise(name: str) -> str:
    """``CosmicTerm`` and ``cosmic-term`` name the same program."""
    return "".join(c for c in name.lower() if c.isalnum())
