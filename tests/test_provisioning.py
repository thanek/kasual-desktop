"""Tests for the pure provisioning domain: catalog, selection, use-case."""

from domain.provisioning.catalog import starter_candidates
from domain.provisioning.selection import AppSelection
from domain.provisioning.provisioning import Provisioning, needs_provisioning


class FakeDiscovery:
    """An AppDiscovery whose available commands and themed icons are fixed up front."""

    def __init__(self, available: set[str], icons: set[str] | None = None):
        self._available = available
        self._icons = icons or set()

    def is_available(self, command: str) -> bool:
        return command in self._available

    def system_icon(self, names: tuple[str, ...]) -> str | None:
        return next((n for n in names if n in self._icons), None)

    def extra_candidates(self):
        return []


class FakeProvisioning:
    """An AppProvisioning recording what it was asked to provision."""

    def __init__(self, provisioned: bool = False):
        self._provisioned = provisioned
        self.received = None

    def is_provisioned(self) -> bool:
        return self._provisioned

    def provision(self, candidates) -> None:
        self.received = list(candidates)
        self._provisioned = True


# ── starter_candidates ──────────────────────────────────────────────────────

class TestStarterCandidates:
    def test_bundled_always_present_with_resolved_paths(self):
        cands = starter_candidates(FakeDiscovery(set()), bundled_base="/opt/kd")
        by_key = {c.key: c for c in cands}
        assert "files" in by_key and "youtube" in by_key
        assert by_key["files"].app.command == "/opt/kd/apps/file_browser/file_browser.sh"
        assert by_key["youtube"].app.command == "/opt/kd/apps/yt/yt.sh"

    def test_system_apps_filtered_by_availability(self):
        none = {c.key for c in starter_candidates(FakeDiscovery(set()), "/x")}
        assert "steam" not in none and "heroic" not in none

        both = {c.key for c in starter_candidates(
            FakeDiscovery({"steam", "heroic"}), "/x")}
        assert "steam" in both and "heroic" in both

    def test_only_available_system_app_included(self):
        keys = {c.key for c in starter_candidates(FakeDiscovery({"steam"}), "/x")}
        assert "steam" in keys and "heroic" not in keys

    def test_defaults_selected_when_present(self):
        cands = starter_candidates(FakeDiscovery({"steam", "heroic"}), "/x")
        assert all(c.default_selected for c in cands)

    def test_steam_is_a_game_with_hold_trigger(self):
        steam = next(c for c in starter_candidates(FakeDiscovery({"steam"}), "/x")
                     if c.key == "steam")
        assert steam.app.is_game
        assert steam.app.recall_menu_trigger == "BTN_MODE_HOLD_1S"
        assert steam.order == 10

    def test_falls_back_to_glyph_when_system_has_no_real_icon(self):
        steam = next(c for c in starter_candidates(FakeDiscovery({"steam"}), "/x")
                     if c.key == "steam")
        assert steam.app.icon == "fa5b.steam"
        assert steam.app.icon_theme is None

    def test_prefers_real_system_icon_over_glyph(self):
        cands = starter_candidates(
            FakeDiscovery({"steam"}, icons={"steam", "youtube"}), "/x")
        steam = next(c for c in cands if c.key == "steam")
        youtube = next(c for c in cands if c.key == "youtube")
        assert steam.app.icon_theme == "steam" and steam.app.icon is None
        assert youtube.app.icon_theme == "youtube" and youtube.app.icon is None

    def test_heroic_uses_reverse_dns_icon_when_present(self):
        heroic = next(
            c for c in starter_candidates(
                FakeDiscovery({"heroic"}, icons={"com.heroicgameslauncher.hgl"}), "/x")
            if c.key == "heroic")
        assert heroic.app.icon_theme == "com.heroicgameslauncher.hgl"
        assert heroic.app.icon is None


# ── AppSelection ──────────────────────────────────────────────────────────────

class TestAppSelection:
    def _candidates(self):
        return starter_candidates(FakeDiscovery({"steam", "heroic"}), "/x")

    def test_seeds_from_default_selected(self):
        sel = AppSelection(self._candidates())
        assert sel.count == 4
        assert all(sel.is_selected(i) for i in range(sel.count))

    def test_toggle_flips_state(self):
        sel = AppSelection(self._candidates())
        sel.toggle(0)
        assert sel.is_selected(0) is False
        sel.toggle(0)
        assert sel.is_selected(0) is True

    def test_chosen_preserves_order_and_excludes_toggled_off(self):
        cands = self._candidates()
        sel = AppSelection(cands)
        sel.toggle(1)   # drop the second candidate
        chosen = sel.chosen()
        assert chosen == [cands[0], cands[2], cands[3]]

    def test_chosen_empty_when_all_off(self):
        cands = self._candidates()
        sel = AppSelection(cands)
        for i in range(sel.count):
            sel.toggle(i)
        assert sel.chosen() == []


# ── use-case ──────────────────────────────────────────────────────────────────

class TestProvisioningUseCase:
    def test_needs_provisioning_when_not_provisioned(self):
        assert needs_provisioning(FakeProvisioning(provisioned=False)) is True

    def test_does_not_need_provisioning_once_marked(self):
        assert needs_provisioning(FakeProvisioning(provisioned=True)) is False

    def test_candidates_delegates_to_starter_list(self):
        uc = Provisioning(FakeProvisioning(), FakeDiscovery({"steam"}), "/opt/kd")
        keys = {c.key for c in uc.candidates()}
        assert keys == {"files", "youtube", "steam"}

    def test_complete_passes_exactly_the_chosen_candidates(self):
        fake = FakeProvisioning()
        uc = Provisioning(fake, FakeDiscovery(set()), "/x")
        chosen = uc.candidates()[:1]
        uc.complete(chosen)
        assert fake.received == chosen
        assert fake.is_provisioned() is True
