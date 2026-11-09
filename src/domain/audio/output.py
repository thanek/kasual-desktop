"""The devices sound can play through, and the port that lists and switches them."""

from dataclasses import dataclass
from typing import Protocol


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
