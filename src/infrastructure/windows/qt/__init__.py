"""Windows-specific Qt infrastructure for Kasual Desktop.

The Desktop UI itself (TopBar, TileBar, AppTile, overlays) is shared with Linux
under ``infrastructure.qt.desktop`` / ``infrastructure.qt.overlays``; only the
genuinely OS-specific pieces live here — currently the topmost desktop surface
(``desktop_surface``). Imports are kept lazy (per submodule) so this package has
no import-time side effects.
"""
