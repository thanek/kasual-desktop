"""The Desktop coordinator — showing, pausing and resuming the Desktop surface.

The framework-agnostic "what happens" when the Desktop comes forward, is
minimized to the tray, or is resumed after the controller reconnects. It drives
the view, the input-focus, the window list and the sound through ports; the Qt
widget is merely the view that carries each step out. The visibility / paused /
foreground transitions are decided by the domain `DesktopState`.

Reads as the vocabulary it implements:
  - show_desktop → go to the bare Desktop: take input, refresh windows, show,
    restore any paused overlays, activate;
  - pause        → sound, mark paused, pause overlays, release input, hide;
  - resume       → take input, sound, show, restore overlays if we were paused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.shell.desktop_state import DesktopState
from domain.shared.feedback import Cue, Feedback

if TYPE_CHECKING:
    from domain.shell.desktop_view import DesktopView


class Desktop:
    def __init__(self, state: DesktopState, view: "DesktopView", feedback: Feedback) -> None:
        self._state    = state
        self._view     = view
        self._feedback = feedback

    def show_desktop(self) -> None:
        """Bring the bare Desktop forward (leaving any running app behind)."""
        was_paused = self._state.go_to_desktop()
        self._view.take_input()
        self._view.refresh_windows()
        self._view.show_fullscreen()
        if was_paused:
            self._view.resume_overlays()
        self._view.activate()

    def pause(self) -> None:
        """Minimize the Desktop to the tray, staying ready to resume."""
        self._feedback.play(Cue.EXIT)
        self._state.pause()
        self._view.pause_overlays()
        self._view.release_input()
        self._view.hide_view()

    def resume(self) -> None:
        """Come back after the controller reconnects, without resetting foreground."""
        was_paused = self._state.resume()
        self._view.take_input()
        self._feedback.play(Cue.START)
        self._view.show_fullscreen()
        if was_paused:
            self._view.resume_overlays()
        self._view.activate()
