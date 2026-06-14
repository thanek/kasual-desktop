"""The overlays currently on screen — the group the shell acts on together."""

from typing import Protocol


class Overlay(Protocol):
    """A member of the on-screen overlay set."""

    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def cancel(self) -> None: ...


class OpenOverlays:
    """The overlays currently on screen.

    Infrastructure registers an overlay as it opens and forgets it as it closes,
    so no concrete overlay kind is ever named here: a new one joins the group
    just by registering. The Desktop coordinator pauses and resumes the group as
    the surface hides and returns; the controller cancels it when the Home
    Overlay takes over the screen.
    """

    def __init__(self) -> None:
        self._open: list[Overlay] = []

    def register(self, overlay: Overlay) -> None:
        self._open.append(overlay)

    def forget(self, overlay: Overlay) -> None:
        if overlay in self._open:
            self._open.remove(overlay)

    def pause(self) -> None:
        for overlay in self._open:
            overlay.pause()

    def resume(self) -> None:
        for overlay in self._open:
            overlay.resume()

    def cancel(self) -> None:
        """Tear down every overlay, dropping its pending action."""
        while self._open:
            self._open.pop().cancel()
