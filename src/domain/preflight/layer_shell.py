"""wlr-layer-shell, as something the system has to be set up for.

Wayland lets no client place its own top-level windows. Kasual Desktop gets its
geometry from wlr-layer-shell — the compositor sizes each surface from its
anchors — or, on GNOME, from the helper extension applying the same vocabulary
itself. With neither, the Desktop, the Home header and the hint bar are handed
arbitrary positions and the interface arrives scattered across the screen.

Unlike a disabled extension this cannot be repaired from inside a running
session: Qt binds its shell integration once, when the application is created.
So the requirement is not blocking — a scattered interface is still usable, and
the user who wants one now should not be held at a card that could not turn
green until the next start anyway.

Two states are worth telling apart, because their fixes differ. NO_PLUGIN is the
common one: the distribution packages LayerShellQt for Qt 5 only, so *this* Qt
has no shell-integration plugin at all. NO_LIBRARY means the plugin is in place
but the interface library it needs is not.
"""

from __future__ import annotations

import enum
from typing import Protocol

from domain.setup.plan import Assessment, Check, StatusLine, Subject
from domain.setup.ports import Requirement
from domain.shared.i18n import translate

NO_PLUGIN = "layer-shell-no-plugin"
NO_LIBRARY = "layer-shell-no-library"


class LayerShellState(enum.Enum):
    READY = "ready"
    NO_PLUGIN = "no-plugin"
    NO_LIBRARY = "no-library"


class LayerShellProbe(Protocol):
    def state(self) -> LayerShellState: ...


_TRAITS = {
    LayerShellState.NO_PLUGIN: NO_PLUGIN,
    LayerShellState.NO_LIBRARY: NO_LIBRARY,
}


class LayerShellSurfaces(Requirement):
    def __init__(self, probe: LayerShellProbe) -> None:
        self._probe = probe

    def subject(self) -> Subject:
        return Subject(
            title=translate(
                "Kasual Desktop", "Kasual Desktop cannot place its own windows"),
            unsupported=translate(
                "Kasual Desktop",
                "Kasual Desktop has no recipe for installing LayerShellQt on this "
                "system. It will run, but its interface arrives scattered across "
                "the screen instead of anchored to it.",
            ),
        )

    def assess(self) -> Assessment:
        state = self._probe.state()
        trait = _TRAITS.get(state)
        return Assessment(
            (self._status(state),), () if trait is None else (trait,))

    def satisfied(self, check: Check) -> bool:
        return False

    @staticmethod
    def _status(state: LayerShellState) -> StatusLine:
        if state is LayerShellState.READY:
            return StatusLine(
                translate("Kasual Desktop", "The compositor sizes Kasual's surfaces"),
                met=True,
            )
        scattered = translate(
            "Kasual Desktop",
            "Wayland lets no application position its own windows, so Kasual "
            "Desktop asks the compositor to anchor them through wlr-layer-shell. "
            "Without it the Desktop, the Home header and the hint bar land "
            "wherever the compositor happens to put them.",
        )
        if state is LayerShellState.NO_PLUGIN:
            return StatusLine(
                translate("Kasual Desktop", "This Qt has no layer-shell integration"),
                met=False,
                detail=f"{scattered}\n\n" + translate(
                    "Kasual Desktop",
                    "The integration plugin is version-locked to the Qt it was "
                    "built for, and none is installed for this one.",
                ),
            )
        return StatusLine(
            translate("Kasual Desktop", "LayerShellQt itself is missing"),
            met=False,
            detail=f"{scattered}\n\n" + translate(
                "Kasual Desktop",
                "The Qt integration plugin is in place, but the LayerShellQt "
                "library it calls into is not.",
            ),
        )
