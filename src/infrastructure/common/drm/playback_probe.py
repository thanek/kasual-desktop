"""PlaybackProbe backed by Qt WebEngine's Widevine key-system access.

A wrong page size or libc makes the module refuse to load, and Netflix surfaces
that only as an opaque playback error.
"""

import logging
import subprocess
import sys
from pathlib import Path

from domain.drm.ports import PlaybackProbe, SystemFacts

logger = logging.getLogger(__name__)

_PROBE_SCRIPT = Path(__file__).with_name("eme_probe.py")
_TIMEOUT_S = 45.0


class QtWebEnginePlaybackProbe(PlaybackProbe):
    def __init__(self, facts: SystemFacts) -> None:
        self._facts = facts

    def can_play_protected(self) -> bool:
        cdm = self._facts.cdm_path()
        if cdm is None:
            return False
        try:
            result = subprocess.run(
                [sys.executable, str(_PROBE_SCRIPT), cdm],
                timeout=_TIMEOUT_S, capture_output=True, text=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("Widevine playback probe failed to run: %s", exc)
            return False
        if result.returncode != 0:
            logger.info("Widevine playback probe rejected %s: %s",
                        cdm, result.stderr.strip())
        return result.returncode == 0
