"""The provisioning use-case — a thin orchestrator over the ports.

"Onboarding" is the first-run instance of provisioning (seeding the user's app
catalog); the domain is provisioning-flavoured so a future "Add apps" config
panel can reuse it. No I/O here — the adapters behind the ports do that.
"""

from domain.provisioning.candidate import CandidateApp
from domain.provisioning.catalog import starter_candidates
from domain.provisioning.ports import AppDiscovery, AppProvisioning


def needs_provisioning(provisioning: AppProvisioning) -> bool:
    """True when the catalog has never been provisioned — the first-run trigger.

    Keyed on the explicit marker (not directory-absence) so it survives the user
    choosing zero apps and does not re-trigger if they later delete every tile.
    """
    return not provisioning.is_provisioned()


class Provisioning:
    """Offers the starter candidates and persists the user's choice."""

    def __init__(
        self,
        provisioning: AppProvisioning,
        discovery: AppDiscovery,
        bundled_base: str,
    ) -> None:
        self._provisioning = provisioning
        self._discovery = discovery
        self._bundled_base = bundled_base

    def candidates(self) -> list[CandidateApp]:
        extras = self._discovery.extra_candidates()
        if extras:
            # Platform ships a complete bundled+scanned starter list (Start
            # Menu scan on Windows); prefer it over the cross-platform baseline,
            # whose bundled entries use ``.sh`` scripts that don't resolve on
            # the platform providing its own extras.
            return list(extras)
        return starter_candidates(self._discovery, self._bundled_base)

    def complete(self, chosen: list[CandidateApp]) -> None:
        self._provisioning.provision(chosen)
