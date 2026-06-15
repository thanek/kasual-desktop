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
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from domain.system.hud import HudControl

logger = logging.getLogger(__name__)

# An active (uncommented) ``no_display`` directive, optionally with a value
# (``no_display`` or ``no_display=1``). A leading ``#`` is not whitespace, so a
# commented line never matches.
_ACTIVE_NO_DISPLAY = re.compile(r"^\s*no_display\b")
# A commented-out ``no_display`` directive — what `enable` leaves behind and what
# `disable` revives in preference to appending a fresh line.
_COMMENTED_NO_DISPLAY = re.compile(r"^\s*#\s*no_display\b")

_DEFAULT_PATH = Path.home() / ".config" / "MangoHud" / "MangoHud.conf"


class MangoHudControl(HudControl):
    def __init__(self, config_path: Path = _DEFAULT_PATH) -> None:
        self._path = config_path

    def is_available(self) -> bool:
        return self._path.is_file()

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
