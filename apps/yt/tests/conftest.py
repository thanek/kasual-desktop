import sys
import types
from unittest.mock import MagicMock

# Stub out Qt WebEngine and evdev before any import — neither is available
# in a headless test environment, and neither is needed for pure logic tests.
for mod in (
    'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtWebEngineCore',
):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Replace QWebEngineUrlRequestInterceptor with a real base class so AdBlocker
# can be subclassed and instantiated without a running Qt application.
import types as _types
_wec = sys.modules['PyQt6.QtWebEngineCore']
_wec.QWebEngineUrlRequestInterceptor = type('QWebEngineUrlRequestInterceptor', (), {})

if 'evdev' not in sys.modules:
    sys.modules['evdev'] = MagicMock()

import os, sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
