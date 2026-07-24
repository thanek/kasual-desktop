"""Startup gate for the surface protocol Kasual's interface rests on.

Wayland lets no client place its own top-level windows. Kasual gets its geometry
from wlr-layer-shell — the compositor sizes each surface from its anchors — or, on
GNOME, from the helper extension applying the same vocabulary itself. With neither,
the Desktop, the Home header and the hint bar are handed arbitrary positions and the
interface arrives scattered across the screen.

Unlike a disabled extension, this cannot be repaired from inside a running session:
Qt binds its shell integration once, when the application is created. So the gate
explains and offers a way out rather than a retry that could never succeed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class SurfaceBlockerView(Protocol):
    def show_missing_layer_shell(
        self, on_continue: Callable[[], None], on_quit: Callable[[], None]
    ) -> None: ...


class SurfaceGate:
    """Lets the session start only once Kasual can really be put on screen —
    or once the user has chosen to accept a scattered one."""

    def __init__(
        self,
        layer_shell_available: Callable[[], bool],
        view: SurfaceBlockerView,
        on_quit: Callable[[], None],
    ) -> None:
        self._available = layer_shell_available
        self._view = view
        self._on_quit = on_quit

    def ensure(self, on_ready: Callable[[], None]) -> None:
        if self._available():
            on_ready()
        else:
            self._view.show_missing_layer_shell(
                on_continue=on_ready, on_quit=self._on_quit)
