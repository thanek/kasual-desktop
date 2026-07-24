import os
import sys
import types
from unittest.mock import MagicMock

# Forced, not defaulted: a COSMIC session exports QT_QPA_PLATFORM itself, and
# honouring it would flash a real window per widget test (see tests/conftest.py).
os.environ["QT_QPA_PLATFORM"] = os.environ.get("KD_TEST_PLATFORM", "offscreen")

# Mock evdev before any import so gamepad.py's module-level UInput() succeeds
if 'evdev' not in sys.modules:
    sys.modules['evdev'] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
