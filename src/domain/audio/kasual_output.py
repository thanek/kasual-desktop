"""Kasual Desktop's sound output, borrowed from the system while it is in charge."""

from typing import Protocol

from domain.audio.output import AudioOutput, AudioOutputs
from domain.shared.choice import SYSTEM_DECIDES, Choice, remembered_but_absent, system_first_choices

OutputChoice = Choice[str | None]


class OutputPreference(Protocol):
    def preferred(self) -> AudioOutput | None: ...
    def set_preferred(self, output: AudioOutput | None) -> None: ...


class BorrowedOutputMemory(Protocol):
    def borrowed_from_system(self) -> str | None: ...
    def remember_borrowed_from_system(self, output_id: str | None) -> None: ...


class OutputPicker(Protocol):
    def options(self) -> list[AudioOutput]: ...
    def chosen(self) -> str | None: ...
    def choose(self, output_id: str | None) -> None: ...


def output_choices(picker: OutputPicker) -> list[OutputChoice]:
    return system_first_choices(picker.options(), picker.chosen())


class KasualOutput(OutputPicker):
    def __init__(
        self,
        preference: OutputPreference,
        outputs: AudioOutputs,
        borrowed: BorrowedOutputMemory,
    ) -> None:
        self._preference = preference
        self._outputs = outputs
        self._borrowed = borrowed
        self._in_charge = False

    def options(self) -> list[AudioOutput]:
        available = self._outputs.available()
        if not available:
            return []
        preferred = self._preference.preferred()
        if remembered_but_absent(available, self.chosen()):
            return [*available, AudioOutput(preferred.id, preferred.label, connected=False)]
        return available

    def chosen(self) -> str | None:
        preferred = self._preference.preferred()
        return SYSTEM_DECIDES if preferred is None else preferred.id

    def choose(self, output_id: str | None) -> None:
        playing_for_kasual = self.chosen()
        self._preference.set_preferred(self._known_output(output_id))
        if not self._in_charge:
            return
        now_chosen = self.chosen()
        if now_chosen is SYSTEM_DECIDES:
            self._give_back_unless_changed_since(playing_for_kasual)
        else:
            self._switch_to(now_chosen, keep_what_was_borrowed=True)

    def take_over(self) -> None:
        self._in_charge = True
        preferred = self.chosen()
        if preferred is not SYSTEM_DECIDES:
            self._switch_to(preferred, keep_what_was_borrowed=False)

    def give_back(self) -> None:
        self._in_charge = False
        self._give_back_unless_changed_since(self.chosen())

    def _switch_to(self, output_id: str, *, keep_what_was_borrowed: bool) -> None:
        if not self._is_connected(output_id):
            return
        current = self._outputs.active()
        if current == output_id:
            return
        already_borrowed = self._borrowed.borrowed_from_system() is not None
        if current is not None and not (keep_what_was_borrowed and already_borrowed):
            self._borrowed.remember_borrowed_from_system(current)
        self._outputs.activate(output_id)

    def _give_back_unless_changed_since(self, playing_for_kasual: str | None) -> None:
        borrowed = self._borrowed.borrowed_from_system()
        if borrowed is None:
            return
        self._borrowed.remember_borrowed_from_system(None)
        changed_by_hand = self._outputs.active() != playing_for_kasual
        if changed_by_hand or not self._is_connected(borrowed):
            return
        self._outputs.activate(borrowed)

    def _known_output(self, output_id: str | None) -> AudioOutput | None:
        found = next((output for output in self._outputs.available()
                      if output.id == output_id), None)
        if found is None:
            return None
        return AudioOutput(found.id, found.label)

    def _is_connected(self, output_id: str) -> bool:
        return any(output.id == output_id and output.connected
                   for output in self._outputs.available())
