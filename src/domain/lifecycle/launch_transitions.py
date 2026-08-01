"""The screen hand-off around a launch: hide, return, and ceded depth."""

from collections.abc import Callable
from dataclasses import dataclass

from domain.lifecycle.cede_depth import CedeDepth
from domain.lifecycle.launch_hide import LaunchHide
from domain.lifecycle.launch_show import LaunchShow
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.window_manager import WindowManager

HideFactory = Callable[
    [WindowManager, ProcessManager, Callable[[], None], Callable[[], None]], LaunchHide]
ShowFactory = Callable[[WindowManager, ProcessManager, Callable[[], None]], LaunchShow]
CedeDepthFactory = Callable[
    [WindowManager, ProcessManager, Callable[[bool], None]], CedeDepth]


class _ImmediateHide:
    """Fallback LaunchHide: cedes at once, without waiting for a window map."""

    def __init__(self, on_cede: Callable[[], None]) -> None:
        self._on_cede = on_cede

    @property
    def is_armed(self) -> bool:
        return False

    def arm(self, app) -> None:
        self._on_cede()

    def cancel(self) -> None:
        pass


class _NoLaunchShow:
    """Fallback LaunchShow: the Desktop returns when the app's process exits."""

    @property
    def is_armed(self) -> bool:
        return False

    @property
    def has_seen_window(self) -> bool:
        return False

    def arm(self, app) -> None:
        pass

    def cancel(self) -> None:
        pass


class _NoCedeDepth:
    """Fallback CedeDepth: where a cede is a plain unmap there is nothing to sink."""

    @property
    def is_armed(self) -> bool:
        return False

    def arm(self, app) -> None:
        pass

    def cancel(self) -> None:
        pass


@dataclass(frozen=True)
class LaunchTransitions:
    hide: LaunchHide
    show: LaunchShow
    cede_depth: CedeDepth

    @classmethod
    def build(
        cls,
        window_manager: WindowManager,
        process_manager: ProcessManager,
        *,
        on_cede: Callable[[], None],
        on_hide: Callable[[], None],
        on_show: Callable[[], None],
        on_sink: Callable[[bool], None],
        hide_factory: HideFactory | None = None,
        show_factory: ShowFactory | None = None,
        cede_depth_factory: CedeDepthFactory | None = None,
    ) -> "LaunchTransitions":
        return cls(
            hide=(hide_factory(window_manager, process_manager, on_cede, on_hide)
                  if hide_factory is not None else _ImmediateHide(on_cede)),
            show=(show_factory(window_manager, process_manager, on_show)
                  if show_factory is not None else _NoLaunchShow()),
            cede_depth=(cede_depth_factory(window_manager, process_manager, on_sink)
                        if cede_depth_factory is not None else _NoCedeDepth()),
        )
