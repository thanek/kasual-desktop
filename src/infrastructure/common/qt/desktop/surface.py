"""Surface strategy for the Desktop widget — how its fullscreen, always-on-top
surface is established and driven, per windowing system.

The Desktop QWidget itself is platform-neutral; the *only* part that differs by
OS is how it becomes (and is driven as) a fullscreen, stay-on-top surface:

  - Wayland/KWin → the widget is promoted to a wlr-layer-shell TOP-layer surface
    (``infrastructure.kde.qt.desktop.surface.LayerShellSurface``);
  - Windows → there is no layer-shell, so the widget is made its own frameless
    WS_EX_TOPMOST top-level window (the Windows infra's ``WindowsDesktopSurface``).

Capturing that one difference behind this small port lets the rest of the UI
(TopBar, TileBar, overlays, the whole Desktop widget) stay shared across both
platforms instead of being forked. This module holds the platform-neutral port
plus a plain fallback; each platform's concrete surface lives in its own package.
"""

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


@runtime_checkable
class DesktopSurface(Protocol):
    """How the Desktop widget becomes — and is driven as — a fullscreen surface."""

    def install(self, widget: QWidget) -> None:
        """Establish the surface for *widget*. Called once during ``Desktop.__init__``,
        before the widget is ever shown."""

    def show_fullscreen(self) -> None: ...
    def hide(self) -> None: ...
    def activate(self) -> None: ...
    def is_visible(self) -> bool: ...

    def on_reactivate(self, callback: Callable[[], None]) -> None:
        """Register the callback the surface invokes when the platform decides the
        Desktop should return to the foreground (e.g. the app it ceded focus to has
        closed). A no-op where the widget already handles this itself (Linux drives
        it from ``changeEvent``/ActivationChange)."""


class PlainSurface:
    """Fallback surface: an ordinary frameless, fullscreen top-level window with no
    compositor-specific promotion.

    Used when the composition root injects no platform surface (e.g. offscreen
    tests, or an unknown windowing system). The real platforms inject their own:
    Linux ``LayerShellSurface`` (KDE), Windows ``WindowsDesktopSurface``.
    """

    def __init__(self) -> None:
        self._widget: QWidget | None = None

    def install(self, widget: QWidget) -> None:
        self._widget = widget
        widget.setWindowFlags(Qt.WindowType.FramelessWindowHint)

    def show_fullscreen(self) -> None:
        self._widget.showFullScreen()

    def hide(self) -> None:
        self._widget.hide()

    def activate(self) -> None:
        self._widget.activateWindow()

    def is_visible(self) -> bool:
        return self._widget.isVisible()

    def on_reactivate(self, callback: Callable[[], None]) -> None:
        pass
