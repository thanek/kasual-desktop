"""Shared `GamepadSignals` / `PadControl` plumbing for platform gamepad watchers.

Both platform watchers read a physical pad on a background thread yet must touch
their observers only on the GUI thread. That bridge — the hop signals, the
`EventEmitter` trio, the LIFO handler stack and the late-subscriber replay — is
identical across platforms and lives here. A subclass implements only its device
read loop, calling the protected `_hop_*` emitters to surface navigation,
BTN_MODE and connect/disconnect onto the GUI thread.

Threading: the read loop runs on a background thread; the `_*_hop` pyqtSignals
marshal each observation onto the GUI thread (Qt delivers them queued because
this QObject lives there), and only then do the domain `EventEmitter`s fan out.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from domain.input.focus_stack import InputFocusStack
from domain.input.gamepad_events import (
    BtnModePressed, GamepadConnected, GamepadDisconnected,
)
from domain.input.gamepad_signals import GamepadSignals
from domain.input.pad_control import PadControl
from domain.shared.event_emitter import EventEmitter, Unsubscribe
from infrastructure.common.qt._meta import ProtocolQtMeta

logger = logging.getLogger(__name__)


class BaseGamepadWatcher(
    QObject, PadControl, GamepadSignals, metaclass=ProtocolQtMeta
):
    """Owns the GUI-thread bridge and the two domain ports; subclasses add the loop.

    Subclasses drive their device read loop on a background thread and call
    `_hop_nav` / `_hop_btn_mode` / `_hop_connected` / `_hop_disconnected` to
    deliver observations; everything those touch (the handler stack, the
    emitters, the `_connected` latch) is only ever read or written on the GUI
    thread, so subclasses never synchronise against observers themselves.
    """

    # Background loop → GUI thread. Delivered via a queued connection because
    # this QObject lives on the GUI thread.
    _nav_hop          = pyqtSignal(str)
    _btn_mode_hop     = pyqtSignal()
    _connected_hop    = pyqtSignal()
    _disconnected_hop = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._stack = InputFocusStack()   # who receives navigation events (LIFO)
        # Last connection state seen on the GUI thread, so a subscriber that
        # registers after the one-shot connected hop already fired still learns
        # the current state — see on_connected.
        self._connected = False

        self._btn_mode_emitter     = EventEmitter[BtnModePressed]()
        self._connected_emitter    = EventEmitter[GamepadConnected]()
        self._disconnected_emitter = EventEmitter[GamepadDisconnected]()

        # Bound-method slots (not lambdas) so each fan-out runs on the GUI thread
        # and is individually testable.
        self._nav_hop.connect(self._dispatch)
        self._btn_mode_hop.connect(self._on_btn_mode_hop)
        self._connected_hop.connect(self._on_connected_hop)
        self._disconnected_hop.connect(self._on_disconnected_hop)

    # ── Protected hops (call from the background loop) ────────────────────────

    def _hop_nav(self, event: str) -> None:
        self._nav_hop.emit(event)

    def _hop_btn_mode(self) -> None:
        self._btn_mode_hop.emit()

    def _hop_connected(self) -> None:
        self._connected_hop.emit()

    def _hop_disconnected(self) -> None:
        self._disconnected_hop.emit()

    # ── GUI-thread slots ──────────────────────────────────────────────────────

    def _dispatch(self, event: str) -> None:
        """Deliver a navigation event to the active handler (on the GUI thread)."""
        self._stack.dispatch(event)

    def _on_btn_mode_hop(self) -> None:
        self._btn_mode_emitter.emit(BtnModePressed())

    def _on_connected_hop(self) -> None:
        self._connected = True
        self._connected_emitter.emit(GamepadConnected())

    def _on_disconnected_hop(self) -> None:
        self._connected = False
        self._disconnected_emitter.emit(GamepadDisconnected())

    # ── GamepadSignals port ────────────────────────────────────────────────────

    def on_btn_mode(self, handler: Callable[[], None]) -> Unsubscribe:
        return self._btn_mode_emitter.subscribe(lambda _evt: handler())

    def on_connected(
        self, handler: Callable[[GamepadConnected], None]
    ) -> Unsubscribe:
        unsubscribe = self._connected_emitter.subscribe(handler)
        # Replay the current state to a late subscriber: if the pad was already
        # grabbed before this subscription, the one-shot hop fired with no
        # listener, so deliver it now (deferred to the event loop, off __init__).
        if self._connected:
            QTimer.singleShot(0, lambda: handler(GamepadConnected()))
        return unsubscribe

    def on_disconnected(
        self, handler: Callable[[GamepadDisconnected], None]
    ) -> Unsubscribe:
        return self._disconnected_emitter.subscribe(handler)

    # ── PadControl port ────────────────────────────────────────────────────────

    def push_handler(self, handler: Callable[[str], None]) -> None:
        self._stack.push(handler)

    def pop_handler(self, handler: Callable[[str], None]) -> None:
        self._stack.pop(handler)

    def inject(self, event: str) -> None:
        """Inject a navigation event (e.g. from keyboard) into the active handler."""
        self._dispatch(event)

    def top_handler(self) -> Callable[[str], None] | None:
        """The handler currently receiving events, or None if the stack is empty."""
        return self._stack.top()

    def trigger_btn_mode(self) -> None:
        """Request BTN_MODE from outside the gamepad (e.g. a keyboard shortcut).

        Routed through the same GUI-thread hop as a real press, so observers run
        on the GUI thread regardless of the caller."""
        self._btn_mode_hop.emit()

    def trigger_home(self) -> None:
        """Open the Home overlay (keyboard equivalent of BTN_MODE)."""
        self.trigger_btn_mode()
