"""Process introspection for KDE/Linux — /proc readers and game detection.

``parent_pid`` / ``process_name`` are injected into domain collaborators
(``TileBar``, ``ForegroundInspector``) that need process-tree information
but must stay platform-free. The game-detection predicate ``is_game_pid``
combines two orthogonal signals:

  * ``uses_graphics_api`` — reads /proc/<pid>/maps for known 3D graphics
    libraries (Vulkan, OpenGL/libGL, DXVK, VKD3D-Proton, Wine Vulkan). A
    process that has mapped any of these is almost certainly a game or a
    3D-capable app, regardless of how it was launched.

  * ``descends_from_launcher`` — walks the /proc parent chain looking for
    known game-launcher process names (Steam, Heroic, Lutris, …). Covers
    games whose launcher does not explicitly load a graphics library but
    that descend from a recognisable runtime (e.g. early-startup frames).

Either signal alone is sufficient: the two are OR-combined.
"""

from __future__ import annotations

from collections.abc import Callable

from domain.catalog.window_rules import walk_parent_chain

# /proc/<pid>/comm names that mark a game launcher or runtime in a process's
# ancestry. Steam wraps every launch in ``reaper`` and runs Proton titles
# through ``pressure-vessel``; Wine/native titles carry a ``wine*`` ancestor;
# the other launchers speak for themselves.  Any name starting with ``wine``
# also matches (comm is kernel-truncated to 15 chars, so ``wine64-preloader``
# arrives as ``wine64-preloade``).
GAME_LAUNCHERS = frozenset({
    "steam", "steamwebhelper", "reaper", "pressure-vessel", "pv-bwrap",
    "gamescope", "lutris", "heroic", "legendary", "gogdl", "nile",
    "bottles", "bottles-cli",
})

# Substrings matched against lines of /proc/<pid>/maps to detect 3D API use.
# libGL.so (OpenGL with GLX) is distinct from libEGL.so, which is used by
# Wayland UI toolkits (Qt, GTK) but not by game renderers — so checking for
# "libGL.so" avoids false positives on ordinary GUI applications.
_GRAPHICS_LIBS = (
    "libvulkan",   # Vulkan loader — Vulkan-native games, DXVK, VKD3D
    "libGL.so",    # Mesa OpenGL with GLX — Linux-native OpenGL games
    "dxvk",        # DXVK: D3D9/D3D11 → Vulkan (Proton, Wine)
    "winevulkan",  # Wine Vulkan layer
    "vkd3d",       # VKD3D-Proton: D3D12 → Vulkan
)


def parent_pid(pid: int) -> int | None:
    """Parent PID of *pid* from ``/proc/<pid>/status``, or None on failure."""
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return None


def process_name(pid: int) -> str | None:
    """Process name of *pid* from ``/proc/<pid>/comm`` (kernel-truncated to 15
    chars), or None on failure."""
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def uses_graphics_api(pid: int) -> bool:
    """True if *pid* has mapped a 3D graphics library.

    Reads /proc/<pid>/maps line by line and returns True on the first match
    against a known graphics API library name. Stops early so the cost is
    proportional to where in the map the library appears (typically early)."""
    try:
        with open(f"/proc/{pid}/maps", encoding="utf-8", errors="replace") as f:
            for line in f:
                if any(lib in line for lib in _GRAPHICS_LIBS):
                    return True
    except OSError:
        pass
    return False


def descends_from_launcher(
    pid:       int,
    name_of:   Callable[[int], str | None],
    parent_of: Callable[[int], int | None],
    launchers: frozenset[str] = GAME_LAUNCHERS,
) -> bool:
    """True if *pid* or any ancestor is a known game launcher / runtime.

    Walks the process-parent chain via ``name_of``/``parent_of`` (both
    injected so the function stays testable without real /proc reads).
    Any ``wine``-prefixed name also matches."""
    for current in walk_parent_chain(pid, parent_of):
        name = (name_of(current) or "").lower()
        if name in launchers or name.startswith("wine"):
            return True
    return False


def is_game_pid(pid: int) -> bool:
    """True if *pid* is a game: uses a 3D graphics API or descends from a launcher."""
    return uses_graphics_api(pid) or descends_from_launcher(pid, process_name, parent_pid)
