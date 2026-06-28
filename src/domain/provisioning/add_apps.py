"""The add-app use-case — provisioning after first run (the ``[＋]`` tile).

The first-run :class:`~domain.provisioning.provisioning.Provisioning` seeds an
empty catalog once from a curated starter list; this reopens provisioning on
demand so adding *any* installed app is a gamepad-first action rather than a
manual ``.desktop`` edit. It offers the system's installed apps (via the
:class:`InstalledApps` source) **minus the already-pinned ones** and persists the
chosen subset as new catalog tiles. No I/O here — the scanner and the
:class:`AppProvisioning` adapter behind the ports do that.
"""

from collections.abc import Sequence

from domain.catalog.app import App
from domain.provisioning.candidate import CandidateApp
from domain.provisioning.catalog import order_for_adding, unpinned_candidates
from domain.provisioning.ports import AppProvisioning, InstalledApps


class AppAdder:
    """Offers the not-yet-pinned installed apps and persists the chosen ones."""

    def __init__(self, installed: InstalledApps, store: AppProvisioning) -> None:
        # The candidate source (system scan) and the same persistence port the
        # first-run flow writes through.
        self._installed = installed
        self._store = store

    def available(self, existing: Sequence[App]) -> list[CandidateApp]:
        """The installed apps not already in *existing* (the live catalog), with the
        well-known launchers ordered first."""
        return order_for_adding(unpinned_candidates(self._installed.scan(), existing))

    def add(self, chosen: list[CandidateApp]) -> None:
        """Persist *chosen* as new catalog ``.desktop`` files.

        Writing them is the durable half; the caller appends each
        ``candidate.app`` to the live tile bar so the new tiles show at once."""
        self._store.provision(chosen)
