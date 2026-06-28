"""The single source of truth for the starter apps offered on first run.

Pure domain rule: *what* Kasual Desktop offers a fresh install, the default
selections, and the availability filtering for system apps. This is the runtime
seed for first-run provisioning. Names here are the canonical English strings —
the view translates them (i18n lives in the Qt layer). Bundled launchers are
always offered; system apps appear only when the injected :class:`AppDiscovery`
finds their command.
"""

from collections.abc import Sequence
from dataclasses import replace

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
    def with_real_icon(app: App, *icon_names: str) -> App:
        """Prefer a real installed app icon over the bundled Font Awesome glyph.

        When the system icon theme actually provides one of *icon_names* (e.g. the
        genuine ``steam`` logo), seed the entry with that themed ``Icon`` and drop
        the glyph, so a provisioned tile shows the real app icon. Leaves the glyph
        in place when the system has no matching icon."""
        found = discovery.system_icon(icon_names)
        return replace(app, icon_theme=found, icon=None) if found else app

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
            app=with_real_icon(App(
                name="YouTube",
                command=f"{bundled_base}/apps/yt/yt.sh",
                icon="fa5b.youtube",
                color="#c0392b",
            ), "youtube"),
            order=30,
            default_selected=True,
        ),
    ]

    if discovery.is_available("steam"):
        candidates.append(CandidateApp(
            key="steam",
            app=with_real_icon(App(
                name="Steam",
                command="steam",
                args=("steam://open/bigpicture",),
                icon="fa5b.steam",
                color="#1b2838",
                recall_menu_trigger=Trigger.HOLD_1S,
                launch_hide_grace_ms=500,
                categories=("Game",),
            ), "steam"),
            order=10,
            default_selected=True,
        ))

    if discovery.is_available("heroic"):
        candidates.append(CandidateApp(
            key="heroic",
            app=with_real_icon(App(
                name="Heroic",
                command="heroic",
                args=("--fullscreen",),
                icon="fa5s.gamepad",
                color="#c0392b",
                recall_menu_trigger=Trigger.CLICK,
                categories=("Game",),
            ), "com.heroicgameslauncher.hgl", "heroic"),
            order=20,
            default_selected=True,
        ))

    return candidates


def unpinned_candidates(
    candidates: Sequence[CandidateApp], existing: Sequence[App]
) -> list[CandidateApp]:
    """The *candidates* not already present in the catalog — the add-app picker list.

    The ``[＋]`` flow re-offers the starter list with the already-pinned apps
    filtered out. Identity is the launch command (and its args), not the
    candidate ``key``: the live catalog holds plain :class:`App`\\ s with no source
    filename, but the command is stable and round-trips through the ``.desktop``
    file unchanged, so a re-offered Steam matches the pinned Steam regardless of
    how its tile was created."""
    pinned = {_launch_identity(app) for app in existing}
    return [c for c in candidates if _launch_identity(c.app) not in pinned]


def _launch_identity(app: App) -> tuple[str, tuple[str, ...]]:
    """The (command, args) pair identifying what an app actually launches."""
    return (app.command, tuple(app.args))


# Well-known gaming launchers / storefronts, surfaced first in the add-app picker
# (KD is gamepad-first, so these are the apps a user most likely wants to pin).
# Matched against a candidate's key (the ``.desktop`` filename — stable for both
# native and Flatpak ids) or its command basename. Order here is the shown order.
_WELL_KNOWN: tuple[str, ...] = (
    "steam", "com.valvesoftware.Steam",
    "heroic", "com.heroicgameslauncher.hgl",
    "lutris", "net.lutris.Lutris",
    "bottles", "com.usebottles.bottles",
    "prismlauncher", "org.prismlauncher.PrismLauncher",
    "com.gog.Galaxy", "legendary",
    "discord", "com.discordapp.Discord",
)


def order_for_adding(candidates: Sequence[CandidateApp]) -> list[CandidateApp]:
    """Order add-app candidates: well-known launchers first, then the rest by name.

    The curated launchers (:data:`_WELL_KNOWN`) lead, in their listed order, so the
    apps a gamepad user most likely wants are within easy reach; everything else
    follows alphabetically by name."""
    rank = {key: i for i, key in enumerate(_WELL_KNOWN)}

    def known_rank(c: CandidateApp) -> int | None:
        if c.key in rank:
            return rank[c.key]
        return rank.get(c.app.command_basename)

    well = sorted((c for c in candidates if known_rank(c) is not None), key=known_rank)
    rest = sorted((c for c in candidates if known_rank(c) is None),
                  key=lambda c: c.app.name.casefold())
    return well + rest
