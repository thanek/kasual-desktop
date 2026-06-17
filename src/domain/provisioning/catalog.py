"""The single source of truth for the starter apps offered on first run.

Pure domain rule: *what* Kasual Desktop offers a fresh install, the default
selections, and the availability filtering for system apps. This supersedes the
loose ``examples/apps/*.desktop`` as the runtime seed (those stay as reference
docs). Names here are the canonical English strings — the view translates them
(i18n lives in the Qt layer). Bundled launchers are always offered; system apps
appear only when the injected :class:`AppDiscovery` finds their command.
"""

from domain.catalog.app import App
from domain.input.vocabulary import Trigger
from domain.provisioning.candidate import CandidateApp
from domain.provisioning.ports import AppDiscovery


def starter_candidates(discovery: AppDiscovery, bundled_base: str) -> list[CandidateApp]:
    """Build the ordered starter list, filtering system apps by availability.

    ``bundled_base`` is the absolute install path of the repo (injected by
    infrastructure), used to resolve the bundled launchers' ``Exec`` — keeping
    the absolute path out of the domain.
    """
    candidates: list[CandidateApp] = [
        CandidateApp(
            key="files",
            app=App(
                name="File Browser",
                command=f"{bundled_base}/apps/file_browser/file_browser.sh",
                icon="fa5s.folder-open",
                color="#5e81ac",
            ),
            order=40,
            default_selected=True,
        ),
        CandidateApp(
            key="youtube",
            app=App(
                name="YouTube",
                command=f"{bundled_base}/apps/yt/yt.sh",
                icon="fa5b.youtube",
                color="#c0392b",
            ),
            order=30,
            default_selected=True,
        ),
    ]

    if discovery.is_available("steam"):
        candidates.append(CandidateApp(
            key="steam",
            app=App(
                name="Steam",
                command="steam",
                args=("steam://open/bigpicture",),
                icon="fa5b.steam",
                color="#1b2838",
                recall_menu_trigger=Trigger.HOLD_1S,
                launch_hide_grace_ms=500,
                categories=("Game",),
            ),
            order=10,
            default_selected=True,
        ))

    if discovery.is_available("heroic"):
        candidates.append(CandidateApp(
            key="heroic",
            app=App(
                name="Heroic",
                command="heroic",
                args=("--fullscreen",),
                icon="fa5s.gamepad",
                color="#c0392b",
                recall_menu_trigger=Trigger.CLICK,
                categories=("Game",),
            ),
            order=20,
            default_selected=True,
        ))

    return candidates
