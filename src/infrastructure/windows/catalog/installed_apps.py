"""List installed apps as add-app candidates — the Windows scanner.

The source behind the ``[＋]`` tile on Windows (an :class:`InstalledApps`): it
reuses the Start Menu shortcut scan that first-run onboarding uses
(:func:`infrastructure.windows.catalog.app_discovery.discover_candidates`), but
clears the per-candidate pre-selection — the add-app picker starts with nothing
checked, the user picks. The use-case filters out the already-pinned apps.
"""

from dataclasses import replace

from domain.provisioning.candidate import CandidateApp
from domain.provisioning.ports import InstalledApps


class WindowsInstalledApps(InstalledApps):
    """Scan the Start Menu for installable app shortcuts."""

    def scan(self) -> list[CandidateApp]:
        from infrastructure.windows.catalog.app_discovery import discover_candidates
        # discover_candidates pre-selects games for the onboarding picker; the
        # add-app picker starts empty (the user adds deliberately), so clear it.
        return [replace(c, default_selected=False) for c in discover_candidates()]
