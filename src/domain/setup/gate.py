"""Offers a requirement's setup card when the system does not meet it.

A non-blocking gate never withholds ``on_done``: the requirement is worth having
but the desktop works without it, so a user who declines still gets there. A
blocking gate has nothing to continue to, and leads to ``on_abort`` instead.
"""

from collections.abc import Callable, Mapping

from domain.setup.plan import Readiness, Remedy
from domain.setup.ports import SetupView, VerificationProbe
from domain.setup.readiness import SetupReadiness


class SetupGate:
    def __init__(
        self,
        readiness: SetupReadiness,
        view: SetupView,
        *,
        probe: VerificationProbe | None = None,
        remedies: Mapping[str, Callable[[], None]] | None = None,
        on_abort: Callable[[], None] | None = None,
    ) -> None:
        self._readiness = readiness
        self._view = view
        self._probe = probe
        self._remedies = remedies or {}
        self._on_abort = on_abort

    def ensure(self, on_done: Callable[[], None], *, force: bool = False) -> None:
        """*force* serves deliberate re-entry: on a ready system the confirmation
        itself is what the user came for."""
        report = self._readiness.report()
        if report.state is Readiness.READY and not force:
            on_done()
            return
        if report.subject.blocking and self._on_abort is None:
            raise ValueError(
                f"{type(self._readiness).__name__} blocks startup but the gate was "
                "given no on_abort, so its way out would start the session it is "
                "there to prevent"
            )
        self._view.present(
            report,
            on_recheck=self._readiness.report,
            on_done=on_done,
            on_abort=self._on_abort or on_done,
            on_remedy=self._run,
            probe=self._probe,
        )

    def _run(self, remedy: Remedy) -> None:
        action = self._remedies.get(remedy.key)
        if action is not None:
            action()
