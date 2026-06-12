"""The gamepad-events port the Application observes.

Framework-agnostic pub/sub replacing the old raw ``pyqtSignal`` attributes:
each "signal" is a typed subscribe method returning an ``Unsubscribe`` token.
The implementation (GamepadWatcher) is responsible for delivering these on the
GUI thread; this port says nothing about threading.
"""

from collections.abc import Callable
from typing import Protocol

from domain.shared.event_emitter import Unsubscribe
from domain.input.gamepad_events import GamepadConnected, GamepadDisconnected


class GamepadSignals(Protocol):
    """Connect/disconnect and BTN_MODE events the lifecycle subscribes to."""

    def on_btn_mode(self, handler: Callable[[], None]) -> Unsubscribe: ...
    def on_connected(
        self, handler: Callable[[GamepadConnected], None]
    ) -> Unsubscribe: ...
    def on_disconnected(
        self, handler: Callable[[GamepadDisconnected], None]
    ) -> Unsubscribe: ...
