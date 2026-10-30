"""AudioOutputs for Windows, where switching the default endpoint needs an
undocumented COM interface: nothing is offered, so the picker stays hidden."""

from domain.audio.output import AudioOutput, AudioOutputs


class NoAudioOutputs(AudioOutputs):
    def available(self) -> list[AudioOutput]:
        return []

    def active(self) -> str | None:
        return None

    def activate(self, output_id: str) -> None:
        pass
