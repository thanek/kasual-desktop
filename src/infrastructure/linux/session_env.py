"""What the session hands to everything it starts, as it stands right now.

The systemd user manager rebuilds this block from ``~/.config/environment.d`` on
``daemon-reload``, so it moves while a running process's own environment — a
snapshot taken when it started — cannot.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Iterator

logger = logging.getLogger(__name__)

_SHOW_ENVIRONMENT = ("systemctl", "--user", "show-environment")
_GIVE_UP_AFTER_S = 5


def session_environ() -> dict[str, str]:
    try:
        block = subprocess.run(
            _SHOW_ENVIRONMENT,
            capture_output=True,
            text=True,
            timeout=_GIVE_UP_AFTER_S,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("Could not read the session's environment: %s", exc)
        return {}
    return dict(_assignments(block))


def _assignments(block: str) -> Iterator[tuple[str, str]]:
    for line in block.splitlines():
        name, assigned, value = line.partition("=")
        if assigned:
            yield name, value
