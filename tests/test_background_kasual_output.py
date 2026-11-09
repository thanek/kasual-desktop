"""Tests for BackgroundKasualOutput."""

import threading

from infrastructure.linux.audio.background import AudioWorker, BackgroundKasualOutput


class RecordingOutput:
    def __init__(self):
        self.steps: list[tuple[str, str]] = []

    def options(self): return []
    def chosen(self): return None
    def choose(self, output_id): self._record(f"choose {output_id}")
    def take_over(self): self._record("take_over")
    def give_back(self): self._record("give_back")

    def _record(self, step):
        self.steps.append((step, threading.current_thread().name))


def test_runs_every_switch_in_order_off_the_calling_thread():
    output = RecordingOutput()
    background = BackgroundKasualOutput(output, AudioWorker())
    background.take_over()
    background.choose("hdmi")
    background.give_back_before_exit()
    assert [step for step, _ in output.steps] == ["take_over", "choose hdmi", "give_back"]
    assert all(thread != threading.current_thread().name for _, thread in output.steps)


def test_a_failing_switch_does_not_stop_the_next():
    output = RecordingOutput()
    worker = AudioWorker()
    worker.run(lambda: 1 / 0)
    BackgroundKasualOutput(output, worker).give_back_before_exit()
    assert [step for step, _ in output.steps] == ["give_back"]
