"""Tests for WindowsVolumeControl — master volume via Core Audio / pycaw.

Maps the domain ``Volume`` (0–100) to the endpoint's 0.0–1.0 scalar. The
IAudioEndpointVolume COM object is cached and re-acquired if a call fails.

Skipped on non-Windows: ``pycaw`` is Windows-only. The COM endpoint is mocked
via ``sys.modules`` so no real audio device is touched.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Tests Windows Core Audio / pycaw adapter; Windows-only",
)

from domain.system.volume import Volume
from infrastructure.windows.volume import WindowsVolumeControl


def _mock_pycaw(scalar=0.5):
    """Build a pycaw.pycaw module mock whose AudioUtilities.GetSpeakers()
    .EndpointVolume reports the given master scalar.

    The production code does ``from pycaw.pycaw import AudioUtilities``, so the
    mock must expose ``AudioUtilities`` directly on the ``pycaw.pycaw`` module
    (not nested under a ``pycaw`` attribute)."""
    pycaw_mod = MagicMock()
    endpoint = MagicMock()
    endpoint.GetMasterVolumeLevelScalar.return_value = scalar
    pycaw_mod.AudioUtilities.GetSpeakers.return_value.EndpointVolume = endpoint
    return pycaw_mod, endpoint


class TestGet:
    def test_returns_volume_scaled_to_int(self):
        pycaw_mod, _ = _mock_pycaw(scalar=0.42)
        with patch.dict("sys.modules", {"pycaw.pycaw": pycaw_mod}):
            assert WindowsVolumeControl().get().value == 42

    def test_rounds_to_nearest_int(self):
        pycaw_mod, _ = _mock_pycaw(scalar=0.555)
        with patch.dict("sys.modules", {"pycaw.pycaw": pycaw_mod}):
            assert WindowsVolumeControl().get().value == 56   # round(55.5)

    def test_default_on_error(self):
        # An exception (e.g. no audio device) → default volume, endpoint reset.
        pycaw_mod = MagicMock()
        pycaw_mod.pycaw.AudioUtilities.GetSpeakers.side_effect = OSError
        with patch.dict("sys.modules", {"pycaw.pycaw": pycaw_mod}):
            ctrl = WindowsVolumeControl()
            assert ctrl.get() == Volume(Volume.DEFAULT)
        # The cached endpoint is cleared so the next call re-acquires.
        assert ctrl._endpoint is None


class TestSet:
    def test_calls_set_master_volume_with_scalar(self):
        pycaw_mod, endpoint = _mock_pycaw()
        with patch.dict("sys.modules", {"pycaw.pycaw": pycaw_mod}):
            WindowsVolumeControl().set(Volume(70))
        endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(0.7, None)

    def test_retries_once_on_failure(self):
        # First call raises, second succeeds — the endpoint is re-acquired and
        # the set is retried exactly once.
        pycaw_mod, endpoint = _mock_pycaw()
        endpoint.SetMasterVolumeLevelScalar.side_effect = [OSError, None]
        with patch.dict("sys.modules", {"pycaw.pycaw": pycaw_mod}):
            WindowsVolumeControl().set(Volume(50))
        assert endpoint.SetMasterVolumeLevelScalar.call_count == 2

    def test_swallows_persistent_failure(self):
        # Both calls raise — the second is logged as error, not re-raised.
        pycaw_mod, endpoint = _mock_pycaw()
        endpoint.SetMasterVolumeLevelScalar.side_effect = [OSError, OSError]
        with patch.dict("sys.modules", {"pycaw.pycaw": pycaw_mod}):
            WindowsVolumeControl().set(Volume(50))   # must not raise


class TestEndpointCache:
    def test_endpoint_cached_across_calls(self):
        pycaw_mod, endpoint = _mock_pycaw(scalar=0.3)
        with patch.dict("sys.modules", {"pycaw.pycaw": pycaw_mod}):
            ctrl = WindowsVolumeControl()
            ctrl.get()
            ctrl.get()
        # GetSpeakers is called once (on first _ep()); the cached endpoint is
        # reused for the second get.
        assert pycaw_mod.AudioUtilities.GetSpeakers.call_count == 1

    def test_endpoint_reacquired_after_error(self):
        pycaw_mod, endpoint = _mock_pycaw(scalar=0.3)
        endpoint.GetMasterVolumeLevelScalar.side_effect = OSError
        with patch.dict("sys.modules", {"pycaw.pycaw": pycaw_mod}):
            ctrl = WindowsVolumeControl()
            ctrl.get()   # fails, clears cache
            ctrl.get()   # re-acquires
        assert pycaw_mod.AudioUtilities.GetSpeakers.call_count == 2
