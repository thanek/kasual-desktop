"""One selectable starter app offered during provisioning."""

from dataclasses import dataclass

from domain.catalog.app import App


@dataclass(frozen=True)
class CandidateApp:
    """A starter app the user may choose to install on first run.

    ``key`` is a stable slug doubling as the output filename (``steam`` →
    ``steam.desktop``); ``order`` is the placement key written as
    ``X-Kasual-Order``; ``default_selected`` is its initial toggle state.
    """

    key:              str
    app:              App
    order:            int
    default_selected: bool

    @property
    def requires_cdm(self) -> bool:
        return self.app.requires_cdm
