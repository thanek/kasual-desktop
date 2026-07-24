"""What a machine must already have before a scenario can run.

A scenario declares its requirements instead of documenting them: the ones that can
be verified are checked before the run touches the screen, and all of them —
verifiable or not — are what `run.py --list` prints. The list is the documentation.

Some can only be confirmed by the person at the keyboard (a game is installed, a
YouTube session is logged in). Those are stated, never guessed at.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from tests.behavioral.harness import kd_client
from tests.behavioral.harness.kd_client import KDClient
from tests.behavioral.harness.report import ScenarioAborted, report


@dataclass(frozen=True)
class Requirement:
    description: str
    verify: Callable[[KDClient | None], bool] | None = None
    needs_kd: bool = False
    remedy: str = 'precondition not met'


def command(name: str, description: str | None = None) -> Requirement:
    return Requirement(
        description or f'{name} is installed',
        lambda _kd: shutil.which(name) is not None,
    )


def writable(path: str, description: str | None = None) -> Requirement:
    return Requirement(
        description or f'{path} is writable',
        lambda _kd: os.access(path, os.W_OK),
    )


def tile(tile_id: str, description: str | None = None) -> Requirement:
    def kd_has_the_tile(kd: KDClient | None) -> bool:
        if kd is None:
            return False
        try:
            kd.tile_index(tile_id)
        except KeyError:
            return False
        return True

    return Requirement(
        description or f'Kasual Desktop has a tile for {tile_id!r}',
        kd_has_the_tile,
        needs_kd=True,
    )


def manual(description: str) -> Requirement:
    """Something only the operator can confirm. Stated and printed, never verified."""
    return Requirement(description)


def not_running(process: str, description: str | None = None,
                remedy: str | None = None) -> Requirement:
    return Requirement(
        description or f'{process} is not running',
        lambda _kd: subprocess.run(['pgrep', '-x', process],
                                   stdout=subprocess.DEVNULL).returncode != 0,
        remedy=remedy or f'quit {process} and run again',
    )


def _physical_gamepads() -> list[str]:
    """Every pad Kasual Desktop could grab instead of the virtual one — its own
    re-emitter and the harness's test pad excluded."""
    from evdev import InputDevice, list_devices

    from infrastructure.linux.input.gamepad_watcher import (
        VIRTUAL_DEVICE_NAME, GamepadWatcher,
    )
    from tests.behavioral.harness.virtual_pad import NAME as TEST_PAD_NAME

    ours = {VIRTUAL_DEVICE_NAME, TEST_PAD_NAME}
    found = []
    for path in list_devices():
        try:
            device = InputDevice(path)
        except OSError:
            continue
        try:
            if GamepadWatcher._is_gamepad(device) and device.name not in ours:
                found.append(device.name)
        finally:
            device.close()
    return found


def no_physical_gamepad() -> Requirement:
    """Kasual Desktop grabs the first matching pad it finds; a connected physical one
    wins, and the harness's presses then reach nothing."""
    return Requirement(
        'no physical gamepad is connected — Kasual Desktop grabs the first pad it '
        'finds, and it must find the virtual one',
        lambda _kd: not _physical_gamepads(),
        remedy='disconnect the physical gamepad(s) and run again',
    )


def kd_running() -> Requirement:
    """Read from the single-instance lock, so this sees the packaged KD too."""
    return Requirement(
        'Kasual Desktop is running',
        lambda _kd: kd_client.running_pid() is not None,
        remedy='start it with: KD_TEST_API=1 ./kasual.sh',
    )


def kd_test_api() -> Requirement:
    """The running KD must be one that answers.

    KD publishes the API only under KD_TEST_API=1, and the packaged instance started
    from the menu is not that one — nothing about it looks wrong, it simply never
    answers.
    """
    return Requirement(
        'its test API answers, and answers with what this harness reads',
        lambda _kd: kd_client.test_api_answers(),
        remedy='the running Kasual Desktop was started without the test API, or it '
               'predates the API this harness expects — quit it and start: '
               'KD_TEST_API=1 ./kasual.sh',
    )


def window_source() -> Requirement:
    """For scenarios that watch a splash, a launcher or a game — everything else in the
    harness reads the pad and KD, which need no backend at all."""
    def a_backend_exists(_kd: KDClient | None) -> bool:
        from tests.behavioral.harness.window_source import backend
        return backend() is not None

    return Requirement(
        'the harness can read this compositor\'s windows',
        a_backend_exists,
        remedy='no window backend for this compositor yet — see '
               'tests/behavioral/PORTING.md',
    )


def _running(compositor_name: str) -> bool:
    from infrastructure.linux.compositor import Compositor, detect_compositor
    return detect_compositor() is Compositor(compositor_name)


def hyprland() -> Requirement:
    """A Hyprland session with its CLI — the window source reads `hyprctl -j` and the
    `socket2` stream keyed by `HYPRLAND_INSTANCE_SIGNATURE`."""
    return Requirement(
        'a Hyprland session (HYPRLAND_INSTANCE_SIGNATURE and hyprctl)',
        lambda _kd: _running('hyprland') and shutil.which('hyprctl') is not None,
        remedy='run this on a Hyprland session with hyprctl on PATH',
    )


def sway() -> Requirement:
    """A Sway session with its CLI — the window source reads `swaymsg -t get_tree` and
    subscribes to `window` events over `SWAYSOCK`."""
    return Requirement(
        'a Sway session (SWAYSOCK and swaymsg)',
        lambda _kd: _running('sway') and shutil.which('swaymsg') is not None,
        remedy='run this on a Sway session with swaymsg on PATH',
    )


def cosmic() -> Requirement:
    """A COSMIC session — the window source speaks cosmic-comp's toplevel protocols
    over the Wayland display socket, so there is no CLI to look for."""
    return Requirement(
        'a COSMIC session (cosmic-comp on the Wayland display socket)',
        lambda _kd: _running('cosmic') and bool(os.environ.get('WAYLAND_DISPLAY')),
        remedy='run this on a COSMIC session',
    )


def compositor_ready() -> Requirement:
    """On GNOME, without the Kasual Helper extension a run would not fail — it would
    pass against a Kasual Desktop that has no window manager and no way to stay on
    screen."""
    def session_is_equipped(_kd: KDClient | None) -> bool:
        from infrastructure.linux.compositor import Compositor, detect_compositor
        if detect_compositor() is not Compositor.GNOME:
            return True
        from infrastructure.gnome.helper import helper_present
        return helper_present()

    return Requirement(
        'the compositor is equipped (on GNOME: the Kasual Helper extension answers)',
        session_is_equipped,
        remedy='enable it: gnome-extensions enable kasual-helper@consoledesktop.org '
               '(a freshly installed extension needs a re-login on Wayland)',
    )


BASE: tuple[Requirement, ...] = (
    kd_running(),
    kd_test_api(),
    compositor_ready(),
    writable('/dev/uinput',
             '/dev/uinput is writable (the `input` group, or a udev rule)'),
    no_physical_gamepad(),
)


def check(requirements: Sequence[Requirement], kd: KDClient | None) -> None:
    """Verify what can be verified now. Without *kd*, only the requirements that do
    not need it — so a missing Steam is caught before the operator is asked to start
    Kasual Desktop."""
    for requirement in requirements:
        if requirement.verify is None:
            if kd is None:
                report(requirement.description, 'INFO', 'confirm this yourself')
            continue
        if requirement.needs_kd != (kd is not None):
            continue
        if requirement.verify(kd):
            report(requirement.description, 'PASS')
        else:
            report(requirement.description, 'FAIL', requirement.remedy)
            raise ScenarioAborted(f'precondition not met: {requirement.description}')
