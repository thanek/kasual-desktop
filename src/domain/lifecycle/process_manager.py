"""The process-management port: launch / track / terminate the configured apps,
and observe their lifecycle (started / finished / launch-failed)."""

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from domain.shared.event_emitter import Unsubscribe
from domain.lifecycle.app_events import AppStarted, AppFinished, AppLaunchFailed


class ProcessManager(Protocol):
    """Launch / track / terminate the configured apps by index, and observe
    their lifecycle (AppManager).

    The ``on_*`` methods are framework-agnostic pub/sub (returning an
    ``Unsubscribe`` token), so the lifecycle observes process events without the
    Desktop reaching for a concrete adapter's Qt signals. The implementation is
    responsible for delivering them on the GUI thread; this port says nothing
    about threading.
    """

    def is_running(self, idx: int | None = None) -> bool: ...
    def launch(
        self,
        idx: int,
        command: str,
        args: Sequence[object] = (),
        env: Mapping[str, str] | None = None,
    ) -> bool: ...
    def running_pid(self, idx: int) -> int | None: ...
    def running_idxs(self) -> list[int]: ...
    def all_running_pids(self) -> list[int]: ...
    def terminate(self, idx: int) -> None: ...

    def on_started(self, handler: Callable[[AppStarted], None]) -> Unsubscribe: ...
    def on_finished(self, handler: Callable[[AppFinished], None]) -> Unsubscribe: ...
    def on_launch_failed(
        self, handler: Callable[[AppLaunchFailed], None]
    ) -> Unsubscribe: ...
