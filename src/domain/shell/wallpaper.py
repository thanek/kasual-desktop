"""The desktop's background — the currently-used system wallpaper.

The Kasual Desktop shows the system's own wallpaper behind its tiles, so the
two never disagree. `Wallpaper` is the background as a domain value (just the
image to render); `SystemWallpaper` is the port that resolves whichever image
the system currently uses. The *how* (reading the desktop environment's config,
picking the right image from a wallpaper package) stays in infrastructure.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Wallpaper:
    """The desktop background: a path to the image to render behind the tiles."""

    image_path: str


class SystemWallpaper(Protocol):
    """Resolves the wallpaper the system is currently using (KDE Plasma's)."""

    def current(self) -> Wallpaper | None: ...
