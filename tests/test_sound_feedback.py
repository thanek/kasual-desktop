"""Tests for the sound-cue adapter.

The shape that matters is resource ownership: one player per cue, built once and
re-triggered. A player per *playback* opens an audio stream per playback, and the
cues are seconds long — sweeping the tile bar then stacks dozens of live streams
until the PulseAudio backend aborts the process.
"""

from unittest.mock import patch

import pytest

from domain.shared.feedback import Cue
from infrastructure.common.audio import feedback as feedback_module
from infrastructure.common.audio.feedback import SoundFeedback


@pytest.fixture(autouse=True)
def silence_sounds():
    """Overrides conftest's global mute: play() is what these tests are about.
    Nothing reaches a device anyway — the players here are stubs."""
    yield


class _StubEffect:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def stop(self) -> None:
        self.calls.append("stop")

    def play(self) -> None:
        self.calls.append("play")


@pytest.fixture
def feedback(qapp):
    return SoundFeedback()


class TestInit:
    def test_builds_one_player_per_bundled_cue(self, feedback):
        feedback.init()
        assert set(feedback._effects) == set(Cue)

    def test_a_missing_file_is_skipped_not_fatal(self, feedback, tmp_path):
        with patch.object(feedback_module, "_SOUNDS_DIR", tmp_path):
            feedback.init()
        assert feedback._effects == {}


class TestPlay:
    def test_retriggers_from_the_start(self, feedback):
        stub = _StubEffect()
        feedback._effects[Cue.CURSOR] = stub
        feedback.play(Cue.CURSOR)
        assert stub.calls == ["stop", "play"]

    def test_repeated_cues_reuse_the_same_player(self, feedback):
        stub = _StubEffect()
        feedback._effects[Cue.CURSOR] = stub
        for _ in range(5):
            feedback.play(Cue.CURSOR)
        assert stub.calls == ["stop", "play"] * 5
        assert feedback._effects[Cue.CURSOR] is stub

    def test_unknown_cue_is_a_no_op(self, feedback):
        feedback.play(Cue.CURSOR)   # never init()ed — must not raise

    def test_each_cue_uses_its_own_player(self, feedback):
        cursor, select = _StubEffect(), _StubEffect()
        feedback._effects[Cue.CURSOR] = cursor
        feedback._effects[Cue.SELECT] = select
        feedback.play(Cue.SELECT)
        assert (cursor.calls, select.calls) == ([], ["stop", "play"])
