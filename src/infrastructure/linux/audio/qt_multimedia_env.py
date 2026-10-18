import os
from collections.abc import MutableMapping

_SKIP_CUDA_PROBE_THAT_HANGS_SUSPEND = {
    "QT_FFMPEG_DECODING_HW_DEVICE_TYPES": "",
    "QT_FFMPEG_ENCODING_HW_DEVICE_TYPES": "",
}
_AVOID_NATIVE_PIPEWIRE_BACKEND_CRASHING_ON_DEVICE_CHANGES = {
    "QT_AUDIO_BACKEND": "pulseaudio",
}
_OVERRIDES = _SKIP_CUDA_PROBE_THAT_HANGS_SUSPEND | _AVOID_NATIVE_PIPEWIRE_BACKEND_CRASHING_ON_DEVICE_CHANGES


def apply_qt_multimedia_overrides() -> None:
    os.environ.update(_OVERRIDES)


def drop_qt_multimedia_overrides(env: MutableMapping[str, str]) -> None:
    for name in _OVERRIDES:
        env.pop(name, None)
