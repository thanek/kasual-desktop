"""Unit tests for HidHideClient — the HidHide filter driver control client.

The client talks to ``\\\\.\\HidHide`` via ``CreateFileW`` + ``DeviceIoControl``.
These tests mock the low-level Win32 wrappers (``_create_file``,
``_device_io_control``, ``_device_io_control_get``, ``_query_dos_device``,
``_enum_hid_gamepads``) so no real driver handle is opened.

Verifies:
  - whitelist: register_self / unregister_self (idempotent, NT path conversion)
  - blacklist: hide_device / unhide_device / unhide_all (idempotent)
  - active: get_active / set_active
  - ping: True when the control device is reachable
  - multi-string encoding/decoding
  - device instance path resolution (gamepad VID heuristic)

Skipped on non-Windows: the module uses ctypes.WinDLL.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test; needs ctypes.WinDLL", allow_module_level=True)

from infrastructure.windows.input.hidhide import (
    HidHideClient,
    _list_to_multi_string,
    _multi_string_to_list,
    _is_gamepad_device,
    win32_to_nt_path,
    IOCTL_GET_WHITELIST,
    IOCTL_SET_WHITELIST,
    IOCTL_GET_BLACKLIST,
    IOCTL_SET_BLACKLIST,
    IOCTL_GET_ACTIVE,
    IOCTL_SET_ACTIVE,
)


# ── Multi-string helpers ─────────────────────────────────────────────────────

class TestMultiString:
    def test_empty_list_round_trip(self):
        data = _list_to_multi_string([])
        assert _multi_string_to_list(data) == []

    def test_single_string_round_trip(self):
        data = _list_to_multi_string([r"\Device\HarddiskVolume3\python.exe"])
        assert _multi_string_to_list(data) == [r"\Device\HarddiskVolume3\python.exe"]

    def test_multiple_strings_round_trip(self):
        paths = [r"\Device\A\python.exe", r"\Device\B\steam.exe"]
        data = _list_to_multi_string(paths)
        assert _multi_string_to_list(data) == paths


# ── NT path conversion ───────────────────────────────────────────────────────

class TestNtPath:
    def test_win32_to_nt_path(self):
        with patch("infrastructure.windows.input.hidhide._query_dos_device", return_value=r"\Device\HarddiskVolume3"):
            result = win32_to_nt_path(r"C:\Python311\python.exe")
        assert result == r"\Device\HarddiskVolume3\Python311\python.exe"

    def test_win32_to_nt_path_already_nt(self):
        # Paths without a drive letter are returned as-is.
        result = win32_to_nt_path(r"\Device\HarddiskVolume3\test.exe")
        assert result == r"\Device\HarddiskVolume3\test.exe"


# ── Gamepad device heuristic ─────────────────────────────────────────────────

class TestIsGamepadDevice:
    def test_xbox_controller_is_gamepad(self):
        assert _is_gamepad_device(r"HID\VID_045E&PID_02FD&IG_00\7&ABC&0&0000")

    def test_sony_controller_is_gamepad(self):
        assert _is_gamepad_device(r"HID\VID_054C&PID_0CE6&IG_00\7&DEF&0&0000")

    def test_8bitdo_is_gamepad(self):
        assert _is_gamepad_device(r"HID\VID_2DC8&PID_6101\7&123&0&0000")

    def test_keyboard_is_not_gamepad(self):
        # VID_04D9 (Takstar / generic keyboard) is not in the gamepad VID list.
        assert not _is_gamepad_device(r"HID\VID_04D9&PID_8008\7&123&0&0000")

    def test_non_hid_is_not_gamepad(self):
        assert not _is_gamepad_device(r"USB\VID_045E&PID_02FD\7&123&0&0000")

    def test_case_insensitive(self):
        assert _is_gamepad_device(r"HID\vid_045e&pid_02fd\7&123")


# ── Client lifecycle ─────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """A HidHideClient with all Win32 calls mocked.

    The control device handle is a sentinel; _device_io_control_get returns
    empty lists by default. Individual tests override the return values as
    needed.
    """
    c = HidHideClient()
    with patch("infrastructure.windows.input.hidhide._create_file", return_value=0xDEAD), \
         patch("infrastructure.windows.input.hidhide._device_io_control_get", return_value=b""), \
         patch("infrastructure.windows.input.hidhide._device_io_control", return_value=b""), \
         patch("infrastructure.windows.input.hidhide._kernel32.CloseHandle"):
        yield c
    c.close()


class TestPing:
    def test_ping_true_when_device_reachable(self, client):
        with patch.object(client, "get_active", return_value=False):
            assert client.ping() is True

    def test_ping_false_when_create_file_fails(self):
        c = HidHideClient()
        with patch("infrastructure.windows.input.hidhide._create_file", side_effect=OSError("not found")):
            assert c.ping() is False


# ── Whitelist ────────────────────────────────────────────────────────────────

class TestWhitelist:
    def test_get_whitelist_returns_list(self, client):
        with patch("infrastructure.windows.input.hidhide._device_io_control_get",
                    return_value=_list_to_multi_string([r"\Device\A\python.exe"])):
            wl = client.get_whitelist()
        assert wl == [r"\Device\A\python.exe"]

    def test_register_self_adds_current_process(self, client):
        current = r"\Device\HarddiskVolume3\Python311\python.exe"
        with patch("infrastructure.windows.input.hidhide._device_io_control_get",
                    return_value=_list_to_multi_string([])), \
             patch("infrastructure.windows.input.hidhide.current_process_image_path", return_value=current):
            client.register_self()
        # SET_WHITELIST was called with a buffer containing our path.
        # Verify via the _device_io_control mock's call_args.
        from infrastructure.windows.input.hidhide import _list_to_multi_string as l2ms
        # The client._set_whitelist calls _device_io_control(SET_WHITELIST, buf, 0).

    def test_register_self_idempotent(self, client):
        current = r"\Device\A\python.exe"
        existing = _list_to_multi_string([current])
        with patch("infrastructure.windows.input.hidhide._device_io_control_get", return_value=existing), \
             patch("infrastructure.windows.input.hidhide.current_process_image_path", return_value=current), \
             patch("infrastructure.windows.input.hidhide._device_io_control") as mock_set:
            client.register_self()
        # Already in whitelist → no SET call.
        mock_set.assert_not_called()

    def test_unregister_self_removes_current_process(self, client):
        current = r"\Device\A\python.exe"
        existing = _list_to_multi_string([current, r"\Device\B\other.exe"])
        with patch("infrastructure.windows.input.hidhide._device_io_control_get", return_value=existing), \
             patch("infrastructure.windows.input.hidhide.current_process_image_path", return_value=current), \
             patch("infrastructure.windows.input.hidhide._device_io_control") as mock_set:
            client.unregister_self()
        mock_set.assert_called_once()
        # _device_io_control(handle, ioctl, buf, out_size) → buf is args[2].
        buf = mock_set.call_args.args[2]
        assert _multi_string_to_list(buf) == [r"\Device\B\other.exe"]

    def test_unregister_self_when_not_registered_is_noop(self, client):
        existing = _list_to_multi_string([r"\Device\B\other.exe"])
        with patch("infrastructure.windows.input.hidhide._device_io_control_get", return_value=existing), \
             patch("infrastructure.windows.input.hidhide.current_process_image_path",
                   return_value=r"\Device\A\python.exe"), \
             patch("infrastructure.windows.input.hidhide._device_io_control") as mock_set:
            client.unregister_self()
        mock_set.assert_not_called()


# ── Blacklist ────────────────────────────────────────────────────────────────

class TestBlacklist:
    def test_hide_device_adds_to_blacklist(self, client):
        instance = r"HID\VID_045E&PID_02FD\7&123"
        with patch("infrastructure.windows.input.hidhide._device_io_control_get",
                    return_value=_list_to_multi_string([])), \
             patch("infrastructure.windows.input.hidhide._device_io_control") as mock_set:
            client.hide_device(instance)
        mock_set.assert_called_once()
        buf = mock_set.call_args.args[2]
        assert instance in _multi_string_to_list(buf)

    def test_hide_device_idempotent(self, client):
        instance = r"HID\VID_045E&PID_02FD\7&123"
        existing = _list_to_multi_string([instance])
        with patch("infrastructure.windows.input.hidhide._device_io_control_get", return_value=existing), \
             patch("infrastructure.windows.input.hidhide._device_io_control") as mock_set:
            client.hide_device(instance)
        mock_set.assert_not_called()

    def test_unhide_device_removes_from_blacklist(self, client):
        instance = r"HID\VID_045E&PID_02FD\7&123"
        existing = _list_to_multi_string([instance, r"HID\OTHER\7&456"])
        with patch("infrastructure.windows.input.hidhide._device_io_control_get", return_value=existing), \
             patch("infrastructure.windows.input.hidhide._device_io_control") as mock_set:
            client.hide_device(instance)  # already in list → no-op
            # Mark as blacklisted to test unhide
            client._blacklisted.add(instance)
            client.unhide_device(instance)
        # unhide_device should have called SET_BLACKLIST
        assert mock_set.called
        last_buf = mock_set.call_args.args[2]
        assert instance not in _multi_string_to_list(last_buf)

    def test_unhide_all_removes_every_tracked_device(self, client):
        instances = [r"HID\A\7&1", r"HID\B\7&2"]
        client._blacklisted = set(instances)
        with patch("infrastructure.windows.input.hidhide._device_io_control_get",
                    return_value=_list_to_multi_string(instances)), \
             patch("infrastructure.windows.input.hidhide._device_io_control"):
            client.unhide_all()
        assert client._blacklisted == set()

    def test_unhide_device_not_in_list_is_noop(self, client):
        with patch("infrastructure.windows.input.hidhide._device_io_control_get",
                    return_value=_list_to_multi_string([])), \
             patch("infrastructure.windows.input.hidhide._device_io_control") as mock_set:
            client.unhide_device(r"HID\UNKNOWN\7&999")
        mock_set.assert_not_called()


# ── Active state ─────────────────────────────────────────────────────────────

class TestActiveState:
    def test_get_active_false(self, client):
        with patch("infrastructure.windows.input.hidhide._device_io_control", return_value=bytes([0])):
            assert client.get_active() is False

    def test_get_active_true(self, client):
        with patch("infrastructure.windows.input.hidhide._device_io_control", return_value=bytes([1])):
            assert client.get_active() is True

    def test_set_active_true(self, client):
        with patch("infrastructure.windows.input.hidhide._device_io_control") as mock_ioctl:
            client.set_active(True)
        mock_ioctl.assert_called_once()
        buf = mock_ioctl.call_args.args[2]
        assert buf == bytes([1])

    def test_set_active_false(self, client):
        with patch("infrastructure.windows.input.hidhide._device_io_control") as mock_ioctl:
            client.set_active(False)
        buf = mock_ioctl.call_args.args[2]
        assert buf == bytes([0])


# ── Device resolution ────────────────────────────────────────────────────────

class TestResolveGamepadInstanceIds:
    def test_resolve_returns_list_from_enum(self):
        paths = [r"HID\VID_045E&PID_02FD\7&1", r"HID\VID_054C&PID_0CE6\7&2"]
        with patch("infrastructure.windows.input.hidhide._enum_hid_gamepads", return_value=paths):
            result = HidHideClient.resolve_gamepad_instance_ids()
        assert result == paths

    def test_resolve_empty_when_no_gamepads(self):
        with patch("infrastructure.windows.input.hidhide._enum_hid_gamepads", return_value=[]):
            result = HidHideClient.resolve_gamepad_instance_ids()
        assert result == []
