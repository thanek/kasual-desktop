"""The ports the setup use-case drives — implemented in infrastructure."""

from collections.abc import Callable
from typing import Protocol

from domain.setup.plan import (
    Assessment, Check, MachineProfile, ReadinessReport, Remedy, Subject,
)


class SystemFacts(Protocol):
    """Answers the predicates any recipe's steps may be written against."""

    def machine(self) -> MachineProfile: ...

    def has_command(self, name: str) -> bool: ...

    def path_exists(self, pattern: str) -> bool:
        """True when the glob *pattern* matches at least one file."""
        ...


class Requirement(Protocol):
    """One thing Kasual Desktop needs of the system it runs on."""

    def subject(self) -> Subject: ...

    def assess(self) -> Assessment:
        """Inspect the system once — recipe selection and every status line the
        card shows come out of the same pass."""
        ...

    def satisfied(self, check: Check) -> bool:
        """Answer a check of a kind only this requirement defines."""
        ...


class VerificationProbe(Protocol):
    """Confirms the requirement actually works, which its parts being in place
    does not."""

    def verify(self, on_result: Callable[[bool], None]) -> None:
        """The outcome reaches *on_result* tens of seconds later at worst."""
        ...

    def cancel(self) -> None:
        """Drops a check in flight — its ``on_result`` is then never called."""
        ...


class SetupView(Protocol):
    def present(
        self,
        report: ReadinessReport,
        on_recheck: Callable[[], ReadinessReport],
        on_done: Callable[[], None],
        on_abort: Callable[[], None],
        on_remedy: Callable[[Remedy], None],
        probe: VerificationProbe | None = None,
    ) -> None: ...
