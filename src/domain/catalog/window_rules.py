"""Rules relating the open-window list to our apps: which windows deserve a
dynamic tile, whether a launched app has a window yet, which recall trigger a
window inherits."""

from collections.abc import Callable, Iterator, Mapping, Sequence

from domain.catalog.app import App
from domain.catalog.window import Window
from domain.input.vocabulary import Trigger


def external_windows(
    windows:               Sequence[Window],
    apps:                  Sequence[App],
    owned_by_running_group: Callable[[Window], bool],
) -> list[Window]:
    """Windows not already shown as a static tile, in original order. A window is
    excluded when it belongs to a running app's process group or matches one of our
    apps. A window with no pid is always external — nothing to attribute it to."""
    def managed(w: Window) -> bool:
        if w.pid == 0:
            return False
        return owned_by_running_group(w) or any(w.matches_app(app) for app in apps)

    return [w for w in windows if not managed(w)]


def app_window_present(
    windows:    Sequence[Window],
    app:        App,
    owned_pids: set[int],
) -> bool:
    """True if *app* already has a mapped window, matched by process subtree
    (*owned_pids*) or app identity. Both keys are needed: a forwarder launch shows
    a window under an unrelated pid but a matching class, while a bootstrap window
    may carry the right pid before its class is set."""
    return any(w.pid in owned_pids or w.matches_app(app) for w in windows)


def is_app_running(
    idx:        int,
    apps:       Sequence[App],
    windows:    Sequence[Window],
    is_process_running: Callable[[str], bool],
) -> bool:
    """True if the app at *idx* is running, by its process or a visible window (the
    window fallback covers an externally-launched or self-relaunched app).

    A Steam game is the exception: the tracked process is the shared Steam client,
    common to every game, so the tile is "running" only while its own
    ``steam_app_<id>`` window exists."""
    if idx >= len(apps):
        return False
    app = apps[idx]
    if app.steam_app_id is not None:
        return any(w.matches_app(app) for w in windows)
    if is_process_running(app.id):
        return True
    return any(w.matches_app(app) for w in windows)


def app_window(windows: Sequence[Window], app: App) -> Window | None:
    """*app*'s own window — the one holding the screen where several are mapped, a
    launcher's splash and its game being the usual pair. A Steam game tile matches
    its ``steam_app_<id>`` window here, where :func:`active_unmanaged_window`
    never would."""
    own = [w for w in windows if w.pid and w.matches_app(app)]
    if not own:
        return None
    return next((w for w in own if w.holds_screen), own[0])


def active_unmanaged_window(
    windows: Sequence[Window],
    apps:    Sequence[App],
) -> Window | None:
    """The active window that belongs to no configured app — e.g. a game running
    in its own window under a launcher, so the Home Overlay names and returns to
    the game, not the launcher. Identity-based, since a Steam game's process
    session isn't reliably attributable but never matches the ``steam`` tile.

    It has to hold the screen. Focus alone would adopt whatever happens to be in
    front — a terminal the user clicked into — and the Home Overlay would then offer
    to close *that*."""
    active = next((w for w in windows if w.active and w.pid), None)
    if active is None or not active.holds_screen:
        return None
    if any(active.matches_app(app) for app in apps):
        return None
    return active


def walk_parent_chain(
    pid:       int,
    parent_of: Callable[[int], int | None],
) -> Iterator[int]:
    """Yield *pid* and each ancestor up the process tree. Stops at pid 1, an
    unknown parent, or a cycle; each pid is visited at most once."""
    visited: set[int] = set()
    current = pid
    while current > 1 and current not in visited:
        visited.add(current)
        yield current
        parent = parent_of(current)
        if parent is None:
            break
        current = parent


def resolve_recall_trigger(
    pid:        int,
    pid_to_app: Mapping[int, App],
    parent_of:  Callable[[int], int | None],
) -> str:
    """Walk the parent chain to the first pid owned by one of our apps and return
    its ``recall_menu_trigger`` — so a game launched by Steam inherits Steam's
    hold-to-recall. Falls back to CLICK when nothing owns it."""
    for current in walk_parent_chain(pid, parent_of):
        app = pid_to_app.get(current)
        if app is not None:
            return app.recall_menu_trigger
    return Trigger.CLICK
