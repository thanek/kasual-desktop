"""ExtensionProbe/ExtensionActivator for the Kasual Helper GNOME Shell extension.

The bus ping is definitive only when the extension is answering; it is silent for
installed-but-disabled, freshly-installed and not-installed alike. The
`gnome-extensions` CLI tells those apart: it answers from GNOME Shell's in-memory
extension list, which is built when the session starts. So a directory the CLI
does not know about, yet which exists on disk, is one that landed there after
login — Wayland cannot reload the Shell, so only a re-login makes it enablable.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from domain.preflight.extension import (
    ExtensionActivator, ExtensionProbe, ExtensionState,
)
from infrastructure.gnome.helper import EXTENSION_UUID, helper_present

logger = logging.getLogger(__name__)

_TIMEOUT_S = 2.0
_EXTENSION_DIRS = (
    Path.home() / ".local" / "share" / "gnome-shell" / "extensions",
    Path("/usr/share/gnome-shell/extensions"),
    Path("/usr/local/share/gnome-shell/extensions"),
)


def _run(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args, timeout=_TIMEOUT_S, capture_output=True, text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("%s failed: %s", args[0], exc)
        return None


class GnomeExtensionProbe(ExtensionProbe):
    def state(self) -> ExtensionState:
        if helper_present():
            return ExtensionState.READY
        known = self._shell_knows()
        if known is True:
            return ExtensionState.DISABLED
        if not self._on_disk():
            return ExtensionState.ABSENT
        return ExtensionState.DISABLED if known is None else ExtensionState.UNLOADED

    def _shell_knows(self) -> bool | None:
        """Whether GNOME Shell has the extension in its list — None if unanswerable."""
        result = _run("gnome-extensions", "info", EXTENSION_UUID)
        return None if result is None else result.returncode == 0

    def _on_disk(self) -> bool:
        return any(
            (base / EXTENSION_UUID / "metadata.json").is_file()
            for base in _EXTENSION_DIRS
        )


class GnomeExtensionActivator(ExtensionActivator):
    _POLL_ATTEMPTS = 15
    _POLL_INTERVAL_S = 0.2

    def enable(self) -> bool:
        _run("gsettings", "set", "org.gnome.shell", "disable-user-extensions", "false")
        result = _run("gnome-extensions", "enable", EXTENSION_UUID)
        if result is None or result.returncode != 0:
            detail = result.stderr.strip() if result else "command unavailable"
            logger.warning("Enabling %s failed: %s", EXTENSION_UUID, detail)
            return False
        return self._await_ready()

    def _await_ready(self) -> bool:
        for _ in range(self._POLL_ATTEMPTS):
            if helper_present():
                return True
            time.sleep(self._POLL_INTERVAL_S)
        return False
