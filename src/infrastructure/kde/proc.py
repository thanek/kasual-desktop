"""Tiny /proc readers — the infrastructure side of the process-tree walks.

The domain rules (``descends_from_launcher``, ``resolve_recall_trigger``) take
``parent_of``/``name_of`` as injected callables so they stay pure; these are the
Linux ``/proc`` implementations wired in at the edge.
"""

from __future__ import annotations


def parent_pid(pid: int) -> int | None:
    """Parent PID of *pid* from ``/proc/<pid>/status``, or None on failure."""
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return None


def process_name(pid: int) -> str | None:
    """Process name of *pid* from ``/proc/<pid>/comm`` (kernel-truncated to 15
    chars), or None on failure."""
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None
