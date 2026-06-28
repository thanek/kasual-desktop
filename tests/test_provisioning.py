"""Tests for the pure provisioning domain: catalog, selection, use-case."""

from domain.catalog.app import App
from domain.provisioning.add_apps import AppAdder
from domain.provisioning.candidate import CandidateApp
from domain.provisioning.catalog import (
    order_for_adding, starter_candidates, unpinned_candidates,
)
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


# ── unpinned_candidates (the add-app picker filter) ─────────────────────────────

class TestUnpinnedCandidates:
    def _candidates(self):
        return starter_candidates(FakeDiscovery({"steam", "heroic"}), "/opt/kd")

    def test_drops_already_pinned_by_launch_command(self):
        cands = self._candidates()
        # An existing Steam tile (same command/args) filters the Steam candidate out.
        existing = [App(name="Steam", command="steam",
                        args=("steam://open/bigpicture",))]
        keys = {c.key for c in unpinned_candidates(cands, existing)}
        assert "steam" not in keys
        assert {"files", "youtube", "heroic"} <= keys

    def test_keeps_all_when_catalog_empty(self):
        cands = self._candidates()
        assert unpinned_candidates(cands, []) == cands

    def test_matches_bundled_apps_by_absolute_command_path(self):
        cands = self._candidates()
        existing = [App(name="File Browser",
                        command="/opt/kd/apps/file_browser/file_browser.sh")]
        keys = {c.key for c in unpinned_candidates(cands, existing)}
        assert "files" not in keys

    def test_same_command_different_args_is_not_a_match(self):
        cands = self._candidates()
        # A bare `steam` tile must not mask the bigpicture Steam candidate.
        existing = [App(name="Steam", command="steam")]
        keys = {c.key for c in unpinned_candidates(cands, existing)}
        assert "steam" in keys


# ── order_for_adding (well-known launchers first) ───────────────────────────────

class TestOrderForAdding:
    def _cand(self, key, name, command=None):
        return CandidateApp(key, App(name=name, command=command or key),
                            order=0, default_selected=False)

    def test_well_known_lead_in_listed_order(self):
        out = order_for_adding([
            self._cand("gimp", "GIMP"),
            self._cand("heroic", "Heroic"),
            self._cand("steam", "Steam"),
        ])
        # Steam precedes Heroic (its _WELL_KNOWN order), both before plain apps.
        assert [c.key for c in out] == ["steam", "heroic", "gimp"]

    def test_rest_sorted_alphabetically_after(self):
        out = order_for_adding([
            self._cand("zed", "Zed"),
            self._cand("ark", "Ark"),
            self._cand("steam", "Steam"),
        ])
        assert [c.key for c in out] == ["steam", "ark", "zed"]

    def test_matches_well_known_by_flatpak_id(self):
        out = order_for_adding([
            self._cand("aaa", "Aaa"),
            self._cand("com.valvesoftware.Steam", "Steam", command="/usr/bin/flatpak"),
        ])
        assert out[0].key == "com.valvesoftware.Steam"

    def test_no_well_known_is_plain_alphabetical(self):
        out = order_for_adding([self._cand("b", "Beta"), self._cand("a", "Alpha")])
        assert [c.app.name for c in out] == ["Alpha", "Beta"]


# ── AppAdder (add apps after first run) ─────────────────────────────────────────

class FakeInstalledApps:
    """An InstalledApps returning a fixed candidate list."""

    def __init__(self, candidates):
        self._candidates = list(candidates)

    def scan(self):
        return list(self._candidates)


class TestAppAdder:
    def _candidates(self):
        return starter_candidates(FakeDiscovery({"steam", "heroic"}), "/opt/kd")

    def test_available_excludes_already_pinned(self):
        adder = AppAdder(FakeInstalledApps(self._candidates()), FakeProvisioning(True))
        existing = [App(name="Steam", command="steam",
                        args=("steam://open/bigpicture",))]
        keys = {c.key for c in adder.available(existing)}
        assert "steam" not in keys and "heroic" in keys

    def test_available_is_everything_when_nothing_pinned(self):
        cands = self._candidates()
        adder = AppAdder(FakeInstalledApps(cands), FakeProvisioning(True))
        # Same set (nothing filtered), though re-ordered well-known-first.
        assert {c.key for c in adder.available([])} == {c.key for c in cands}

    def test_available_orders_well_known_first(self):
        cands = self._candidates()   # includes steam + heroic
        adder = AppAdder(FakeInstalledApps(cands), FakeProvisioning(True))
        keys = [c.key for c in adder.available([])]
        assert keys[:2] == ["steam", "heroic"]

    def test_add_persists_chosen(self):
        fake = FakeProvisioning(provisioned=True)
        cands = self._candidates()
        adder = AppAdder(FakeInstalledApps(cands), fake)
        adder.add(cands[:2])
        assert fake.received == cands[:2]
