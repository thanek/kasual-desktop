"""Tests for the sound-cue adapter.

Two shapes matter. Resource ownership: a fixed set of players per cue, built once
and re-triggered — a player per *playback* opens an audio stream per playback, and
the cues are seconds long, so sweeping the tile bar stacks dozens of live streams
until the PulseAudio backend aborts the process. And the rule that keeps the cues
audible at all: a player is never rewound while it is still sounding, because
cutting one short damages it for good (measured, see the module docstring).
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
        self.device = None

    def stop(self) -> None:
        self.calls.append("stop")

    def play(self) -> None:
        self.calls.append("play")

    def setAudioDevice(self, device) -> None:   # noqa: N802 — Qt's spelling
        self.device = device


class _StubDevice:
    def __init__(self, description="Speakers", null=False) -> None:
        self._description = description
        self._null = null

    def isNull(self) -> bool:                   # noqa: N802 — Qt's spelling
        return self._null

    def description(self) -> str:
        return self._description


@pytest.fixture
def feedback(qapp):
    return SoundFeedback()


def _stub_voices(feedback, cue, count, length=2.0):
    """Give *cue* a ring of stub players, as init() would with real ones."""
    voices = [_StubEffect() for _ in range(count)]
    feedback._voices[cue] = voices
    feedback._free_at[cue] = [0.0] * count
    feedback._length[cue] = length
    return voices


class TestInit:
    def test_builds_players_for_every_bundled_cue(self, feedback):
        feedback.init()
        assert set(feedback._voices) == set(Cue)

    def test_each_cue_is_timed_from_its_own_wav(self, feedback):
        feedback.init()
        # The bundled cues are seconds long, not milliseconds; a length of zero
        # would let a player be rewound the moment after it started.
        assert all(0.1 < length < 10 for length in feedback._length.values())

    def test_a_cue_gets_a_whole_ring_of_players(self, feedback):
        feedback.init()
        assert all(len(voices) == feedback_module._VOICES
                   for voices in feedback._voices.values())

    def test_a_missing_file_is_skipped_not_fatal(self, feedback, tmp_path):
        with patch.object(feedback_module, "_SOUNDS_DIR", tmp_path):
            feedback.init()
        assert feedback._voices == {}


class TestOutputDevice:
    """Left alone, QSoundEffect plays into whichever device it picks first — on a
    machine with an HDMI output beside its speakers that is silence with nothing
    wrong anywhere. Every cue is pointed at the default output instead."""

    def test_every_player_plays_on_the_default_output(self, feedback):
        speakers = _StubDevice("Speakers")
        _stub_voices(feedback, Cue.CURSOR, 2)
        _stub_voices(feedback, Cue.SELECT, 2)
        with patch.object(feedback_module.QMediaDevices, "defaultAudioOutput",
                          return_value=speakers):
            feedback._follow_default_output()
        assert all(effect.device is speakers for effect in feedback._all_effects())

    def test_a_new_default_output_takes_the_cues_with_it(self, feedback):
        headphones = _StubDevice("Headphones")
        _stub_voices(feedback, Cue.CURSOR, 1)
        with patch.object(feedback_module.QMediaDevices, "defaultAudioOutput",
                          return_value=headphones):
            feedback._follow_default_output()
        assert feedback._voices[Cue.CURSOR][0].device is headphones

    def test_no_output_at_all_leaves_the_cues_where_they_are(self, feedback):
        _stub_voices(feedback, Cue.CURSOR, 1)
        with patch.object(feedback_module.QMediaDevices, "defaultAudioOutput",
                          return_value=_StubDevice(null=True)):
            feedback._follow_default_output()
        assert feedback._voices[Cue.CURSOR][0].device is None


class TestPlay:
    """The clock is driven rather than waited on: a player is held until the sound
    it is carrying has finished, which is a matter of when."""

    @staticmethod
    def _press(feedback, cue, at):
        with patch.object(feedback_module.time, "monotonic", return_value=at):
            feedback.play(cue)

    def test_retriggers_from_the_start(self, feedback):
        voices = _stub_voices(feedback, Cue.CURSOR, 1)
        self._press(feedback, Cue.CURSOR, 10.0)
        assert voices[0].calls == ["stop", "play"]

    def test_presses_in_a_row_sound_over_each_other(self, feedback):
        voices = _stub_voices(feedback, Cue.CURSOR, 3, length=2.0)
        for i in range(3):
            self._press(feedback, Cue.CURSOR, 10.0 + i * 0.3)
        assert [v.calls.count("play") for v in voices] == [1, 1, 1]

    def test_a_player_is_reused_once_its_sound_has_finished(self, feedback):
        voices = _stub_voices(feedback, Cue.CURSOR, 1, length=2.0)
        self._press(feedback, Cue.CURSOR, 10.0)
        self._press(feedback, Cue.CURSOR, 30.0)
        assert voices[0].calls.count("play") == 2

    def test_the_ring_is_walked_before_anything_is_reused(self, feedback):
        voices = _stub_voices(feedback, Cue.CURSOR, 3, length=2.0)
        for i in range(3):
            self._press(feedback, Cue.CURSOR, 10.0 + i * 5)
        assert [v.calls.count("play") for v in voices] == [1, 1, 1]

    def test_unknown_cue_is_a_no_op(self, feedback):
        feedback.play(Cue.CURSOR)   # never init()ed — must not raise

    def test_each_cue_uses_its_own_players(self, feedback):
        cursor = _stub_voices(feedback, Cue.CURSOR, 1)
        select = _stub_voices(feedback, Cue.SELECT, 1)
        self._press(feedback, Cue.SELECT, 10.0)
        assert (cursor[0].calls, select[0].calls) == ([], ["stop", "play"])


class TestSoundingPlayersAreLeftAlone:
    """Rewinding a player that is still sounding damages it, and the damage
    accumulates until the cues disappear altogether. A press with nothing free is
    dropped instead — the one thing that measurably kept them audible."""

    def test_no_player_is_rewound_while_it_is_still_sounding(self, feedback):
        voices = _stub_voices(feedback, Cue.CURSOR, 3, length=2.0)
        for step in range(6):
            TestPlay._press(feedback, Cue.CURSOR, 10.0 + step * 0.1)
        assert all(v.calls.count("play") <= 1 for v in voices)

    def test_a_press_with_every_player_busy_goes_unheard(self, feedback):
        voices = _stub_voices(feedback, Cue.CURSOR, 2, length=2.0)
        for step in range(5):
            TestPlay._press(feedback, Cue.CURSOR, 10.0 + step * 0.1)
        assert sum(v.calls.count("play") for v in voices) == 2

    def test_a_held_key_still_ticks_along(self, feedback):
        voices = _stub_voices(feedback, Cue.CURSOR, 8, length=2.0)
        for step in range(150):                      # five seconds at 30 a second
            TestPlay._press(feedback, Cue.CURSOR, 10.0 + step * 0.033)
        played = sum(v.calls.count("play") for v in voices)
        assert 8 <= played <= 20                     # a tick or two a second, not 150

    def test_the_tail_beyond_the_wav_is_respected(self, feedback):
        # The sound is still on its way out of the audio server after the samples
        # run out; a player rewound in that moment is being cut short too.
        voices = _stub_voices(feedback, Cue.CURSOR, 1, length=2.0)
        TestPlay._press(feedback, Cue.CURSOR, 10.0)
        TestPlay._press(feedback, Cue.CURSOR, 10.0 + 2.0 + feedback_module._TAIL_S / 2)
        assert voices[0].calls.count("play") == 1

    def test_another_cue_is_not_held_back_by_the_cursor(self, feedback):
        cursor = _stub_voices(feedback, Cue.CURSOR, 3)
        select = _stub_voices(feedback, Cue.SELECT, 3)
        TestPlay._press(feedback, Cue.CURSOR, 10.0)
        TestPlay._press(feedback, Cue.SELECT, 10.01)
        assert (sum(v.calls.count("play") for v in cursor),
                sum(v.calls.count("play") for v in select)) == (1, 1)
