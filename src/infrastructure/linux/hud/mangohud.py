"""MangoHudControl — the :class:`HudControl` port backed by MangoHud's config.

MangoHud reads ``~/.config/MangoHud/MangoHud.conf`` and hides its overlay when an
active (uncommented) ``no_display`` line is present. This adapter treats that
file as the HUD's on/off state — it is the one place that knows the config
format:

  - **available** ⟺ the config file exists; with no file the whole HUD feature is
    absent (the toggle never appears);
  - **enabled** ⟺ no active ``no_display`` line (a commented one doesn't count);
  - **enable** → comment out every active ``no_display`` line;
  - **disable** → uncomment an existing ``no_display`` line, or append one.

Reads happen live on each call, so creating or deleting the file between Home
Overlay opens is reflected without restarting Kasual.

The config alone never puts the overlay on screen: MangoHud's Vulkan layer is
*implicit*, gated on ``MANGOHUD=1``, so a game started without that variable loads
no layer at all and ``no_display`` has nothing to hide — hence ``launch_env``.

That environment reaches only what Kasual Desktop starts: a running Steam takes
``steam://rungameid/…`` over IPC and starts the game from its own. So
``is_attached`` asks the game's process, and :class:`MangoHudSession` the
session — the reading behind the setup card in :mod:`domain.preflight.hud`.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from domain.preflight.hud import HudEnvironment
from domain.system.hud import HudControl
from infrastructure.linux.proc import process_environ

logger = logging.getLogger(__name__)

_ENABLE_VAR  = "MANGOHUD"
_DISABLE_VAR = "DISABLE_MANGOHUD"
_OFF_VALUES  = ("", "0")

# An active (uncommented) ``no_display`` directive, optionally with a value
# (``no_display`` or ``no_display=1``). A leading ``#`` is not whitespace, so a
# commented line never matches.
_ACTIVE_NO_DISPLAY = re.compile(r"^\s*no_display\b")
# A commented-out ``no_display`` directive — what `enable` leaves behind and what
# `disable` revives in preference to appending a fresh line.
_COMMENTED_NO_DISPLAY = re.compile(r"^\s*#\s*no_display\b")

_DEFAULT_PATH = Path.home() / ".config" / "MangoHud" / "MangoHud.conf"


def _carries_hud(environ: Mapping[str, str]) -> bool:
    """Whether a process started with *environ* loads MangoHud's layer."""
    if _DISABLE_VAR in environ:
        return False
    return environ.get(_ENABLE_VAR, "") not in _OFF_VALUES


class MangoHudSession(HudEnvironment):
    """Read from Kasual Desktop's own environment: a session hands the same one to
    every process it starts."""

    def __init__(self, environ: Mapping[str, str] = os.environ) -> None:
        self._environ = environ

    def carried_by_session(self) -> bool:
        return _carries_hud(self._environ)


class MangoHudControl(HudControl):
    def __init__(
        self,
        config_path: Path = _DEFAULT_PATH,
        environ_of: Callable[[int], Mapping[str, str]] = process_environ,
    ) -> None:
        self._path = config_path
        self._environ_of = environ_of

    def is_available(self) -> bool:
        return self._path.is_file()

    def launch_env(self) -> Mapping[str, str]:
        return {_ENABLE_VAR: "1"}

    def is_attached(self, pid: int | None) -> bool:
        """Read from the environment *pid* was started with, not from the libraries
        it has mapped: a game that has not created its Vulkan device yet has mapped
        none, and the toggle would flicker while the game starts up."""
        if pid is None:
            return False
        return _carries_hud(self._environ_of(pid))

    def is_enabled(self) -> bool:
        # Absent config: nothing forces the HUD off, so it counts as enabled.
        return not any(_ACTIVE_NO_DISPLAY.match(line) for line in self._read())

    def enable(self) -> None:
        lines = self._read()
        commented = [
            "# " + line if _ACTIVE_NO_DISPLAY.match(line) else line
            for line in lines
        ]
        if commented != lines:
            self._write(commented)

    def disable(self) -> None:
        lines = self._read()
        if any(_ACTIVE_NO_DISPLAY.match(line) for line in lines):
            return  # already disabled
        for i, line in enumerate(lines):
            if _COMMENTED_NO_DISPLAY.match(line):
                lines[i] = re.sub(r"^(\s*)#\s*", r"\1", line)  # uncomment in place
                self._write(lines)
                return
        self._write([*lines, "no_display"])

    # ── File access ──────────────────────────────────────────────────────────

    def _read(self) -> list[str]:
        try:
            return self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

    def _write(self, lines: list[str]) -> None:
        try:
            self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.error("Could not write MangoHud config %s: %s", self._path, exc)
