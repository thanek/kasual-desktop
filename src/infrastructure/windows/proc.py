"""psutil-backed process-tree readers — the Windows side of the process walks.

Mirror of :mod:`infrastructure.kde.proc`: the domain rules
(``descends_from_launcher``, ``resolve_recall_trigger``) take ``parent_of`` /
``name_of`` as injected callables so they stay pure; these are the Windows
implementations, wired in by ``windows_main``.

``process_name`` returns the executable basename lowercased with the ``.exe``
suffix stripped, so a Windows process name like ``steam.exe`` matches the bare
names in ``domain.catalog.window_rules.GAME_LAUNCHERS`` (which carry no
extension, mirroring Linux ``/proc/<pid>/comm``).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def parent_pid(pid: int) -> int | None:
    """Parent PID of *pid* via psutil, or None when it can't be read."""
    try:
        import psutil
        return psutil.Process(pid).ppid()
    except Exception:
        return None


def process_name(pid: int) -> str | None:
    """Executable name of *pid* via psutil — lowercased, ``.exe`` stripped — or
    None when it can't be read. Stripping the extension lets Windows names match
    the launcher set (``steam.exe`` → ``steam``)."""
    try:
        import psutil
        name = psutil.Process(pid).name()
    except Exception:
        return None
    if not name:
        return None
    name = name.lower()
    return name[:-4] if name.endswith(".exe") else name
