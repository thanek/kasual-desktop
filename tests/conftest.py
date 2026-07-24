import os
import sys
from unittest.mock import MagicMock, patch

# Offscreen backend — works without a display (CI, Xvfb, etc.).
# Forced rather than defaulted: a COSMIC session exports QT_QPA_PLATFORM itself
# ("wayland;xcb"), and honouring that makes every widget test flash a real window
# on the developer's screen. KD_TEST_PLATFORM is the deliberate way to ask for a
# real platform instead.
os.environ["QT_QPA_PLATFORM"] = os.environ.get("KD_TEST_PLATFORM", "offscreen")

# Mock evdev on platforms where it's not available (Windows). The Linux gamepad
# watcher imports evdev at module level; many tests use the mock_gamepad fixture
# which imports GamepadWatcher. Without this mock, every test using mock_gamepad
# would fail with ModuleNotFoundError on Windows. The apps' conftest.py files
# already do the same thing.
try:
    import evdev  # noqa: F401
except ImportError:
    sys.modules['evdev'] = MagicMock()

# Add the project root to the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest


@pytest.fixture(autouse=True)
def silence_sounds():
    """Mutes sound playback (SoundFeedback) in all tests."""
    with patch("infrastructure.common.audio.feedback.SoundFeedback.play"):
        yield


@pytest.fixture
def mock_gamepad(qapp):
    """
    GamepadWatcher without starting the _loop thread.

    Patches threading.Thread before __init__ calls it,
    so the evdev loop never starts — tests are fully isolated
    from hardware and UInput permissions.
    """
    with patch("infrastructure.linux.input.gamepad_watcher.threading.Thread"):
        from infrastructure.linux.input.gamepad_watcher import GamepadWatcher
        gw = GamepadWatcher()
    return gw
