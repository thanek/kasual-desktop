"""One selectable starter app offered during provisioning.

Pure domain — describes *what* could be seeded into the user's app catalog,
not the live selection state (that mutable concern lives in
:class:`domain.provisioning.selection.AppSelection`, so candidates stay
immutable and reusable across sessions).
"""

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
