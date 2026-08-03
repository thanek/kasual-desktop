"""The ports the DRM-readiness use-case drives — implemented in infrastructure."""

from collections.abc import Callable
from typing import Protocol

from domain.drm.plan import MachineProfile, ReadinessReport


class SystemFacts(Protocol):
    """Answers the predicates a recipe's steps are written against."""

    def machine(self) -> MachineProfile: ...

    def has_command(self, name: str) -> bool: ...

    def path_exists(self, pattern: str) -> bool:
        """True when the glob *pattern* matches at least one file."""
        ...

    def cdm_path(self) -> str | None:
        """The Widevine module for this architecture, or None when absent."""
        ...


class PlaybackProbe(Protocol):
    """Confirms the CDM actually loads, which its presence on disk does not."""

    def verify(self, on_result: Callable[[bool], None]) -> None:
        """The outcome reaches *on_result* tens of seconds later at worst."""
        ...

    def cancel(self) -> None:
        """Drops a check in flight — its ``on_result`` is then never called."""
        ...


class DrmSetupView(Protocol):
    def present(
        self,
        report: ReadinessReport,
        on_recheck: Callable[[], ReadinessReport],
        on_done: Callable[[], None],
        probe: PlaybackProbe | None = None,
    ) -> None: ...
