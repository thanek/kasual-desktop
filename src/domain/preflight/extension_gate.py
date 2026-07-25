"""Startup gate for an integration that window management depends on.

DISABLED is the one state the gate can resolve on its own, by enabling it;
ABSENT and UNLOADED it can only instruct the user to fix. UNLOADED is the one
instruction the gate can still act on halfway: the remedy is a fresh session, so
it offers to end this one rather than leaving the user to find the logout menu.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from typing import Protocol


class ExtensionState(enum.Enum):
    READY = "ready"
    DISABLED = "disabled"
    ABSENT = "absent"
    UNLOADED = "unloaded"


class ExtensionProbe(Protocol):
    def state(self) -> ExtensionState: ...


class ExtensionActivator(Protocol):
    def enable(self) -> bool:
        """Attempt to enable the extension; True once it is ready to answer."""
        ...


class SessionEnder(Protocol):
    def log_out(self) -> None:
        """End the desktop session, so the next one starts with the extension."""
        ...


class PreflightView(Protocol):
    def ask_enable(
        self, on_accept: Callable[[], None], on_decline: Callable[[], None]
    ) -> None: ...

    def show_instructions(
        self,
        state: ExtensionState,
        on_retry: Callable[[], None],
        on_quit: Callable[[], None],
        on_logout: Callable[[], None] | None = None,
    ) -> None: ...


class ExtensionGate:
    def __init__(
        self,
        probe: ExtensionProbe,
        activator: ExtensionActivator,
        view: PreflightView,
        on_quit: Callable[[], None],
        session: SessionEnder | None = None,
    ) -> None:
        self._probe = probe
        self._activator = activator
        self._view = view
        self._on_quit = on_quit
        self._session = session

    def ensure(self, on_ready: Callable[[], None]) -> None:
        state = self._probe.state()
        if state is ExtensionState.READY:
            on_ready()
        elif state is ExtensionState.DISABLED:
            self._view.ask_enable(
                on_accept=lambda: self._enable_then(on_ready),
                on_decline=lambda: self._instruct(ExtensionState.DISABLED, on_ready),
            )
        else:
            self._instruct(state, on_ready)

    def _enable_then(self, on_ready: Callable[[], None]) -> None:
        if self._activator.enable():
            on_ready()
        else:
            self._instruct(ExtensionState.DISABLED, on_ready)

    def _instruct(self, state: ExtensionState, on_ready: Callable[[], None]) -> None:
        self._view.show_instructions(
            state,
            on_retry=lambda: self.ensure(on_ready),
            on_quit=self._on_quit,
            on_logout=self._logout_remedy(state),
        )

    def _logout_remedy(self, state: ExtensionState) -> Callable[[], None] | None:
        if state is ExtensionState.UNLOADED and self._session is not None:
            return self._session.log_out
        return None
