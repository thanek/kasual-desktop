"""Kasual Desktop's sound switches, run in order off the GUI thread."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from domain.audio.kasual_output import KasualOutput, OutputPicker
from domain.audio.output import AudioOutput
from domain.shell.session_collaborators import SessionSound

logger = logging.getLogger(__name__)

Work = Callable[[], None]


class AudioWorker:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio-output")

    def run(self, work: Work) -> None:
        self._executor.submit(_logging_failures, work)

    def finish(self) -> None:
        self._executor.shutdown(wait=True)


def _logging_failures(work: Work) -> None:
    try:
        work()
    except Exception:
        logger.exception("Audio output switch failed")


class BackgroundKasualOutput(OutputPicker, SessionSound):
    def __init__(self, output: KasualOutput, worker: AudioWorker) -> None:
        self._output = output
        self._worker = worker

    def options(self) -> list[AudioOutput]:
        return self._output.options()

    def chosen(self) -> str | None:
        return self._output.chosen()

    def choose(self, output_id: str | None) -> None:
        self._worker.run(lambda: self._output.choose(output_id))

    def take_over(self) -> None:
        self._worker.run(self._output.take_over)

    def give_back(self) -> None:
        self._worker.run(self._output.give_back)

    def give_back_before_exit(self) -> None:
        self.give_back()
        self._worker.finish()
