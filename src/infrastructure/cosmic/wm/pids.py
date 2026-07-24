"""Best-effort PID for a COSMIC toplevel.

Every other backend hands Kasual the owning process outright — KWin's scripting
API, the GNOME helper, ``swaymsg``, ``hyprctl`` — but no toplevel protocol carries
one, and a Wayland client cannot ask who owns someone else's surface. Two sources
recover it:

* **XWayland.** Every Proton and Steam title, and most older games, are X11 clients
  underneath, publishing ``_NET_WM_PID`` on a window whose ``WM_CLASS`` is the very
  app_id the toplevel reports.
* **The process table.** A native Wayland client is matched by app_id against the
  names its processes run under.

The answer is a *set* of candidates rather than one PID, because app_id often
cannot separate two instances of the same program. That is enough for the question
the lifecycle actually asks — "is this window one of the ones I just launched?" —
which :func:`representative_pid` cannot answer alone. Where a single number is
unavoidable, an unresolvable set collapses to 0, which the domain already reads as
"not attributable to an app of ours"; a wrong PID would be far worse than none.
"""

from __future__ import annotations

import logging
import os

from collections.abc import Iterable, Sequence

from domain.catalog.window_rules import walk_parent_chain
from infrastructure.cosmic.wm.toplevels import Toplevel
from infrastructure.linux.proc import parent_pid

logger = logging.getLogger(__name__)

_COMM_MAX = 15


class WindowPidResolver:
    """Resolves toplevels to the PIDs that could own them, keyed by identifier."""

    def __init__(self) -> None:
        self._xwayland = _XWaylandWindows()

    def resolve(self, toplevels: Sequence[Toplevel]) -> dict[str, frozenset[int]]:
        candidates: dict[str, frozenset[int]] = {}
        unresolved: list[Toplevel] = []
        x11 = self._xwayland.snapshot()
        for toplevel in toplevels:
            pid = _x11_pid(x11, toplevel)
            if pid:
                candidates[toplevel.identifier] = frozenset({pid})
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

    A client that runs a process per window — cosmic-term does — offers several
    equally named candidates for one toplevel. The process they all descend from
    is the one a launch would have started, and expanding its tree finds the
    others again, so it stands for the whole app. Genuinely separate instances
    have no such root and stay unattributed rather than guessed at.
    """
    for pid in candidates:
        if all(pid in walk_parent_chain(other, parent_pid) for other in candidates):
            return pid
    return 0


# ── XWayland ───────────────────────────────────────────────────────────────

class _X11Window:
    __slots__ = ("classes", "title", "pid")

    def __init__(self, classes: tuple[str, ...], title: str, pid: int) -> None:
        self.classes = classes
        self.title = title
        self.pid = pid


def _x11_pid(windows: Sequence[_X11Window], toplevel: Toplevel) -> int:
    """The PID of the X11 window this toplevel is, matched by class then title.

    Several instances of one app share a class, so the title breaks the tie; with
    no title match a single candidate is still unambiguous.
    """
    candidates = [w for w in windows if toplevel.app_id in w.classes]
    if not candidates:
        return 0
    titled = [w for w in candidates if w.title == toplevel.title]
    if len(titled) == 1:
        return titled[0].pid
    return candidates[0].pid if len(candidates) == 1 else 0


class _XWaylandWindows:
    """The X11 client list, read through a connection reopened on demand.

    Absent python-xlib or an X server the snapshot is simply empty, so a pure
    Wayland COSMIC session falls straight through to the process table.
    """

    def __init__(self) -> None:
        self._display = None
        self._atoms: dict = {}
        self._unavailable = False

    def snapshot(self) -> list[_X11Window]:
        try:
            display = self._ensure_display()
            if display is None:
                return []
            return self._read(display)
        except Exception as exc:
            logger.debug("XWayland window scan failed: %s", exc)
            self._display = None
            return []

    def _ensure_display(self):
        if self._display is not None:
            return self._display
        if self._unavailable or not os.environ.get("DISPLAY"):
            self._unavailable = True
            return None
        try:
            from Xlib import display
        except ImportError:
            logger.info("python-xlib not installed — XWayland window PIDs disabled")
            self._unavailable = True
            return None
        disp = display.Display()
        self._atoms = {
            "list": disp.intern_atom("_NET_CLIENT_LIST"),
            "pid": disp.intern_atom("_NET_WM_PID"),
            "name": disp.intern_atom("_NET_WM_NAME"),
        }
        self._display = disp
        return disp

    def _read(self, display) -> list[_X11Window]:
        from Xlib import X
        from Xlib.Xatom import CARDINAL

        listing = display.screen().root.get_full_property(
            self._atoms["list"], X.AnyPropertyType)
        if listing is None:
            return []
        windows: list[_X11Window] = []
        for window_id in listing.value:
            window = display.create_resource_object("window", window_id)
            pid = window.get_full_property(self._atoms["pid"], CARDINAL)
            if pid is None or not pid.value:
                continue
            windows.append(_X11Window(
                classes=tuple(window.get_wm_class() or ()),
                title=self._title(window),
                pid=int(pid.value[0]),
            ))
        return windows

    def _title(self, window) -> str:
        from Xlib import X

        prop = window.get_full_property(self._atoms["name"], X.AnyPropertyType)
        if prop is not None and prop.value:
            value = prop.value
            return (value.decode("utf-8", "replace") if isinstance(value, bytes)
                    else str(value))
        return window.get_wm_name() or ""


# ── process table ──────────────────────────────────────────────────────────

def _named_processes(processes: dict[str, set[int]], app_id: str) -> frozenset[int]:
    """Every process running under *app_id*.

    A reverse-DNS app_id (``com.system76.CosmicTerm``) is also tried by its last
    segment, which is what such a client's binary is normally called.
    """
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
        # comm is kernel-truncated to 15 characters, and a truncated name matches
        # the wrong app_id outright: cosmic-settings-daemon arrives as
        # "cosmic-settings". The untruncated sources below cover those.
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
    """Fold the spelling differences between an app_id and a binary name —
    ``CosmicTerm`` and ``cosmic-term`` name the same program."""
    return "".join(c for c in name.lower() if c.isalnum())
