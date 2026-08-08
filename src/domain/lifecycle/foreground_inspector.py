"""Introspection of the foreground target — what is in front, and is it a game."""

from __future__ import annotations

import logging
from collections.abc import Callable

from domain.catalog.live_catalog import LiveCatalog
from domain.catalog.target import AppTarget, Target, WindowTarget
from domain.catalog.window_rules import active_window_not_owned_by, app_window
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
        is_game_pid: Callable[[int], bool] = lambda _: False,
    ) -> None:
        self._foreground  = foreground
        self._wm          = window_manager
        self._apps        = apps
        self._app_manager = app_manager
        self._is_game_pid = is_game_pid

    def current_app(self) -> Target | None:
        """The foreground Target, or None on the bare Desktop. A game spawned by a
        launcher (its own window while the foreground stays the launcher tile) is
        reported instead, so the Home Overlay names and returns to it."""
        target = self._foreground.current
        if isinstance(target, AppTarget):
            spawned = self._active_spawned_window(target)
            if spawned is not None:
                return spawned
        return target

    def _active_spawned_window(self, target: AppTarget) -> WindowTarget | None:
        app = self._apps[target.index]
        window = active_window_not_owned_by(self._wm.cached_windows(), app)
        if window is None:
            return None
        logger.debug(
            "Recall over %s: active window is not its own → targeting %r (id=%s)",
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
            return self._app_manager.running_pid(target.app_id)
        return None

    def foreground_game_pid(self) -> int | None:
        """The pid the foreground game renders through. A window answers before the
        tile's process, which a ``steam://`` tile leaves as an exited forwarder."""
        target = self._foreground.current
        if isinstance(target, WindowTarget):
            return target.pid or None
        if isinstance(target, AppTarget):
            windows = self._wm.cached_windows()
            app = self._apps[target.index]
            spawned = active_window_not_owned_by(windows, app)
            if spawned is not None:
                return spawned.pid
            own = app_window(windows, app)
            if own is not None:
                return own.pid
            return self._app_manager.running_pid(target.app_id)
        return None

    def foreground_is_game(self) -> bool:
        """Whether the foreground is a game — a tile carrying ``Categories=Game``, or
        a window ``is_game_pid`` classifies as one. A launcher's own UI is an
        ``AppTarget`` without that category, so it does not qualify; the pid check
        then covers the game the launcher spawned into its own window."""
        target = self._foreground.current
        if isinstance(target, WindowTarget):
            result = bool(target.pid) and self._is_game_pid(target.pid)
            logger.debug("foreground_is_game: WindowTarget %r pid=%s -> %s",
                         target.name, target.pid, result)
            return result
        if isinstance(target, AppTarget):
            app = self._apps[target.index]
            if app.is_game:
                logger.debug("foreground_is_game: AppTarget %r -> Categories=Game", target.name)
                return True
            window = active_window_not_owned_by(self._wm.cached_windows(), app)
            if window is not None and window.pid:
                result = self._is_game_pid(window.pid)
                logger.debug("foreground_is_game: AppTarget %r, active window %r pid=%s -> %s",
                             target.name, window.title, window.pid, result)
                return result
            logger.debug("foreground_is_game: AppTarget %r, no spawned window -> False",
                         target.name)
            return False
        logger.debug("foreground_is_game: no foreground target -> False")
        return False
