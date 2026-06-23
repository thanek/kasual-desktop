"""Thin ctypes bridge to KDE's LayerShellQt — turn a top-level QWidget into a
wlr-layer-shell surface (a panel/overlay anchored in a compositor layer that
can sit above normal windows, including fullscreen).

PyQt6 ships no LayerShellQt bindings, so we call the C++ API directly through
the exported (mangled) symbols of libLayerShellQtInterface.so.6. Requirements:
  - running on the SYSTEM Qt (not pip-bundled): the layer-shell shell
    integration plugin is version-locked to the system Qt build;
  - QT_WAYLAND_SHELL_INTEGRATION=layer-shell set before QApplication;
  - the Qt platform being `wayland`.

Validated on KWin 6.5.2 / Qt 6.9.2 (see tools/spike_layershell.py).

Usage:
    w = QWidget()
    # ... build UI ...
    make_layer_surface(w, layer=Layer.OVERLAY, anchors=Anchor.ALL,
                       exclusive_zone=-1, keyboard=Keyboard.NONE)
    w.show()

make_layer_surface() forces native window creation itself; just make sure to
call it BEFORE w.show() — the layer surface is created with our settings when
the window is first shown.
"""

import ctypes
import logging

from PyQt6 import sip
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget

# The layer/anchor/keyboard enums are shared vocabulary, defined platform-neutrally
# in common; this adapter is the Wayland binding that consumes them.
from infrastructure.common.qt.ui.layer_shell import Anchor, Keyboard, Layer

logger = logging.getLogger(__name__)

_LIB_NAME = "libLayerShellQtInterface.so.6"

# Mangled C++ symbols (from `nm -D libLayerShellQtInterface.so.6`).
_SYM_GET     = "_ZN12LayerShellQt6Window3getEP7QWindow"
_SYM_LAYER   = "_ZN12LayerShellQt6Window8setLayerENS0_5LayerE"
_SYM_ANCHORS = "_ZN12LayerShellQt6Window10setAnchorsE6QFlagsINS0_6AnchorEE"
_SYM_EXCL    = "_ZN12LayerShellQt6Window16setExclusiveZoneEi"
_SYM_KBD     = "_ZN12LayerShellQt6Window24setKeyboardInteractivityENS0_21KeyboardInteractivityE"


_lib = None  # CDLL once bound, False once known-unavailable, None untried


def _load():
    global _lib
    if _lib is not None:
        return _lib or None
    try:
        lib = ctypes.CDLL(_LIB_NAME)
        lib._ls_get = getattr(lib, _SYM_GET)
        lib._ls_get.restype = ctypes.c_void_p
        lib._ls_get.argtypes = [ctypes.c_void_p]
        for attr, sym in (("_ls_layer", _SYM_LAYER), ("_ls_anchors", _SYM_ANCHORS),
                          ("_ls_excl", _SYM_EXCL), ("_ls_kbd", _SYM_KBD)):
            fn = getattr(lib, sym)
            fn.restype = None
            # QFlags<Anchor> and the enums are all int-sized across the ABI.
            fn.argtypes = [ctypes.c_void_p, ctypes.c_int]
            setattr(lib, attr, fn)
        _lib = lib
    except (OSError, AttributeError) as exc:
        logger.error("DBG layer_shell: cannot bind %s: %s", _LIB_NAME, exc)
        _lib = False
    return _lib or None


def is_available() -> bool:
    """True if LayerShellQt could be bound (system Qt with the lib present)."""
    return _load() is not None


def make_layer_surface(
    widget: QWidget,
    *,
    layer: Layer = Layer.TOP,
    anchors: Anchor = Anchor.NONE,
    exclusive_zone: int = 0,
    keyboard: Keyboard = Keyboard.NONE,
) -> bool:
    """Configure `widget`'s top-level window as a layer-shell surface.

    Must be called before widget.show(). Returns True on success, False if
    not on Wayland, LayerShellQt is unavailable, or the handle creation failed.
    """
    if QGuiApplication.platformName() != "wayland":
        # offscreen (tests), xcb, etc. — leave the widget as an ordinary window.
        return False

    lib = _load()
    if lib is None:
        return False

    widget.winId()  # create the native QWindow (shell surface comes at show())
    qwin = widget.windowHandle()
    if qwin is None:
        logger.error("DBG layer_shell: windowHandle() is None after winId()")
        return False

    ls_window = lib._ls_get(sip.unwrapinstance(qwin))
    if not ls_window:
        logger.error("DBG layer_shell: LayerShellQt::Window::get() returned null")
        return False

    lib._ls_layer(ls_window, int(layer))
    lib._ls_anchors(ls_window, int(anchors))
    lib._ls_excl(ls_window, exclusive_zone)
    lib._ls_kbd(ls_window, int(keyboard))
    return True
