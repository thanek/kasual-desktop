"""COSMIC (cosmic-comp) adapters.

cosmic-comp offers neither an IPC CLI nor a scripting or extension host, so window
management is spoken directly as Wayland protocols — ``ext-foreign-toplevel-list``
for the window list, ``cosmic-toplevel-info``/``cosmic-toplevel-management`` for
state and control. It does implement wlr-layer-shell, so the Desktop surface needs
no COSMIC-specific adapter. The wallpaper comes from cosmic-config on disk.
"""
