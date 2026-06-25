"""psutil-backed process-tree reader — parent-PID lookup for Windows.

Used for recall-trigger inheritance: a game window inherits its launcher
tile's BTN_MODE trigger by walking the process-parent chain via ``parent_pid``.
Game detection on Windows uses the RTSS shared-memory signal instead
(see ``infrastructure.windows.hud.rtss_shmem``), so no process-name reader
is needed here.
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
