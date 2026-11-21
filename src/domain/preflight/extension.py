"""The GNOME Shell helper extension, as something the system has to be set up for.

Window management on GNOME goes through the extension, so this is the one
requirement Kasual Desktop cannot run without. Two of its states carry a remedy
Kasual Desktop can perform itself: DISABLED it can enable, and UNLOADED needs a
fresh session, which it can at least start rather than leaving the user to find
the logout menu. ABSENT it can only instruct.
"""

from __future__ import annotations

import enum
from typing import Protocol

from domain.setup.plan import Assessment, Check, StatusLine, Subject
from domain.setup.ports import Requirement
from domain.shared.i18n import translate

ENABLE = "enable"
LOG_OUT = "log-out"

DISABLED = "extension-disabled"
ABSENT = "extension-absent"
UNLOADED = "extension-unloaded"

STAGE = "extension-stage"
INSTALLED = "installed"
FRESH_SESSION = "fresh-session"


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


_TRAITS = {
    ExtensionState.DISABLED: DISABLED,
    ExtensionState.ABSENT: ABSENT,
    ExtensionState.UNLOADED: UNLOADED,
}

_STAGES_PASSED = {
    INSTALLED: frozenset({
        ExtensionState.UNLOADED, ExtensionState.DISABLED, ExtensionState.READY}),
    FRESH_SESSION: frozenset({ExtensionState.DISABLED, ExtensionState.READY}),
}


def stage_check(stage: str) -> Check:
    return Check(STAGE, stage)


class HelperExtension(Requirement):
    def __init__(self, probe: ExtensionProbe) -> None:
        self._probe = probe
        self._last_assessed_state: ExtensionState | None = None

    def subject(self) -> Subject:
        return Subject(
            title=translate(
                "Kasual Desktop", "Kasual Desktop needs its GNOME Shell helper"),
            unsupported=translate(
                "Kasual Desktop",
                "Kasual Desktop cannot tell what state the helper extension is "
                "in on this system.",
            ),
            blocking=True,
        )

    def assess(self) -> Assessment:
        state = self._last_assessed_state = self._probe.state()
        trait = _TRAITS.get(state)
        return Assessment(
            (self._status(state),), () if trait is None else (trait,))

    def satisfied(self, check: Check) -> bool:
        if check.kind != STAGE or self._last_assessed_state is None:
            return False
        return self._last_assessed_state in _STAGES_PASSED.get(
            check.value, frozenset())

    @staticmethod
    def _status(state: ExtensionState) -> StatusLine:
        if state is ExtensionState.READY:
            return StatusLine(
                translate("Kasual Desktop", "The Kasual Helper extension is running"),
                met=True,
            )
        return StatusLine(
            translate(
                "Kasual Desktop", "The Kasual Helper extension is not answering"),
            met=False,
        )
