"""MangoHudControl — the :class:`HudControl` port backed by MangoHud's config.

``~/.config/MangoHud/MangoHud.conf`` is the HUD's state and its absence the
absence of the feature. An active ``no_display`` line hides the overlay; while it
is shown, ``preset=N`` picks MangoHud's built-in detail level (1 FPS only …
4 detailed). MangoHud watches the file and re-reads both on every write, so a
running game follows the slider live. The user's own lines stay untouched and
still override what a preset sets.

The config alone never puts the overlay on screen: MangoHud's Vulkan layer is
*implicit*, gated on ``MANGOHUD=1``, which reaches only what Kasual Desktop starts
itself — hence ``launch_env``, ``is_attached`` and :class:`MangoHudSession`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from domain.preflight.hud import HudEnvironment
from domain.system.hud import HUD_OFF, HudControl, HudLevel
from infrastructure.linux.proc import process_environ
from infrastructure.linux.session_env import session_environ

logger = logging.getLogger(__name__)

_ENABLE_VAR  = "MANGOHUD"
_DISABLE_VAR = "DISABLE_MANGOHUD"
_OFF_VALUES  = ("", "0")

_ACTIVE_NO_DISPLAY = re.compile(r"^\s*no_display\b")
_COMMENTED_NO_DISPLAY = re.compile(r"^\s*#\s*no_display\b")
_ACTIVE_PRESET = re.compile(r"^\s*preset\s*=\s*(-?\d+)")

_MOST_DETAILED_PRESET = 4
_DETAIL_PRESETS = range(1, _MOST_DETAILED_PRESET + 1)
_PRESET_HIDING_THE_OVERLAY = 0

_DEFAULT_PATH = Path.home() / ".config" / "MangoHud" / "MangoHud.conf"


def _hides_the_overlay(line: str) -> bool:
    return bool(_ACTIVE_NO_DISPLAY.match(line))


def _uncommented(line: str) -> str:
    return re.sub(r"^(\s*)#\s*", r"\1", line)


def _active_preset(lines: list[str]) -> int | None:
    for line in lines:
        match = _ACTIVE_PRESET.match(line)
        if match:
            return int(match.group(1))
    return None


def _level_value(lines: list[str]) -> int:
    if any(_hides_the_overlay(line) for line in lines):
        return HUD_OFF
    preset = _active_preset(lines)
    if preset == _PRESET_HIDING_THE_OVERLAY:
        return HUD_OFF
    if preset in _DETAIL_PRESETS:
        return preset
    return _MOST_DETAILED_PRESET


def _overlay_hidden(lines: list[str]) -> list[str]:
    if any(_hides_the_overlay(line) for line in lines):
        return lines
    for i, line in enumerate(lines):
        if _COMMENTED_NO_DISPLAY.match(line):
            return [*lines[:i], _uncommented(line), *lines[i + 1:]]
    return [*lines, "no_display"]


def _overlay_shown(lines: list[str]) -> list[str]:
    return ["# " + line if _hides_the_overlay(line) else line for line in lines]


def _with_preset(lines: list[str], preset: int) -> list[str]:
    directive = f"preset={preset}"
    if _active_preset(lines) is None:
        return [*lines, directive]
    return [directive if _ACTIVE_PRESET.match(line) else line for line in lines]


def _carries_hud(environ: Mapping[str, str]) -> bool:
    """Whether a process started with *environ* loads MangoHud's layer."""
    if _DISABLE_VAR in environ:
        return False
    return environ.get(_ENABLE_VAR, "") not in _OFF_VALUES


class MangoHudSession(HudEnvironment):
    """The session's environment as it stands, not Kasual Desktop's own snapshot of
    it: the setup card's step moves the one and cannot move the other."""

    def __init__(
        self, environ: Callable[[], Mapping[str, str]] = session_environ,
    ) -> None:
        self._environ = environ

    def carried_by_session(self) -> bool:
        return _carries_hud(self._environ())


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
        """The environment, not the mapped libraries: a game yet to create its Vulkan
        device has mapped none, and the slider would flicker as it starts up."""
        if pid is None:
            return False
        return _carries_hud(self._environ_of(pid))

    def level(self) -> HudLevel:
        return HudLevel(_level_value(self._read()), _MOST_DETAILED_PRESET)

    def set_level(self, level: HudLevel) -> None:
        lines = self._read()
        if level.is_off:
            updated = _overlay_hidden(lines)
        else:
            updated = _with_preset(_overlay_shown(lines), level.value)
        if updated != lines:
            self._write(updated)

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
