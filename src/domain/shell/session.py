"""Session policy — controller presence decides whether Kasual Desktop is on screen
and owns the sound."""

from domain.shell.session_collaborators import (
    ConnectionIndicator, Dismissable, SessionSound, SessionView,
)


class SessionPolicy:
    """Keeps desktop visibility in sync with controller presence."""

    def __init__(self, view: SessionView, indicator: ConnectionIndicator,
                 sound: SessionSound):
        self._view = view
        self._indicator = indicator
        self._sound = sound

    def gamepad_connected_changed(
        self, connected: bool, overlay: Dismissable | None
    ) -> None:
        self._indicator.set_connected(connected)
        if connected:
            self._view.resume()
            self._sound.take_over()
        else:
            if overlay is not None:
                overlay.hide_overlay()
            self._view.withdraw()
            self._sound.give_back()
