"""Tests for recipe matching and for the shipped recipe set's structure."""

from pathlib import PurePosixPath

from domain.drm.plan import (
    Check, CheckKind, MachineProfile, Recipe, Step, recipe_for,
)
from domain.drm.recipes import all_recipes

_PACKAGE_MANAGERS = {"apt", "apt-get", "dnf", "flatpak", "pacman", "rpm-ostree",
                     "zypper"}


def _recipe(key, arch=(), distros=(), traits=()) -> Recipe:
    return Recipe(
        key=key,
        notice="notice",
        steps=(Step("t", "i", Check(CheckKind.CDM)),),
        arch=arch,
        distros=distros,
        traits=traits,
    )


def _tool(command: str) -> str:
    words = command.split()
    return words[1] if words[0] == "sudo" else words[0]


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

    def test_a_trait_keeps_a_recipe_away_from_machines_without_it(self):
        ostree = _recipe("ostree", traits=("ostree",))
        classic = _recipe("classic")
        recipes = (ostree, classic)
        assert recipe_for(MachineProfile(arch="x86_64"), recipes) is classic
        booted = MachineProfile(arch="x86_64", traits=("ostree",))
        assert recipe_for(booted, recipes) is ostree

    def test_a_recipe_needs_every_trait_it_names(self):
        both = _recipe("both", traits=("ostree", "raspberrypi"))
        machine = MachineProfile(arch="aarch64", traits=("ostree",))
        assert recipe_for(machine, (both,)) is None


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

    def test_a_command_check_follows_a_command_that_installs_it(self):
        """A step verified by "is X on PATH" needs a command that puts it there:
        one that only downloads files can never tick its own box."""
        for recipe in all_recipes():
            for step in recipe.steps:
                if step.check.kind is CheckKind.COMMAND and step.command:
                    assert _tool(step.command) in _PACKAGE_MANAGERS, recipe.key
                    assert step.check.value in step.command, recipe.key

    def test_a_path_check_names_the_location_its_command_writes_to(self):
        for recipe in all_recipes():
            for step in recipe.steps:
                if step.check.kind is CheckKind.PATH:
                    location = str(PurePosixPath(step.check.value).parent)
                    assert location in step.command, recipe.key


class TestShippedSelection:
    def test_an_immutable_fedora_layers_the_installer_instead_of_installing_it(self):
        machine = MachineProfile(arch="aarch64", distro_id="fedora",
                                 traits=("ostree",))
        assert recipe_for(machine, all_recipes()).key == "fedora-arm-ostree"

    def test_a_classic_fedora_keeps_the_dnf_recipe(self):
        machine = MachineProfile(arch="aarch64", distro_id="fedora")
        assert recipe_for(machine, all_recipes()).key == "fedora-arm"

    def test_an_immutable_x86_system_is_sent_to_flathub(self):
        machine = MachineProfile(arch="x86_64", distro_id="bazzite",
                                 like=("fedora",), traits=("ostree",))
        assert recipe_for(machine, all_recipes()).key == "intel-ostree"

    def test_a_raspberry_pi_gets_its_one_package(self):
        machine = MachineProfile(arch="aarch64", distro_id="debian",
                                 traits=("raspberrypi",))
        assert recipe_for(machine, all_recipes()).key == "raspberrypi-arm"

    def test_debian_on_other_arm_hardware_gets_the_installer_script(self):
        machine = MachineProfile(arch="aarch64", distro_id="debian")
        assert recipe_for(machine, all_recipes()).key == "generic-arm"
