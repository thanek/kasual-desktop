"""Shared skeletons for the wlroots window managers.

Sway (``swaymsg``) and Hyprland (``hyprctl``) both expose the window list and the
control operations over a JSON-speaking CLI, so :class:`WlrootsWindowManager`
narrows the snapshot-based :class:`PollingWindowManager` to that transport; each
subclass supplies only the CLI vocabulary and the window mapping. Compositors
here without such a CLI (labwc, wayfire) build on the plain
:class:`PollingWindowManager` and speak Wayland instead.
"""

from __future__ import annotations

import json
import logging
import subprocess

from infrastructure.linux.wm.base import PollingWindowManager

logger = logging.getLogger(__name__)

_CLI_TIMEOUT_S = 2.0


class WlrootsWindowManager(PollingWindowManager):
    """Polling window manager over a compositor's JSON IPC CLI. Subclasses
    implement ``_enum_windows`` and the imperative operations in that
    compositor's IPC."""

    def _run(self, args: list[str]) -> None:
        """Fire-and-forget CLI command; failures degrade to a logged warning."""
        try:
            subprocess.run(
                args, timeout=_CLI_TIMEOUT_S, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("%s failed: %s", args[0], exc)

    def _run_json(self, args: list[str]):
        """Run a CLI query and parse its JSON output, or None on any failure."""
        try:
            out = subprocess.run(
                args, timeout=_CLI_TIMEOUT_S, check=True,
                capture_output=True, text=True,
            ).stdout
            return json.loads(out)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            logger.warning("%s query failed: %s", args[0], exc)
            return None
