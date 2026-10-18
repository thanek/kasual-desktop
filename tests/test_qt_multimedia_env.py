import os

from infrastructure.linux.audio.qt_multimedia_env import (
    apply_qt_multimedia_overrides,
    drop_qt_multimedia_overrides,
)


def test_sound_cues_avoid_the_native_pipewire_backend(monkeypatch):
    monkeypatch.setattr(os, "environ", {})
    apply_qt_multimedia_overrides()
    assert os.environ["QT_AUDIO_BACKEND"] == "pulseaudio"


def test_dropping_overrides_leaves_unrelated_env_alone():
    env = {"QT_AUDIO_BACKEND": "pulseaudio", "QT_FFMPEG_DECODING_HW_DEVICE_TYPES": "", "HOME": "/home/u"}
    drop_qt_multimedia_overrides(env)
    assert env == {"HOME": "/home/u"}
