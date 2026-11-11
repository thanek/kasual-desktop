"""Tests for KasualOutput."""

from domain.audio.kasual_output import KasualOutput
from domain.audio.output import AudioOutput
from domain.shared.choice import SYSTEM_DECIDES

SPEAKERS = AudioOutput("usb:speaker", "Speakers – USB Audio")
HDMI = AudioOutput("gpu:hdmi", "HDMI / DisplayPort – GB203")
HEADPHONES = AudioOutput("usb:headphones", "Headphones – USB Audio")
HDMI_UNPLUGGED = AudioOutput(HDMI.id, HDMI.label, connected=False)


class FakeOutputs:
    def __init__(self, outputs=(SPEAKERS, HDMI), active=SPEAKERS.id):
        self.outputs = list(outputs)
        self.playing = active
        self.activated: list[str] = []

    def available(self):
        return self.outputs

    def active(self):
        return self.playing

    def activate(self, output_id):
        self.activated.append(output_id)
        self.playing = output_id


class FakePreference:
    def __init__(self, output=None):
        self.output = output

    def preferred(self):
        return self.output

    def set_preferred(self, output):
        self.output = output


class FakeBorrowed:
    def __init__(self, output_id=None):
        self.output_id = output_id

    def borrowed_from_system(self):
        return self.output_id

    def remember_borrowed_from_system(self, output_id):
        self.output_id = output_id


class DevicesComingBack:
    def __init__(self, arrive=lambda: None):
        self._arrive = arrive
        self.waited_until_ready: list[bool] = []

    def wait_for(self, ready):
        if not ready():
            self._arrive()
        self.waited_until_ready.append(ready())


def _kasual(preferred=HDMI, outputs=None, borrowed=None, patience=None):
    outputs = outputs or FakeOutputs()
    borrowed = borrowed or FakeBorrowed()
    patience = patience or DevicesComingBack()
    preference = FakePreference(preferred)
    return KasualOutput(preference, outputs, borrowed, patience), outputs, borrowed, preference


class TestTakeOver:
    def test_switches_to_kasuals_output_and_remembers_the_systems(self):
        kasual, outputs, borrowed, _ = _kasual()
        kasual.take_over()
        assert outputs.playing == HDMI.id
        assert borrowed.output_id == SPEAKERS.id

    def test_leaves_the_sound_alone_when_the_system_decides(self):
        kasual, outputs, borrowed, _ = _kasual(preferred=None)
        kasual.take_over()
        assert outputs.activated == []
        assert borrowed.output_id is None

    def test_leaves_the_sound_alone_while_kasuals_output_is_unplugged(self):
        kasual, outputs, borrowed, _ = _kasual(outputs=FakeOutputs([SPEAKERS, HDMI_UNPLUGGED]))
        kasual.take_over()
        assert outputs.activated == []
        assert borrowed.output_id is None

    def test_keeps_an_earlier_loan_when_kasuals_output_already_plays(self):
        outputs = FakeOutputs(active=HDMI.id)
        kasual, outputs, borrowed, _ = _kasual(outputs=outputs,
                                               borrowed=FakeBorrowed(SPEAKERS.id))
        kasual.take_over()
        assert outputs.activated == []
        assert borrowed.output_id == SPEAKERS.id

    def test_a_fresh_take_over_forgets_a_stale_loan(self):
        outputs = FakeOutputs([SPEAKERS, HDMI, HEADPHONES], active=HEADPHONES.id)
        kasual, _, borrowed, _ = _kasual(outputs=outputs, borrowed=FakeBorrowed(SPEAKERS.id))
        kasual.take_over()
        assert borrowed.output_id == HEADPHONES.id


class TestGiveBack:
    def test_returns_the_systems_output(self):
        kasual, outputs, borrowed, _ = _kasual()
        kasual.take_over()
        kasual.give_back()
        assert outputs.playing == SPEAKERS.id
        assert borrowed.output_id is None

    def test_nothing_to_return_when_nothing_was_borrowed(self):
        kasual, outputs, _, _ = _kasual(outputs=FakeOutputs(active=HDMI.id))
        kasual.give_back()
        assert outputs.activated == []

    def test_respects_an_output_changed_by_hand_meanwhile(self):
        kasual, outputs, borrowed, _ = _kasual(
            outputs=FakeOutputs([SPEAKERS, HDMI, HEADPHONES]))
        kasual.take_over()
        outputs.playing = HEADPHONES.id
        kasual.give_back()
        assert outputs.playing == HEADPHONES.id
        assert borrowed.output_id is None

    def test_cannot_return_an_output_that_is_gone(self):
        kasual, outputs, borrowed, _ = _kasual()
        kasual.take_over()
        outputs.outputs = [HDMI]
        kasual.give_back()
        assert outputs.playing == HDMI.id
        assert borrowed.output_id is None

    def test_waits_for_the_systems_output_to_come_back_after_resume(self):
        outputs = FakeOutputs()

        def usb_audio_comes_back():
            outputs.outputs = [SPEAKERS, HDMI]
            outputs.playing = HDMI.id

        patience = DevicesComingBack(usb_audio_comes_back)
        kasual, _, borrowed, _ = _kasual(outputs=outputs, patience=patience)
        kasual.take_over()
        outputs.outputs = [HDMI]
        outputs.playing = None
        kasual.give_back()
        assert patience.waited_until_ready == [True]
        assert outputs.playing == SPEAKERS.id
        assert borrowed.output_id is None

    def test_returns_the_systems_output_when_kasuals_output_vanished(self):
        outputs = FakeOutputs([SPEAKERS, HDMI, HEADPHONES])
        kasual, _, borrowed, _ = _kasual(outputs=outputs)
        kasual.take_over()
        outputs.outputs = [SPEAKERS, HEADPHONES]
        outputs.playing = HEADPHONES.id
        kasual.give_back()
        assert outputs.playing == SPEAKERS.id

    def test_does_not_wait_when_nothing_was_borrowed(self):
        patience = DevicesComingBack()
        kasual, _, _, _ = _kasual(outputs=FakeOutputs(active=HDMI.id), patience=patience)
        kasual.give_back()
        assert patience.waited_until_ready == []

    def test_returns_a_loan_left_behind_by_an_earlier_run(self):
        kasual, outputs, _, _ = _kasual(outputs=FakeOutputs(active=HDMI.id),
                                        borrowed=FakeBorrowed(SPEAKERS.id))
        kasual.give_back()
        assert outputs.playing == SPEAKERS.id


class TestChoose:
    def test_remembers_the_pick_with_its_label(self):
        kasual, _, _, preference = _kasual(preferred=None)
        kasual.choose(HDMI.id)
        assert preference.output == AudioOutput(HDMI.id, HDMI.label)
        assert kasual.chosen() == HDMI.id

    def test_out_of_charge_only_remembers(self):
        kasual, outputs, _, _ = _kasual(preferred=None)
        kasual.choose(HDMI.id)
        assert outputs.activated == []

    def test_in_charge_switches_right_away(self):
        kasual, outputs, borrowed, _ = _kasual(preferred=None)
        kasual.take_over()
        kasual.choose(HDMI.id)
        assert outputs.playing == HDMI.id
        assert borrowed.output_id == SPEAKERS.id

    def test_switching_between_kasuals_outputs_keeps_the_systems_loan(self):
        outputs = FakeOutputs([SPEAKERS, HDMI, HEADPHONES])
        kasual, _, borrowed, _ = _kasual(outputs=outputs)
        kasual.take_over()
        kasual.choose(HEADPHONES.id)
        assert outputs.playing == HEADPHONES.id
        assert borrowed.output_id == SPEAKERS.id

    def test_handing_the_choice_to_the_system_returns_its_output(self):
        kasual, outputs, borrowed, _ = _kasual()
        kasual.take_over()
        kasual.choose(SYSTEM_DECIDES)
        assert outputs.playing == SPEAKERS.id
        assert borrowed.output_id is None
        assert kasual.chosen() is SYSTEM_DECIDES


class TestOptions:
    def test_offers_what_the_system_offers(self):
        kasual, _, _, _ = _kasual()
        assert kasual.options() == [SPEAKERS, HDMI]

    def test_a_remembered_output_that_is_unplugged_stays_on_the_list_by_name(self):
        kasual, _, _, _ = _kasual(outputs=FakeOutputs([SPEAKERS]))
        assert kasual.options() == [SPEAKERS, HDMI_UNPLUGGED]

    def test_nothing_to_offer_where_the_system_offers_nothing(self):
        kasual, _, _, _ = _kasual(outputs=FakeOutputs([], active=None))
        assert kasual.options() == []
