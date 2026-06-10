"""The process-management port: launch / track / terminate the configured apps."""

from collections.abc import Mapping, Sequence
from typing import Protocol


class ProcessManager(Protocol):
    """Launch / track / terminate the configured apps by index (AppManager)."""

    def is_running(self, idx: int | None = None) -> bool: ...
    def launch(
        self,
        idx: int,
        command: str,
        args: Sequence[object] = (),
        env: Mapping[str, str] | None = None,
    ) -> bool: ...
    def running_pid(self, idx: int) -> int | None: ...
    def all_running_pids(self) -> list[int]: ...
    def terminate(self, idx: int) -> None: ...
