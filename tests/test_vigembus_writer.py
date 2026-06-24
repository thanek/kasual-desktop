"""Unit tests for VigemWriter — the ViGEmBus virtual Xbox360 pad writer.

The writer talks to ``ViGEmClient.dll`` via ctypes. These tests mock the DLL
at the ``_load_vigem_dll`` / ``_setup_prototypes`` seam so no real DLL or
driver is needed. They verify:

  - Button press/release → correct XUSB bitmask set/cleared in the report
  - Guide button → XUSB_GAMEPAD_GUIDE bit pulse
  - Axis normalisation: pygame -1..1 → ViGEm s16 (-32768..32767) / u8 (0..255)
  - Y-axis inversion (pygame positive=down, XInput positive=up)
  - D-pad (hat) → individual XUSB D-pad buttons
  - connect/disconnect lifecycle (alloc/connect/target_add/target_remove)
  - syn() is a no-op

Skipped on non-Windows: the writer uses ctypes.WinDLL (Windows-only).
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test; needs ctypes.WinDLL", allow_module_level=True)

from infrastructure.windows.input.vigembus_writer import (
    PG_BTN_EAST, PG_BTN_NORTH, PG_BTN_SELECT, PG_BTN_SOUTH, PG_BTN_START,
    PG_BTN_TL, PG_BTN_TR, PG_BTN_WEST,
    VIGEM_ERROR_NONE,
    XUSB_GAMEPAD_A, XUSB_GAMEPAD_B, XUSB_GAMEPAD_BACK, XUSB_GAMEPAD_GUIDE,
    XUSB_GAMEPAD_LEFT_SHOULDER, XUSB_GAMEPAD_RIGHT_SHOULDER, XUSB_GAMEPAD_START,
    XUSB_GAMEPAD_X, XUSB_GAMEPAD_Y,
    XUSB_GAMEPAD_DPAD_UP, XUSB_GAMEPAD_DPAD_DOWN,
    XUSB_GAMEPAD_DPAD_LEFT, XUSB_GAMEPAD_DPAD_RIGHT,
    XUSB_REPORT,
    VigemWriter,
)


def _mock_dll():
    """A mock ViGEmClient.dll with the C API functions as MagicMocks.

    alloc/connect return sentinel values; target_add returns VIGEM_ERROR_NONE.
    """
    dll = MagicMock()
    dll.vigem_alloc.return_value = 0x1000
    dll.vigem_connect.return_value = VIGEM_ERROR_NONE
    dll.vigem_target_x360_alloc.return_value = 0x2000
    dll.vigem_target_add.return_value = VIGEM_ERROR_NONE
    return dll


@pytest.fixture
def writer():
    """A connected VigemWriter backed by a mock DLL.

    Patches ``_load_vigem_dll`` and ``_setup_prototypes`` so no real DLL is
    loaded. The mock DLL is accessible via ``writer._dll``.
    """
    dll = _mock_dll()
    with patch("infrastructure.windows.input.vigembus_writer._load_vigem_dll", return_value=dll), \
         patch("infrastructure.windows.input.vigembus_writer._setup_prototypes"):
        w = VigemWriter()
        w.connect()
    return w


# ── Lifecycle ────────────────────────────────────────────────────────────────

class TestLifecycle:
    def test_connect_allocs_client_and_target(self, writer):
        writer._dll.vigem_alloc.assert_called_once()
        writer._dll.vigem_connect.assert_called_once_with(0x1000)
        writer._dll.vigem_target_x360_alloc.assert_called_once()
        writer._dll.vigem_target_add.assert_called_once_with(0x1000, 0x2000)
        assert writer.is_connected

    def test_connect_raises_on_bus_not_found(self):
        """If vigem_connect fails, connect() raises and cleans up."""
        dll = _mock_dll()
        dll.vigem_connect.return_value = 0xE0000001  # BUS_NOT_FOUND
        with patch("infrastructure.windows.input.vigembus_writer._load_vigem_dll", return_value=dll), \
             patch("infrastructure.windows.input.vigembus_writer._setup_prototypes"):
            w = VigemWriter()
            with pytest.raises(RuntimeError, match="vigem_connect"):
                w.connect()
        assert not w.is_connected

    def test_connect_raises_on_target_add_failure(self):
        dll = _mock_dll()
        dll.vigem_target_add.return_value = 0xE0000002  # NO_FREE_SLOT
        with patch("infrastructure.windows.input.vigembus_writer._load_vigem_dll", return_value=dll), \
             patch("infrastructure.windows.input.vigembus_writer._setup_prototypes"):
            w = VigemWriter()
            with pytest.raises(RuntimeError, match="vigem_target_add"):
                w.connect()
        assert not w.is_connected

    def test_disconnect_removes_target_and_frees_client(self, writer):
        writer.disconnect()
        writer._dll.vigem_target_remove.assert_called_once_with(0x1000, 0x2000)
        writer._dll.vigem_target_free.assert_called_once_with(0x2000)
        writer._dll.vigem_disconnect.assert_called_once_with(0x1000)
        writer._dll.vigem_free.assert_called_once_with(0x1000)
        assert not writer.is_connected

    def test_disconnect_is_idempotent(self, writer):
        writer.disconnect()
        writer.disconnect()  # should not raise
        # Second call should not re-call target_remove (target is None).
        assert writer._dll.vigem_target_remove.call_count == 1

    def test_disconnect_without_connect_is_noop(self):
        w = VigemWriter()
        w.disconnect()  # should not raise


# ── Button writes ────────────────────────────────────────────────────────────

class TestButtonWrites:
    def test_south_press_sets_a_bit(self, writer):
        writer.write_button(PG_BTN_SOUTH, 1)
        assert writer.report.wButtons & XUSB_GAMEPAD_A

    def test_south_release_clears_a_bit(self, writer):
        writer.write_button(PG_BTN_SOUTH, 1)
        writer.write_button(PG_BTN_SOUTH, 0)
        assert not (writer.report.wButtons & XUSB_GAMEPAD_A)

    def test_east_press_sets_b_bit(self, writer):
        writer.write_button(PG_BTN_EAST, 1)
        assert writer.report.wButtons & XUSB_GAMEPAD_B

    def test_west_press_sets_x_bit(self, writer):
        writer.write_button(PG_BTN_WEST, 1)
        assert writer.report.wButtons & XUSB_GAMEPAD_X

    def test_north_press_sets_y_bit(self, writer):
        writer.write_button(PG_BTN_NORTH, 1)
        assert writer.report.wButtons & XUSB_GAMEPAD_Y

    def test_tl_press_sets_left_shoulder(self, writer):
        writer.write_button(PG_BTN_TL, 1)
        assert writer.report.wButtons & XUSB_GAMEPAD_LEFT_SHOULDER

    def test_tr_press_sets_right_shoulder(self, writer):
        writer.write_button(PG_BTN_TR, 1)
        assert writer.report.wButtons & XUSB_GAMEPAD_RIGHT_SHOULDER

    def test_select_press_sets_back(self, writer):
        writer.write_button(PG_BTN_SELECT, 1)
        assert writer.report.wButtons & XUSB_GAMEPAD_BACK

    def test_start_press_sets_start(self, writer):
        writer.write_button(PG_BTN_START, 1)
        assert writer.report.wButtons & XUSB_GAMEPAD_START

    def test_unknown_button_is_ignored(self, writer):
        writer.write_button(99, 1)  # no mapping → no-op
        assert writer.report.wButtons == 0

    def test_flush_sends_update(self, writer):
        writer.write_button(PG_BTN_SOUTH, 1)
        writer._dll.vigem_target_x360_update.assert_called()
        # The update call receives the report struct.
        call_args = writer._dll.vigem_target_x360_update.call_args
        report = call_args.args[2]
        assert isinstance(report, XUSB_REPORT)
        assert report.wButtons & XUSB_GAMEPAD_A


# ── Guide button ─────────────────────────────────────────────────────────────

class TestGuideButton:
    def test_set_guide_true_sets_guide_bit(self, writer):
        writer.set_guide(True)
        assert writer.report.wButtons & XUSB_GAMEPAD_GUIDE

    def test_set_guide_false_clears_guide_bit(self, writer):
        writer.set_guide(True)
        writer.set_guide(False)
        assert not (writer.report.wButtons & XUSB_GAMEPAD_GUIDE)

    def test_guide_pulse_emits_two_updates(self, writer):
        writer.set_guide(True)
        writer.set_guide(False)
        assert writer._dll.vigem_target_x360_update.call_count == 2


# ── Axis normalisation ───────────────────────────────────────────────────────

class TestAxisWrites:
    def test_left_stick_x_full_right(self, writer):
        writer.write_axis(0, 1.0)
        assert writer.report.sThumbLX == 32767

    def test_left_stick_x_full_left(self, writer):
        writer.write_axis(0, -1.0)
        assert writer.report.sThumbLX == -32768

    def test_left_stick_y_full_up(self, writer):
        # pygame Y: -1 = up. XInput Y: +32767 = up. So -1 → +32767 (inverted).
        writer.write_axis(1, -1.0)
        assert writer.report.sThumbLY == 32767

    def test_left_stick_y_full_down(self, writer):
        # pygame Y: 1 = down. XInput Y: -32768 = down. So 1 → -32768.
        writer.write_axis(1, 1.0)
        assert writer.report.sThumbLY == -32768

    def test_right_stick_x(self, writer):
        writer.write_axis(2, 0.5)
        assert writer.report.sThumbRX == 16384

    def test_right_stick_y_inverted(self, writer):
        writer.write_axis(3, -1.0)
        assert writer.report.sThumbRY == 32767

    def test_left_trigger_rest(self, writer):
        # pygame trigger: -1 = rest. XInput trigger: 0 = rest.
        writer.write_axis(4, -1.0)
        assert writer.report.bLeftTrigger == 0

    def test_left_trigger_full(self, writer):
        # pygame trigger: 1 = fully pressed. XInput trigger: 255 = full.
        writer.write_axis(4, 1.0)
        assert writer.report.bLeftTrigger == 255

    def test_right_trigger_half(self, writer):
        # pygame trigger: 0 = halfway. → (0+1)/2 * 255 = 127.
        writer.write_axis(5, 0.0)
        assert writer.report.bRightTrigger == 127

    def test_unknown_axis_is_ignored(self, writer):
        writer.write_axis(99, 1.0)
        # No exception, no state change.

    def test_axis_clamps_to_s16_range(self, writer):
        writer.write_axis(0, 2.0)  # beyond 1.0 → clamped to 32767
        assert writer.report.sThumbLX == 32767


# ── D-pad (hat) ──────────────────────────────────────────────────────────────

class TestHatWrites:
    def test_hat_up(self, writer):
        writer.write_hat(0, 1)  # y=1 = up
        assert writer.report.wButtons & XUSB_GAMEPAD_DPAD_UP
        assert not (writer.report.wButtons & XUSB_GAMEPAD_DPAD_DOWN)

    def test_hat_down(self, writer):
        writer.write_hat(0, -1)  # y=-1 = down
        assert writer.report.wButtons & XUSB_GAMEPAD_DPAD_DOWN
        assert not (writer.report.wButtons & XUSB_GAMEPAD_DPAD_UP)

    def test_hat_left(self, writer):
        writer.write_hat(-1, 0)
        assert writer.report.wButtons & XUSB_GAMEPAD_DPAD_LEFT

    def test_hat_right(self, writer):
        writer.write_hat(1, 0)
        assert writer.report.wButtons & XUSB_GAMEPAD_DPAD_RIGHT

    def test_hat_center_clears_all_dpad(self, writer):
        writer.write_hat(-1, 0)
        writer.write_hat(0, 0)
        assert not (writer.report.wButtons & XUSB_GAMEPAD_DPAD_LEFT)
        assert not (writer.report.wButtons & XUSB_GAMEPAD_DPAD_RIGHT)
        assert not (writer.report.wButtons & XUSB_GAMEPAD_DPAD_UP)
        assert not (writer.report.wButtons & XUSB_GAMEPAD_DPAD_DOWN)

    def test_hat_diagonal_up_left(self, writer):
        writer.write_hat(-1, 1)
        assert writer.report.wButtons & XUSB_GAMEPAD_DPAD_UP
        assert writer.report.wButtons & XUSB_GAMEPAD_DPAD_LEFT


# ── syn() ────────────────────────────────────────────────────────────────────

class TestSyn:
    def test_syn_is_noop(self, writer):
        writer.syn()  # should not raise, should not send an update
        # syn() doesn't call vigem_target_x360_update.
