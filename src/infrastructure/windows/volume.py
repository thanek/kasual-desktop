"""Windows master-volume control (the VolumeControl port) via Core Audio / pycaw.

Maps the domain ``Volume`` (0–100) to the endpoint's 0.0–1.0 scalar. The
IAudioEndpointVolume COM object is cached and re-acquired if a call fails (e.g.
the default output device changed). All calls happen on the GUI thread, where
comtypes has COM initialised.
"""

import logging

from domain.system.volume import Volume, VolumeControl

logger = logging.getLogger(__name__)


class WindowsVolumeControl(VolumeControl):
    def __init__(self) -> None:
        self._endpoint = None

    def _ep(self):
        if self._endpoint is None:
            from pycaw.pycaw import AudioUtilities
            self._endpoint = AudioUtilities.GetSpeakers().EndpointVolume
        return self._endpoint

    def get(self) -> Volume:
        try:
            return Volume(round(self._ep().GetMasterVolumeLevelScalar() * 100))
        except Exception as exc:
            logger.warning("Volume get failed: %s", exc)
            self._endpoint = None
            return Volume(Volume.DEFAULT)

    def set(self, volume: Volume) -> None:
        try:
            self._ep().SetMasterVolumeLevelScalar(volume.value / 100.0, None)
        except Exception as exc:
            logger.warning("Volume set failed, retrying once: %s", exc)
            self._endpoint = None
            try:
                self._ep().SetMasterVolumeLevelScalar(volume.value / 100.0, None)
            except Exception as exc2:
                logger.error("Volume set failed: %s", exc2)
