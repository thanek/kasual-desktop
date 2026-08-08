"""Tests for the gamepad-access requirement: what it concludes from the device
nodes, and which recipe each kind of system is sent down.

The real filesystem is only touched through LinuxDeviceAccess, which is exercised
against a temporary tree of its own.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from domain.input_access.ports import NodeAccess
from domain.input_access.recipes import INSTALLED_RULE_PATH, all_recipes
from domain.input_access.requirement import (
    GamepadAccess, JOYSTICK_NODES, NO_UDEV, RULE_INSTALLED, UINPUT_NODE,
)
from domain.setup.plan import MachineProfile, Readiness
from domain.setup.readiness import SetupReadiness

_ACCESS = "infrastructure.linux.input.access"
_RULE_SOURCE = "/opt/kasual/packaging/99-kasual-desktop.rules"


class _Access:
    def __init__(
        self,
        *,
        uinput=NodeAccess.GRANTED,
        joysticks=(),
        grants=True,
        rule=True,
        udev=True,
    ):
        self._uinput = uinput
        self._joysticks = joysticks
        self._grants = grants
        self._rule = rule
        self._udev = udev

    def uinput(self):
        return self._uinput

    def joysticks(self):
        return self._joysticks

    def grants_joystick_access(self):
        return self._grants

    def access_rule_installed(self):
        return self._rule

    def udev_available(self):
        return self._udev


class _Facts:
    def machine(self):
        return MachineProfile(arch="x86_64", distro_id="fedora")

    def has_command(self, name):
        return False

    def path_exists(self, pattern):
        return False


def _assess(**kwargs):
    return GamepadAccess(_Access(**kwargs)).assess()


class TestReadingTheGamepad:
    def test_a_connected_readable_pad_is_enough(self):
        assert _assess(joysticks=(NodeAccess.GRANTED,)).met

    def test_a_connected_pad_that_cannot_be_opened_is_the_whole_problem(self):
        """evdev filters out what it cannot open, so this is the case that shows
        up as no controller at all rather than a broken one."""
        assessment = _assess(joysticks=(NodeAccess.DENIED,))
        assert not assessment.met
        assert not assessment.statuses[0].met

    def test_one_denied_pad_among_several_still_counts(self):
        assert not _assess(
            joysticks=(NodeAccess.GRANTED, NodeAccess.DENIED)).met

    def test_no_pad_connected_falls_back_to_what_the_system_grants(self):
        assert _assess(joysticks=(), grants=True).met
        assert not _assess(joysticks=(), grants=False).met

    def test_the_unconnected_case_says_it_could_not_be_tested(self):
        detail = _assess(joysticks=(), grants=False).statuses[0].detail
        assert "No controller is connected" in detail


class TestForwardingToApps:
    def test_uinput_is_required_even_when_the_pad_reads_fine(self):
        """The grab is rolled back when the virtual pad cannot be built, so a
        readable controller with no /dev/uinput is still no controller."""
        assessment = _assess(
            joysticks=(NodeAccess.GRANTED,), uinput=NodeAccess.DENIED)
        assert not assessment.met
        assert assessment.statuses[1].met is False

    def test_a_missing_node_and_a_closed_one_read_differently(self):
        missing = _assess(uinput=NodeAccess.MISSING).statuses[1]
        denied = _assess(uinput=NodeAccess.DENIED).statuses[1]
        assert missing.text != denied.text
        assert "not loaded" in missing.detail


class TestChecksTheRecipesAreWrittenAgainst:
    def test_the_two_facets_are_answered_apart(self):
        requirement = GamepadAccess(
            _Access(joysticks=(NodeAccess.GRANTED,), uinput=NodeAccess.DENIED))
        assert requirement.satisfied(JOYSTICK_NODES)
        assert not requirement.satisfied(UINPUT_NODE)

    def test_an_unrelated_check_is_not_claimed(self):
        from domain.setup.plan import Check
        assert not GamepadAccess(_Access()).satisfied(Check("other", "x"))


class TestRecipeChosen:
    def _report(self, **kwargs):
        return SetupReadiness(
            GamepadAccess(_Access(grants=False, **kwargs)),
            _Facts(),
            all_recipes(_RULE_SOURCE),
        ).report()

    def _commands(self, report):
        return [status.step.command for status in report.steps]

    def test_a_package_install_is_told_to_apply_the_rule_it_already_has(self):
        report = self._report(rule=True)
        assert "udevadm control --reload-rules" in self._commands(report)[0]

    def test_a_source_checkout_is_told_to_install_the_rule_first(self):
        report = self._report(rule=False)
        assert self._commands(report)[0] == (
            f"sudo install -Dm644 {_RULE_SOURCE} {INSTALLED_RULE_PATH}")

    def test_a_host_without_udev_falls_back_to_the_input_group(self):
        report = self._report(rule=False, udev=False)
        assert self._commands(report)[0] == "sudo usermod -aG input $USER"

    def test_no_udev_wins_over_an_installed_rule_file(self):
        """A rule nothing will ever read is not a way out."""
        report = self._report(rule=True, udev=False)
        assert self._commands(report)[0] == "sudo usermod -aG input $USER"

    def test_every_recipe_covers_uinput(self):
        for kwargs in ({"rule": True}, {"rule": False}, {"udev": False}):
            report = self._report(**kwargs)
            assert any("modprobe uinput" in c for c in self._commands(report))

    def test_the_uinput_step_re_makes_the_node_not_just_the_module(self):
        """A module already loaded before the rule landed keeps the permissions
        it was created with, so modprobe alone leaves DENIED exactly as it was
        and the card would send the user round the same loop forever."""
        for kwargs in ({"rule": True}, {"rule": False}):
            uinput = [c for c in self._commands(self._report(**kwargs))
                      if "modprobe uinput" in c]
            assert all("udevadm trigger" in c for c in uinput)

    def test_without_udev_the_node_is_fixed_by_hand(self):
        uinput = [c for c in self._commands(self._report(rule=False, udev=False))
                  if "modprobe uinput" in c]
        assert all("chmod 660 /dev/uinput" in c for c in uinput)

    def test_the_reload_reaches_the_subsystem_uinput_lives_in(self):
        """Gamepads are `input` and /dev/uinput is `misc`; a trigger naming only
        the first re-applies the rule to half of what it grants."""
        reloads = [c for c in self._commands(self._report(rule=True))
                   if "udevadm trigger" in c and "modprobe" not in c]
        assert reloads
        assert all("--subsystem-match=misc" in c for c in reloads)

    def test_a_ready_system_reports_ready(self):
        report = SetupReadiness(
            GamepadAccess(_Access(joysticks=(NodeAccess.GRANTED,))),
            _Facts(),
            all_recipes(_RULE_SOURCE),
        ).report()
        assert report.state is Readiness.READY

    def test_the_card_never_offers_to_do_it_for_you(self):
        """Every step here needs root, so there is nothing to put on a button."""
        assert self._report(rule=True).remedies == ()


class TestTraits:
    def test_the_installed_rule_shows_up_as_a_trait(self):
        assert RULE_INSTALLED in _assess(rule=True).traits
        assert RULE_INSTALLED not in _assess(rule=False).traits

    def test_a_host_without_udev_says_so(self):
        assert NO_UDEV in _assess(udev=False).traits
        assert NO_UDEV not in _assess(udev=True).traits


class TestLinuxDeviceAccess:
    """The adapter reads udev's own database rather than asking evdev, which
    would hide exactly the devices being diagnosed."""

    def _access(self):
        from infrastructure.linux.input.access import LinuxDeviceAccess
        return LinuxDeviceAccess()

    def test_a_missing_node_is_missing_not_denied(self, tmp_path):
        from infrastructure.linux.input import access
        with patch.object(access, "UINPUT_NODE", tmp_path / "absent"):
            assert self._access().uinput() is NodeAccess.MISSING

    def test_an_unwritable_node_is_denied(self, tmp_path):
        from infrastructure.linux.input import access
        node = tmp_path / "uinput"
        node.touch()
        with patch.object(access, "UINPUT_NODE", node), \
                patch(f"{_ACCESS}.os.access", return_value=False):
            assert self._access().uinput() is NodeAccess.DENIED

    def test_a_readable_writable_node_is_granted(self, tmp_path):
        from infrastructure.linux.input import access
        node = tmp_path / "uinput"
        node.touch()
        with patch.object(access, "UINPUT_NODE", node):
            assert self._access().uinput() is NodeAccess.GRANTED

    @pytest.mark.parametrize(
        "record,expected",
        [("E:ID_INPUT_JOYSTICK=1", 1),
         ("E:ID_INPUT_GAMEPAD=1", 1),
         ("E:ID_INPUT_KEYBOARD=1", 0)],
    )
    def test_only_the_devices_the_shipped_rule_matches_are_counted(
        self, tmp_path, record, expected
    ):
        """The same two properties 99-kasual-desktop.rules keys on — a keyboard
        must never be pulled into this."""
        node = tmp_path / "event0"
        node.touch()
        udev_data = tmp_path / "udev"
        udev_data.mkdir()
        (udev_data / "c13:64").write_text(f"I:1\n{record}\n")
        from infrastructure.linux.input import access
        with patch(f"{_ACCESS}.glob.glob", return_value=[str(node)]), \
                patch.object(access, "_UDEV_DATA", udev_data), \
                patch(f"{_ACCESS}.os.major", return_value=13), \
                patch(f"{_ACCESS}.os.minor", return_value=64):
            assert len(self._access().joysticks()) == expected

    def test_a_device_with_no_udev_record_is_not_a_gamepad(self, tmp_path):
        node = tmp_path / "event0"
        node.touch()
        from infrastructure.linux.input import access
        with patch(f"{_ACCESS}.glob.glob", return_value=[str(node)]), \
                patch.object(access, "_UDEV_DATA", tmp_path / "nothing"):
            assert self._access().joysticks() == ()

    def test_the_rule_is_looked_for_where_packages_and_admins_put_it(self, tmp_path):
        from infrastructure.linux.input import access
        etc = tmp_path / "etc"
        etc.mkdir()
        with patch.object(access, "_RULE_DIRECTORIES", (etc,)):
            assert not self._access().access_rule_installed()
            (etc / access.RULE_FILE).touch()
            assert self._access().access_rule_installed()

    def test_group_membership_is_a_way_in_of_its_own(self):
        from infrastructure.linux.input import access
        with patch.object(access.LinuxDeviceAccess, "access_rule_installed",
                          return_value=False), \
                patch(f"{_ACCESS}._in_input_group", return_value=True):
            assert self._access().grants_joystick_access()

    def test_a_host_without_the_input_group_does_not_crash(self):
        with patch(f"{_ACCESS}.grp.getgrnam", side_effect=KeyError):
            from infrastructure.linux.input.access import _in_input_group
            assert _in_input_group() is False


class TestShippedRuleCoversBothNodes:
    """The recipes send people to a rule file; it has to actually grant what the
    requirement checks for."""

    def _rule(self):
        return Path(__file__).parent.parent / "packaging" / "99-kasual-desktop.rules"

    def test_it_grants_joystick_event_nodes(self):
        text = self._rule().read_text()
        assert 'ENV{ID_INPUT_JOYSTICK}=="1"' in text
        assert 'ENV{ID_INPUT_GAMEPAD}=="1"' in text

    def test_it_grants_uinput(self):
        assert 'KERNEL=="uinput"' in self._rule().read_text()

    def test_it_leaves_keyboards_and_mice_alone(self):
        text = self._rule().read_text()
        assert "ID_INPUT_KEYBOARD" not in text and "ID_INPUT_MOUSE" not in text

    def test_the_package_hook_triggers_both_subsystems_the_rule_grants(self):
        """Otherwise a package install leaves /dev/uinput untouched until a
        reboot, on any machine where uinput was already loaded."""
        hook = (Path(__file__).parent.parent / "packaging" / "postinstall.sh")
        trigger = [line for line in hook.read_text().splitlines()
                   if line.lstrip().startswith("udevadm trigger")]
        assert trigger
        assert all("--subsystem-match=input" in line
                   and "--subsystem-match=misc" in line for line in trigger)
