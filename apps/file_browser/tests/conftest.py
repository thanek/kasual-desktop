import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Mock evdev before any import so gamepad.py's module-level UInput() succeeds
if 'evdev' not in sys.modules:
    sys.modules['evdev'] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
