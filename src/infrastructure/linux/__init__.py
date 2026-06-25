"""Generic Linux infrastructure — adapters that work on any Linux session,
independent of the desktop environment / Wayland compositor.

KWin/Plasma-specific adapters (window management, layer-shell surface,
wallpaper) live in the sibling ``kde`` package; everything here relies only on
portable interfaces: PipeWire/Pulse (``pactl``), logind (``systemctl``),
NetworkManager, evdev, MangoHud, freedesktop notifications, and ``/proc``.
"""
