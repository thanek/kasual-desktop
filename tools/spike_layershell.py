#!/usr/bin/env python3
"""Spike A — can PyQt6 create a wlr-layer-shell `overlay` surface on KWin?

We have no official Python bindings for LayerShellQt, so we:
  1. force Qt's Wayland platform to use the layer-shell shell integration
     (QT_WAYLAND_SHELL_INTEGRATION=layer-shell, set before QApplication),
  2. reach LayerShellQt::Window's C++ API via ctypes to set layer=Overlay,
     anchors=all-edges, exclusiveZone=-1 (draw over panels), keyboard=None.

The surface is semi-transparent and never grabs the keyboard, so it can't
lock you out. It auto-closes after a timeout regardless.

Run with WAYLAND_DEBUG=1 to objectively confirm the role:
    WAYLAND_DEBUG=1 python tools/spike_layershell.py 2>&1 | grep layer
A `zwlr_layer_shell_v1.get_layer_surface` request proves it became a
layer surface (not a plain xdg-toplevel).
"""

import ctypes
import os
import sys

# MUST be set before the Wayland platform plugin initializes.
os.environ["QT_WAYLAND_SHELL_INTEGRATION"] = "layer-shell"

from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer, QDateTime
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel

# LayerShellQt::Window enum values (stable, mirror the wlr-layer-shell protocol)
LAYER_BACKGROUND, LAYER_BOTTOM, LAYER_TOP, LAYER_OVERLAY = 0, 1, 2, 3
ANCHOR_TOP, ANCHOR_BOTTOM, ANCHOR_LEFT, ANCHOR_RIGHT = 1, 2, 4, 8
ANCHOR_ALL = ANCHOR_TOP | ANCHOR_BOTTOM | ANCHOR_LEFT | ANCHOR_RIGHT
KBD_NONE, KBD_EXCLUSIVE, KBD_ON_DEMAND = 0, 1, 2

_LIB = "libLayerShellQtInterface.so.6"
# Mangled symbol names (from `nm -D` on the lib)
_SYM_GET   = "_ZN12LayerShellQt6Window3getEP7QWindow"
_SYM_LAYER = "_ZN12LayerShellQt6Window8setLayerENS0_5LayerE"
_SYM_ANCH  = "_ZN12LayerShellQt6Window10setAnchorsE6QFlagsINS0_6AnchorEE"
_SYM_EXCL  = "_ZN12LayerShellQt6Window16setExclusiveZoneEi"
_SYM_KBD   = "_ZN12LayerShellQt6Window24setKeyboardInteractivityENS0_21KeyboardInteractivityE"


def configure_layer_surface(widget: QWidget) -> bool:
    """Attach LayerShellQt config to `widget`'s QWindow. Returns success."""
    try:
        lib = ctypes.CDLL(_LIB)
    except OSError as exc:
        print(f"[spike] cannot load {_LIB}: {exc}")
        return False

    lib._get = getattr(lib, _SYM_GET)
    lib._get.restype = ctypes.c_void_p
    lib._get.argtypes = [ctypes.c_void_p]
    for name, sym in (("_layer", _SYM_LAYER), ("_anch", _SYM_ANCH),
                      ("_excl", _SYM_EXCL), ("_kbd", _SYM_KBD)):
        fn = getattr(lib, sym)
        fn.restype = None
        fn.argtypes = [ctypes.c_void_p, ctypes.c_int]
        setattr(lib, name, fn)

    qwin = widget.windowHandle()
    if qwin is None:
        print("[spike] windowHandle() is None — call winId() first")
        return False
    qwin_ptr = sip.unwrapinstance(qwin)

    ls_window = lib._get(qwin_ptr)
    if not ls_window:
        print("[spike] LayerShellQt::Window::get() returned null")
        return False
    print(f"[spike] LayerShellQt::Window* = 0x{ls_window:x}")

    lib._layer(ls_window, LAYER_OVERLAY)
    lib._anch(ls_window, ANCHOR_ALL)
    lib._excl(ls_window, -1)        # ignore other exclusive zones → cover panels
    lib._kbd(ls_window, KBD_NONE)   # never steal keyboard → can't lock you out
    print("[spike] configured: layer=OVERLAY anchors=ALL exclusiveZone=-1 kbd=NONE")
    return True


def main() -> int:
    app = QApplication(sys.argv)
    print(f"[spike] Qt platform: {app.platformName()}")

    w = QWidget()
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    w.setStyleSheet("background: rgba(10, 16, 24, 130);")

    layout = QVBoxLayout(w)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    banner = QLabel()
    banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
    banner.setStyleSheet(
        "background:#88c0d0; color:#0b140e; font-size:30px; font-weight:bold;"
        " padding:40px 60px; border-radius:18px;"
    )
    layout.addWidget(banner)

    # Live-updating text proves this surface is our own, on top, and animating.
    def tick():
        left = (deadline - QDateTime.currentMSecsSinceEpoch()) // 1000
        banner.setText(
            "KD layer-shell spike — warstwa OVERLAY\n"
            "Powinno być NAD panelem, oknami i pełnym ekranem.\n"
            f"auto-zamknięcie za {max(left, 0)} s"
        )
    timer = QTimer(w)
    timer.timeout.connect(tick)
    timer.start(250)

    # Create the native QWindow (but not yet the shell surface), configure it,
    # then show — LayerShellQt reads the config when the surface is created.
    w.winId()
    ok = configure_layer_surface(w)
    if not ok:
        print("[spike] FALLBACK: layer-shell config failed; showing as plain window")
    w.showFullScreen()

    SECONDS = 30
    deadline = QDateTime.currentMSecsSinceEpoch() + SECONDS * 1000
    tick()
    QTimer.singleShot(SECONDS * 1000, app.quit)
    print(f"[spike] showing overlay for {SECONDS}s …")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
