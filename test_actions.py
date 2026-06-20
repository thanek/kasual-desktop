import sys
sys.path.insert(0, 'src')
import importlib

# Force reload
if 'infrastructure.windows.qt.home_overlay' in sys.modules:
    del sys.modules['infrastructure.windows.qt.home_overlay']
if 'infrastructure.windows.qt' in sys.modules:
    del sys.modules['infrastructure.windows.qt']

from infrastructure.windows.qt.home_overlay import HomeOverlay
import inspect

src = inspect.getsource(HomeOverlay._setup_ui)
lines = src.split('\n')
in_actions = False
for line in lines:
    if 'actions' in line and '=' in line:
        in_actions = True
    if in_actions:
        print(line)
        if ']' in line and in_actions:
            break