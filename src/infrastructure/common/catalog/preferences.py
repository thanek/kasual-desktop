"""Persisted scalar preferences — the file side of the preference ports.

Small user choices that aren't part of the app catalog (whose ``.desktop`` files
are handled in :mod:`app_config`) live in a single JSON file under the same
cross-platform config root. Currently just the default power action; the store is
a plain key→value JSON so further scalars can join it without a new file each.
"""

import json
import logging
from pathlib import Path

from domain.system.actions import POWER_ACTIONS, SLEEP
from domain.system.power_preference import PowerPreference

from infrastructure.common.catalog.app_config import config_root

logger = logging.getLogger(__name__)

_POWER_DEFAULT_KEY = "power_default"


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
