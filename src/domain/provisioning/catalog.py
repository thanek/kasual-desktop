"""The starter apps offered on first run. Names are the canonical English strings
the view translates; bundled launchers are always offered, system apps only when
discovery finds their command."""

from collections.abc import Sequence
from dataclasses import replace

from domain.catalog.app import App
from domain.input.vocabulary import Trigger
from domain.provisioning.candidate import CandidateApp
from domain.provisioning.ports import AppDiscovery


# What Kasual's own apps announce themselves as (their Wayland app_id). Keyed by the
# launcher that starts them, because that is all a tile records about them.
BUNDLED_WM_CLASS = {
    "file_browser.sh": "kasual-file-browser",
    "yt.sh":           "kasual-youtube",
    "netflix.sh":      "kasual-netflix",
}


def with_bundled_identity(app: App) -> App:
    """Tiles provisioned before Kasual's own apps announced an app_id carry no
    StartupWMClass, so those apps' windows look foreign to Kasual — it would offer to
    close "the window" rather than the app. Their identity is known; fill it in."""
    if app.wm_class or app.command_basename not in BUNDLED_WM_CLASS:
        return app
    return replace(app, wm_class=BUNDLED_WM_CLASS[app.command_basename])


def starter_candidates(discovery: AppDiscovery, bundled_base: str) -> list[CandidateApp]:
    """Build the ordered starter list, filtering system apps by availability."""
    def with_real_icon(app: App, *icon_names: str) -> App:
        found = discovery.system_icon(icon_names)
        return replace(app, icon_theme=found) if found else app

    candidates: list[CandidateApp] = [
        CandidateApp(
            key="files",
            app=App(
                name="File Browser",
                command=f"{bundled_base}/apps/file_browser/file_browser.sh",
                wm_class=BUNDLED_WM_CLASS["file_browser.sh"],
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
                wm_class=BUNDLED_WM_CLASS["yt.sh"],
                icon="fa5b.youtube",
                color="#c0392b",
            ), "youtube"),
            order=30,
            default_selected=True,
        ),
        CandidateApp(
            key="netflix",
            app=with_real_icon(App(
                name="Netflix",
                command=f"{bundled_base}/apps/netflix/netflix.sh",
                wm_class=BUNDLED_WM_CLASS["netflix.sh"],
                icon="fa5s.film",
                color="#e50914",
            ), "netflix"),
            order=35,
            default_selected=False,
            requires_cdm=True,
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
    """The *candidates* not already pinned. Identity is the launch command, not the
    ``key``: the live catalog holds plain apps with no source filename, but the
    command round-trips unchanged, so a re-offered Steam matches the pinned one."""
    pinned = {_launch_identity(app) for app in existing}
    return [c for c in candidates if _launch_identity(c.app) not in pinned]


def _launch_identity(app: App) -> tuple[str, tuple[str, ...]]:
    return (app.command, tuple(app.args))


# Gaming launchers surfaced first (KD is gamepad-first); matched against a
# candidate's key or command basename. Order here is the shown order.
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
    """Well-known launchers first (in listed order), then the rest by name."""
    rank = {key: i for i, key in enumerate(_WELL_KNOWN)}

    def known_rank(c: CandidateApp) -> int | None:
        if c.key in rank:
            return rank[c.key]
        return rank.get(c.app.command_basename)

    well = sorted((c for c in candidates if known_rank(c) is not None), key=known_rank)
    rest = sorted((c for c in candidates if known_rank(c) is None),
                  key=lambda c: c.app.name.casefold())
    return well + rest
