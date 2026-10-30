"""The devices sound can play through, the port that lists and switches them,
and how they are offered to the user to pick from."""

from dataclasses import dataclass
from typing import Protocol

from domain.shared.choice import Choice, connection_aware_label

OutputChoice = Choice[str]


@dataclass(frozen=True)
class AudioOutput:
    id: str
    label: str
    connected: bool = True


class AudioOutputs(Protocol):
    def available(self) -> list[AudioOutput]: ...
    def active(self) -> str | None: ...
    def activate(self, output_id: str) -> None: ...


def active_output_label(outputs: AudioOutputs) -> str | None:
    active = outputs.active()
    return next((output.label for output in outputs.available() if output.id == active), None)


def output_choices(outputs: AudioOutputs) -> list[OutputChoice]:
    active = outputs.active()
    return [
        OutputChoice(
            connection_aware_label(output.label, output.connected), output.id,
            pickable=output.connected, chosen=output.id == active,
        )
        for output in outputs.available()
    ]
