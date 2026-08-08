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
from tests.behavioral.harness.kd_client import KasualDesktopUnavailable, KDClient
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


def tiles(at_least: int) -> Requirement:
    def kd_has_enough_tiles(kd: KDClient | None) -> bool:
        if kd is None:
            return False
        try:
            return len(kd.snapshot()['tiles']) >= at_least
        except KasualDesktopUnavailable:
            return False

    return Requirement(
        f'Kasual Desktop has at least {at_least} tiles, so the cursor has somewhere '
        f'to move',
        kd_has_enough_tiles,
        needs_kd=True,
        remedy=f'add tiles until there are {at_least}, and run again',
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


def kd_idle() -> Requirement:
    """An app KD still believes is running changes what the pad does: over a game
    BTN_MODE follows its hold-to-recall policy, so a short press opens nothing."""
    def nothing_in_front(kd: KDClient | None) -> bool:
        if kd is None:
            return False
        try:
            return kd.snapshot()['foreground'] is None
        except KasualDesktopUnavailable:
            return False

    return Requirement(
        'Kasual Desktop has no app in the foreground',
        nothing_in_front,
        needs_kd=True,
        remedy='KD still has an app in front — wait for it to notice the app is gone, '
               'or restart KD, and run again',
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


def steam_devtools_client() -> Requirement:
    """Two PyPI packages install a module called ``websocket`` and only
    ``websocket-client`` has the functions, so the import alone proves nothing."""
    def the_real_client_is_installed(_kd: KDClient | None) -> bool:
        try:
            import websocket
        except ImportError:
            return False
        return hasattr(websocket, 'create_connection')

    return Requirement(
        'the websocket-client package is installed (Steam DevTools)',
        the_real_client_is_installed,
        remedy='pip install websocket-client — and if the stub is in the way: '
               'pip uninstall websocket',
    )


def mangohud_configured() -> Requirement:
    """KD offers the HUD toggle only where a MangoHud config exists, so a scenario
    asserting the card would otherwise fail against the machine, not against KD.
    Whether the game carries the layer is the run's own to assert."""
    def the_config_exists(_kd: KDClient | None) -> bool:
        from infrastructure.linux.hud.mangohud import MangoHudControl
        return MangoHudControl().is_available()

    return Requirement(
        'MangoHud is configured (~/.config/MangoHud/MangoHud.conf exists — KD offers '
        'the HUD toggle only then)',
        the_config_exists,
        remedy='install MangoHud and create the config: '
               'mkdir -p ~/.config/MangoHud && touch ~/.config/MangoHud/MangoHud.conf',
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
    """What each compositor needs beyond itself: on GNOME the Kasual Helper
    extension, without which a run passes against a Kasual Desktop that has no
    window manager at all; on COSMIC python-xlib, without which no game has a
    PID."""
    def session_is_equipped(_kd: KDClient | None) -> bool:
        from infrastructure.linux.compositor import Compositor, detect_compositor
        compositor = detect_compositor()
        if compositor is Compositor.GNOME:
            from infrastructure.gnome.helper import helper_present
            return helper_present()
        if compositor is Compositor.COSMIC:
            try:
                import Xlib  # noqa: F401
            except ImportError:
                return False
        return True

    return Requirement(
        'the compositor is equipped (GNOME: the Kasual Helper extension answers; '
        'COSMIC: python-xlib is importable)',
        session_is_equipped,
        remedy='GNOME: gnome-extensions enable kasual-helper@consoledesktop.org (a '
               'freshly installed extension needs a re-login on Wayland). '
               'COSMIC: install python-xlib — apt install python3-xlib, or '
               'pip install python-xlib inside the virtualenv KD runs from',
    )


BASE: tuple[Requirement, ...] = (
    kd_running(),
    kd_test_api(),
    compositor_ready(),
    writable('/dev/uinput',
             '/dev/uinput is writable (the `input` group, or a udev rule)'),
    no_physical_gamepad(),
    kd_idle(),
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
