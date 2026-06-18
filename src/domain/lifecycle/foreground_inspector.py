"""Introspection of the foreground target — what is in front, and is it a game.

The read-only half of the app-lifecycle concern, split out of
:class:`domain.lifecycle.app_lifecycle.AppLifecycle` so the coordinator is left
with the *acting* (launch / restore / close / exit) and this owns the *asking*:
which Target the controller should treat as foreground (a launcher-spawned game
window may stand in for its launcher tile), the foreground app's pid, and whether
the foreground qualifies as a game (gating the in-game HUD toggle).

Depends only on query collaborators — the foreground state, the window manager's
cached windows, the catalog, the process manager and the injected /proc readers —
never on the view, gamepad, feedback or scheduler. That narrow surface is what
makes the game-detection rules cheap to test in isolation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from domain.catalog.live_catalog import LiveCatalog
from domain.catalog.target import AppTarget, Target, WindowTarget
from domain.catalog.window_rules import (
    active_unmanaged_window, descends_from_launcher,
)
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.window_manager import WindowManager

logger = logging.getLogger(__name__)


class ForegroundInspector:
    """Answers what is foreground and whether it is a game (no side effects)."""

    def __init__(
        self,
        foreground,
        window_manager: WindowManager,
        apps: LiveCatalog,
        app_manager: ProcessManager,
        parent_of: Callable[[int], int | None] = lambda _pid: None,
        process_name_of: Callable[[int], str | None] = lambda _pid: None,
    ) -> None:
        self._foreground      = foreground
        self._wm              = window_manager
        self._apps            = apps
        self._app_manager     = app_manager
        # /proc readers for the game-detection ancestry walk (foreground_is_game);
        # injected so the inspector stays Qt-free and filesystem-free.
        self._parent_of       = parent_of
        self._process_name_of = process_name_of

    def current_app(self) -> Target | None:
        """The foreground Target, or None on the bare Desktop.

        When the foreground app has spawned a distinct active window — e.g. a
        game launched by Steam, which runs in its own top-level window while the
        foreground stays the Steam tile — that window is reported instead, so the
        Home Overlay names it and Cancel returns to it rather than to the
        launcher underneath.
        """
        target = self._foreground.current
        if isinstance(target, AppTarget):
            spawned = self._active_spawned_window(target)
            if spawned is not None:
                return spawned
        return target

    def _active_spawned_window(self, target: AppTarget) -> WindowTarget | None:
        window = active_unmanaged_window(self._wm.cached_windows(), self._apps)
        if window is None:
            return None
        # The game inherits its launcher's recall trigger (e.g. Steam's HOLD_1S),
        # so BTN_MODE behaves the same whether the launcher or its game is front.
        app = self._apps[target.index]
        logger.debug(
            "Recall over %s: active window unmanaged → targeting %r (id=%s)",
            target.name, window.title, window.id,
        )
        return WindowTarget(
            window_id=window.id, name=window.title,
            trigger=app.recall_menu_trigger, pid=window.pid,
        )

    def foreground_pid(self) -> int | None:
        """OS pid of the foreground app, if one is a running App tile."""
        target = self._foreground.current
        if isinstance(target, AppTarget):
            return self._app_manager.running_pid(target.index)
        return None

    def foreground_is_game(self) -> bool:
        """Whether the foreground is a game — gating the in-game HUD toggle.

        A game is either a launcher-spawned window whose process descends from a
        known launcher (Steam/Heroic/Lutris/…; the active unmanaged window, or a
        directly-activated external-window tile), or a configured tile carrying
        ``Categories=Game``. The launcher's own UI (e.g. Steam) is an ``AppTarget``
        without that category, so it correctly does not qualify."""
        target = self._foreground.current
        if isinstance(target, WindowTarget):
            return bool(target.pid) and self._descends_from_launcher(target.pid)
        if isinstance(target, AppTarget):
            window = active_unmanaged_window(self._wm.cached_windows(), self._apps)
            if window is not None and window.pid:
                return self._descends_from_launcher(window.pid)
            return self._apps[target.index].is_game
        return False

    def _descends_from_launcher(self, pid: int) -> bool:
        return descends_from_launcher(pid, self._process_name_of, self._parent_of)
