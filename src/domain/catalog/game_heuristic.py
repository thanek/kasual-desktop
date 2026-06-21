"""Heuristic: does an app look like a game / gaming launcher?

Used to pre-select the relevant tiles during first-run onboarding (the picker
ticks these by default). Deliberately small for now — a curated launcher list
plus the freedesktop ``Game`` category — and meant to grow over time, shared by
both the Linux and Windows onboarding paths.

Pure domain: takes an :class:`App`, no I/O, no platform specifics.
"""

from domain.catalog.app import App

# Known gaming launchers / storefronts, matched as substrings of the app's name
# or command (lowercased). Expand as needed.
_LAUNCHER_KEYWORDS = (
    "steam",
    "epic games",
    "gog galaxy",
    "galaxyclient",
    "ea app",
    "ea desktop",
    "origin",
    "battle.net",
    "battlenet",
    "ubisoft",
    "uplay",
    "riot",
    "playnite",
    "itch",
    "amazon games",
    "xbox",
    "rockstar games",
)


def looks_like_game(app: App) -> bool:
    """True if *app* is a game or a known gaming launcher.

    Checks the freedesktop ``Game`` category first (set on Linux ``.desktop``
    entries), then falls back to matching known launcher names/commands — the
    only signal available for Windows ``.lnk`` apps, which carry no category."""
    if app.is_game:
        return True
    hay = f"{app.name} {app.command}".lower()
    return any(keyword in hay for keyword in _LAUNCHER_KEYWORDS)
