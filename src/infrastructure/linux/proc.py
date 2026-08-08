"""Process introspection for Linux — /proc readers and game detection.

``parent_pid`` / ``process_name`` are injected into domain collaborators
(``TileBar``, ``ForegroundInspector``) that need process-tree information
but must stay platform-free; ``process_environ`` reads what a running
process was started with. The game-detection predicate ``is_game_pid``
combines two orthogonal signals:

  * ``uses_translation_layer`` — reads /proc/<pid>/maps for the Windows→Vulkan
    graphics translation layers (DXVK, VKD3D-Proton, Wine Vulkan). Only a
    Windows game run under Wine/Proton maps these.

  * ``descends_from_launcher`` — walks the /proc parent chain looking for
    known game-launcher process names (Steam, Heroic, Lutris, …). Covers
    native games, which map nothing a browser or video player does not.

Either signal alone is sufficient: the two are OR-combined. Anything else
(a native game started outside a launcher) is recognised by its tile's
``Categories=Game`` instead, not from the process.
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

# Substrings matched against lines of /proc/<pid>/maps. Only Wine/Proton
# translation layers qualify: the plain 3D loaders (libvulkan, libGL, libEGL)
# are mapped by ordinary accelerated desktop apps too — a Qt video player, a
# Chromium-based app, or any process the MangoHud Vulkan layer attaches to —
# so they say nothing about a process being a game.
_TRANSLATION_LAYERS = (
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


def process_environ(pid: int) -> dict[str, str]:
    """The environment *pid* was started with, or an empty mapping when it cannot
    be read (the process is gone, or belongs to another user)."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            raw = f.read()
    except OSError:
        return {}
    entries = (e.decode("utf-8", "replace") for e in raw.split(b"\0") if e)
    return dict(e.split("=", 1) for e in entries if "=" in e)


def expand_pid_tree(root_pids: set[int]) -> set[int]:
    """Return *root_pids* expanded with all their descendant PIDs.

    Uses /proc/<pid>/task/<pid>/children (Linux-specific, available on all
    modern kernels with CONFIG_PROC_CHILDREN=y). Silently skips processes that
    have already exited.
    """
    result: set[int] = set()
    queue = list(root_pids)
    while queue:
        pid = queue.pop()
        if pid in result:
            continue
        result.add(pid)
        try:
            with open(f'/proc/{pid}/task/{pid}/children') as f:
                for child in f.read().split():
                    if child.strip():
                        queue.append(int(child))
        except (OSError, ValueError):
            pass
    return result


def uses_translation_layer(pid: int) -> bool:
    """True if *pid* has mapped a Wine/Proton graphics translation layer.

    Reads /proc/<pid>/maps line by line and returns True on the first match.
    Stops early so the cost is proportional to where in the map the library
    appears (typically early)."""
    try:
        with open(f"/proc/{pid}/maps", encoding="utf-8", errors="replace") as f:
            for line in f:
                if any(lib in line for lib in _TRANSLATION_LAYERS):
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
    """True if *pid* is a game: runs translated graphics or descends from a launcher."""
    return uses_translation_layer(pid) or descends_from_launcher(pid, process_name, parent_pid)
