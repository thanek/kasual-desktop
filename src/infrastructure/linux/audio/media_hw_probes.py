"""Keeps Qt Multimedia's FFmpeg backend from probing GPU decoders.

The probe initialises CUDA, and a process holding /dev/nvidia-uvm can hang in
the NVIDIA driver while exiting, which blocks system suspend.
"""

import os
from collections.abc import MutableMapping

_HW_DEVICE_PROBES = (
    "QT_FFMPEG_DECODING_HW_DEVICE_TYPES",
    "QT_FFMPEG_ENCODING_HW_DEVICE_TYPES",
)
_NO_DEVICES = ""


def disable_media_hw_probes() -> None:
    for probe in _HW_DEVICE_PROBES:
        os.environ[probe] = _NO_DEVICES


def restore_media_hw_probes(env: MutableMapping[str, str]) -> None:
    for probe in _HW_DEVICE_PROBES:
        env.pop(probe, None)
