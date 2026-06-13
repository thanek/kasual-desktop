"""VolumeControl adapter over ``pactl`` (PulseAudio / PipeWire)."""

import logging
import subprocess

from domain.system.volume import Volume, VolumeControl

logger = logging.getLogger(__name__)

_SINK = "@DEFAULT_SINK@"


class PactlVolumeControl(VolumeControl):
    """Implements the VolumeControl port for the default sink via ``pactl``."""

    def get(self) -> Volume:
        try:
            out = subprocess.check_output(
                ["pactl", "get-sink-volume", _SINK],
                text=True, stderr=subprocess.DEVNULL,
            )
            # e.g. "Volume: front-left: 52428 / 80% / ..."
            for part in out.split():
                if part.endswith("%"):
                    return Volume(int(part.rstrip("%")))
        except Exception:
            pass
        return Volume(Volume.DEFAULT)

    def set(self, volume: Volume) -> None:
        try:
            subprocess.Popen(
                ["pactl", "set-sink-volume", _SINK, f"{volume.value}%"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.error("Error during volume setting: %s", exc)
