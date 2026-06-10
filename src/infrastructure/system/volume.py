"""VolumeControl adapter over ``pactl`` (PulseAudio / PipeWire)."""

import logging
import subprocess

from ports import VolumeControl

logger = logging.getLogger(__name__)

_SINK    = "@DEFAULT_SINK@"
_DEFAULT = 50   # fallback when the sink volume can't be read


class PactlVolumeControl(VolumeControl):
    """Implements the VolumeControl port for the default sink via ``pactl``."""

    def get(self) -> int:
        try:
            out = subprocess.check_output(
                ["pactl", "get-sink-volume", _SINK],
                text=True, stderr=subprocess.DEVNULL,
            )
            # e.g. "Volume: front-left: 52428 / 80% / ..."
            for part in out.split():
                if part.endswith("%"):
                    return int(part.rstrip("%"))
        except Exception:
            pass
        return _DEFAULT

    def set(self, percent: int) -> None:
        percent = max(0, min(100, percent))
        try:
            subprocess.Popen(
                ["pactl", "set-sink-volume", _SINK, f"{percent}%"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.error("Error during volume setting: %s", exc)
