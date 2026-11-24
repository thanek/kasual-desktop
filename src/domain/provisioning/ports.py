"""The ports the provisioning use-case drives — implemented in infrastructure."""

from collections.abc import Callable
from typing import Protocol

from domain.provisioning.candidate import CandidateApp
from domain.system.autostart import AutostartChoice


class AppProvisioning(Protocol):
    """Persists the chosen starter apps and records that provisioning happened."""

    def is_provisioned(self) -> bool:
        """True once the catalog has been provisioned (the marker exists)."""
        ...

    def provision(self, candidates: list[CandidateApp]) -> None:
        """Write each chosen app's ``.desktop`` file, then create the marker.

        Called with an empty list when the user provisions zero apps — the
        marker is still created so first-run does not re-trigger."""
        ...


class AppDiscovery(Protocol):
    """Detects whether a system command/app is available to launch."""

    def is_available(self, command: str) -> bool: ...

    def system_icon(self, names: tuple[str, ...]) -> str | None:
        """The first of *names* the system icon theme provides, else None."""
        ...

    def extra_candidates(self) -> list[CandidateApp]:
        """Platform-specific starter candidates; the use-case prefers a non-empty
        list over the cross-platform baseline. Empty by default."""
        ...


class InstalledApps(Protocol):
    """Enumerates every installed app as an add-app candidate (never pre-selected);
    the source behind the ``[＋]`` tile."""

    def scan(self) -> list[CandidateApp]:
        ...


class ProvisioningView(Protocol):
    """The UI surface the controller drives to let the user pick starter apps."""

    def present(
        self,
        candidates: list[CandidateApp],
        on_confirm: Callable[[list[CandidateApp]], None],
        on_cancel: Callable[[], None] | None = None,
        title: str | None = None,
        autostart: AutostartChoice | None = None,
    ) -> None: ...
