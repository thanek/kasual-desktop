"""The ports the provisioning use-case drives — implemented in infrastructure.

Keeps the domain free of filesystem I/O, app detection and Qt: the use-case and
the view talk to these Protocols, the composition root binds the concrete
adapters (``DesktopAppProvisioning``, ``WhichAppDiscovery``,
``OnboardingOverlay``).
"""

from collections.abc import Callable
from typing import Protocol

from domain.provisioning.candidate import CandidateApp


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
    """Detects whether a system command/app is available to launch.

    Two shapes of discovery live behind this port: binary availability on
    ``PATH`` (``is_available`` / ``system_icon`` — what the bundled
    :func:`starter_candidates` catalogue filters on) and a platform-specific
    **extras** layer (``extra_candidates`` — e.g. a Start Menu scan on Windows,
    empty by default). The use-case prefers a non-empty ``extra_candidates``
    list over the cross-platform baseline so a platform can ship its own
    complete bundled+scanned candidate set when the baseline's paths do not
    apply (e.g. Windows bundled apps launch via ``pythonw.exe`` rather than a
    ``.sh`` script).
    """

    def is_available(self, command: str) -> bool: ...

    def system_icon(self, names: tuple[str, ...]) -> str | None:
        """The first of *names* the system icon theme actually provides, else None.

        Lets provisioning prefer a real installed app icon (e.g. the genuine
        ``steam`` logo) over the bundled Font Awesome glyph when the system has
        one — the glyph stays as the fallback for a system that does not."""
        ...

    def extra_candidates(self) -> list[CandidateApp]:
        """Platform-specific extra starter candidates beyond the baseline.

        Empty by default (Linux relies on the cross-platform
        :func:`starter_candidates`). A platform that bundles its own app launch
        mechanism and/or scans the system menu (Start Menu on Windows) returns
        the full appended list here; the use-case prefers this over the
        baseline when non-empty."""
        ...


class InstalledApps(Protocol):
    """Enumerates the apps installed on the system as add-app candidates.

    The source behind the ``[＋]`` tile (post-first-run provisioning, §7.4).
    Unlike :class:`AppDiscovery`, which only answers availability of a handful of
    known commands, this returns the *whole* installed set — freedesktop
    ``.desktop`` files on Linux, Start Menu shortcuts on Windows — as
    :class:`CandidateApp`\\ s (never pre-selected: the user picks). The add-app
    use-case filters the already-pinned ones out before showing the picker."""

    def scan(self) -> list[CandidateApp]:
        ...


class ProvisioningView(Protocol):
    """The UI surface the controller drives to let the user pick starter apps."""

    def present(
        self,
        candidates: list[CandidateApp],
        on_confirm: Callable[[list[CandidateApp]], None],
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        """Show the picker; report the chosen candidates via ``on_confirm``.

        ``on_cancel`` is offered for reuse by views that allow dismissal; the
        first-run picker is confirm-only and never invokes it."""
        ...
