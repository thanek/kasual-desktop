"""Persisted scalar preferences — the file side of the preference ports.

Small user choices that aren't part of the app catalog (whose ``.desktop`` files
are handled in :mod:`app_config`) live in a single JSON file under the same
cross-platform config root, as plain key→value JSON.
"""

import json
import logging
from pathlib import Path

from domain.audio.kasual_output import BorrowedOutputMemory, OutputPreference
from domain.audio.output import AudioOutput
from domain.display.display import DisplayPreference
from domain.preflight.hud import HudSetupMemory
from domain.shell.background_hint import BackgroundHintMemory
from domain.system.actions import POWER_ACTIONS, SLEEP
from domain.system.power_preference import PowerPreference

from infrastructure.common.catalog.app_config import config_root

logger = logging.getLogger(__name__)

_POWER_DEFAULT_KEY = "power_default"
_BACKGROUND_HINT_KEY = "background_hint_shown"
_HUD_SETUP_KEY = "hud_setup_shown"
_DISPLAY_KEY = "display"
_AUDIO_OUTPUT_KEY = "audio_output"
_AUDIO_OUTPUT_LABEL_KEY = "audio_output_label"
_BORROWED_AUDIO_OUTPUT_KEY = "audio_output_borrowed_from_system"


def _preferences_file() -> Path:
    return config_root() / "preferences.json"


def _read() -> dict:
    try:
        return json.loads(_preferences_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Missing or corrupt file → no stored preferences yet.
        return {}


def _write(data: dict) -> None:
    path = _preferences_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot write preferences %s: %s", path, exc)


class DesktopPowerPreference(PowerPreference):
    """Persists the default power action in ``<config>/preferences.json``."""

    def default(self) -> str:
        value = _read().get(_POWER_DEFAULT_KEY)
        # Guard against a hand-edited or stale value naming a non-power action.
        return value if value in POWER_ACTIONS else SLEEP

    def set_default(self, action_key: str) -> None:
        if action_key not in POWER_ACTIONS:
            logger.warning("Ignoring non-power default: %r", action_key)
            return
        data = _read()
        data[_POWER_DEFAULT_KEY] = action_key
        _write(data)


class DesktopBackgroundHintMemory(BackgroundHintMemory):
    def was_ever_shown(self) -> bool:
        return bool(_read().get(_BACKGROUND_HINT_KEY))

    def mark_shown(self) -> None:
        data = _read()
        data[_BACKGROUND_HINT_KEY] = True
        _write(data)


class DesktopHudSetupMemory(HudSetupMemory):
    def was_ever_shown(self) -> bool:
        return bool(_read().get(_HUD_SETUP_KEY))

    def mark_shown(self) -> None:
        data = _read()
        data[_HUD_SETUP_KEY] = True
        _write(data)


class DesktopDisplayPreference(DisplayPreference):
    def preferred(self) -> str | None:
        value = _read().get(_DISPLAY_KEY)
        return value if isinstance(value, str) and value else None

    def set_preferred(self, display_id: str | None) -> None:
        data = _read()
        if display_id is None:
            data.pop(_DISPLAY_KEY, None)
        else:
            data[_DISPLAY_KEY] = display_id
        _write(data)


class DesktopOutputPreference(OutputPreference):
    def preferred(self) -> AudioOutput | None:
        data = _read()
        output_id = data.get(_AUDIO_OUTPUT_KEY)
        if not isinstance(output_id, str) or not output_id:
            return None
        label = data.get(_AUDIO_OUTPUT_LABEL_KEY)
        return AudioOutput(output_id, label if isinstance(label, str) and label else output_id)

    def set_preferred(self, output: AudioOutput | None) -> None:
        data = _read()
        if output is None:
            data.pop(_AUDIO_OUTPUT_KEY, None)
            data.pop(_AUDIO_OUTPUT_LABEL_KEY, None)
        else:
            data[_AUDIO_OUTPUT_KEY] = output.id
            data[_AUDIO_OUTPUT_LABEL_KEY] = output.label
        _write(data)


class DesktopBorrowedOutputMemory(BorrowedOutputMemory):
    def borrowed_from_system(self) -> str | None:
        value = _read().get(_BORROWED_AUDIO_OUTPUT_KEY)
        return value if isinstance(value, str) and value else None

    def remember_borrowed_from_system(self, output_id: str | None) -> None:
        data = _read()
        if output_id is None:
            data.pop(_BORROWED_AUDIO_OUTPUT_KEY, None)
        else:
            data[_BORROWED_AUDIO_OUTPUT_KEY] = output_id
        _write(data)
