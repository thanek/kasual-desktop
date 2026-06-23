"""Layer-shell vocabulary — the plain enums describing a wlr-layer-shell surface.

These are pure data (no Wayland/KDE dependency) shared by the platform-neutral UI
(overlays, the overlay/desktop surface dispatchers) as parameters. The actual
LayerShellQt binding that consumes them lives in the KDE adapter
(``infrastructure.kde.qt.ui.layer_shell``); keeping the vocabulary here lets the
shared UI name a layer/anchor/keyboard mode without importing that adapter.
"""

import enum


class Layer(enum.IntEnum):
    BACKGROUND = 0
    BOTTOM     = 1
    TOP        = 2
    OVERLAY    = 3


class Anchor(enum.IntFlag):
    NONE   = 0
    TOP    = 1
    BOTTOM = 2
    LEFT   = 4
    RIGHT  = 8
    ALL    = TOP | BOTTOM | LEFT | RIGHT


class Keyboard(enum.IntEnum):
    NONE      = 0
    EXCLUSIVE = 1
    ON_DEMAND = 2
