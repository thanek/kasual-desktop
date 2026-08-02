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

    def can_play_protected(self) -> bool: ...


class DrmSetupView(Protocol):
    def present(
        self,
        report: ReadinessReport,
        on_recheck: Callable[[], ReadinessReport],
        on_done: Callable[[], None],
        on_verify: Callable[[], bool] | None = None,
    ) -> None:
        """``on_verify`` blocks for seconds, so a view must let a repaint
        through before calling it."""
        ...
