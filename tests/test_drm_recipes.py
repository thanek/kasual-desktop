"""Tests for recipe matching and for the shipped recipe set's structure."""

from domain.drm.plan import (
    Check, CheckKind, MachineProfile, Recipe, Step, recipe_for,
)
from domain.drm.recipes import all_recipes


def _recipe(key, arch=(), distros=()) -> Recipe:
    return Recipe(
        key=key,
        notice="notice",
        steps=(Step("t", "i", Check(CheckKind.CDM)),),
        arch=arch,
        distros=distros,
    )


class TestMatching:
    def test_matches_on_architecture(self):
        arm = _recipe("arm", arch=("aarch64",))
        intel = _recipe("intel", arch=("x86_64",))
        machine = MachineProfile(arch="x86_64")
        assert recipe_for(machine, (arm, intel)) is intel

    def test_matches_on_distro_id(self):
        fedora = _recipe("fedora", distros=("fedora",))
        machine = MachineProfile(arch="aarch64", distro_id="fedora")
        assert recipe_for(machine, (fedora,)) is fedora

    def test_derivative_matches_through_id_like(self):
        debian = _recipe("debian", distros=("debian",))
        machine = MachineProfile(
            arch="x86_64", distro_id="pop", like=("ubuntu", "debian"))
        assert recipe_for(machine, (debian,)) is debian

    def test_specific_recipe_wins_over_the_family_it_precedes(self):
        pop = _recipe("pop", distros=("pop",))
        debian = _recipe("debian", distros=("debian",))
        machine = MachineProfile(
            arch="x86_64", distro_id="pop", like=("ubuntu", "debian"))
        assert recipe_for(machine, (pop, debian)) is pop

    def test_empty_fields_match_any_machine(self):
        generic = _recipe("generic")
        assert recipe_for(MachineProfile(arch="riscv64"), (generic,)) is generic

    def test_no_match_returns_none(self):
        arm = _recipe("arm", arch=("aarch64",))
        assert recipe_for(MachineProfile(arch="x86_64"), (arm,)) is None

    def test_distro_must_match_alongside_architecture(self):
        fedora_arm = _recipe("fedora-arm", arch=("aarch64",), distros=("fedora",))
        machine = MachineProfile(arch="aarch64", distro_id="debian")
        assert recipe_for(machine, (fedora_arm,)) is None


class TestShippedRecipes:
    """Structural guards, so a recipe added later cannot produce a checklist
    that verifies nothing or omits the licence notice."""

    def test_every_recipe_ends_in_the_cdm_check(self):
        for recipe in all_recipes():
            assert recipe.steps, recipe.key
            assert recipe.steps[-1].check.kind is CheckKind.CDM, recipe.key

    def test_every_recipe_carries_a_notice(self):
        for recipe in all_recipes():
            assert recipe.notice.strip(), recipe.key

    def test_every_step_is_described(self):
        for recipe in all_recipes():
            for step in recipe.steps:
                assert step.title.strip(), recipe.key
                assert step.instruction.strip(), recipe.key

    def test_keys_are_unique(self):
        keys = [recipe.key for recipe in all_recipes()]
        assert len(keys) == len(set(keys))

    def test_command_and_path_checks_name_a_target(self):
        for recipe in all_recipes():
            for step in recipe.steps:
                if step.check.kind is not CheckKind.CDM:
                    assert step.check.value, recipe.key

    def test_this_machine_resolves_to_a_recipe(self):
        machine = MachineProfile(arch="aarch64", distro_id="fedora")
        assert recipe_for(machine, all_recipes()) is not None
