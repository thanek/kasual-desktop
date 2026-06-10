"""The Desktop's own state: on screen? paused? what's in front?

Pure state + transitions, no Qt. Composes the shared :class:`ForegroundState`
(so the foreground a coordinator and the app-lifecycle see stays one truth) and
adds the desktop's visibility and the *paused* notion — minimized-but-ready, as
opposed to fully gone.

The one rule worth naming lives in :meth:`go_to_desktop` / :meth:`resume`: the
overlays hidden by a pause are restored *only* when we are actually coming back
from a pause — both transitions report that so the view can act on it.
"""

from domain.shell.foreground import ForegroundState
from domain.catalog.target import Target


class DesktopState:
    def __init__(self, foreground: ForegroundState | None = None) -> None:
        self._foreground = foreground or ForegroundState()
        self._visible = False
        self._paused  = False

    # ── Queries ──────────────────────────────────────────────────────────────

    @property
    def foreground(self) -> ForegroundState:
        return self._foreground

    @property
    def current(self) -> Target | None:
        return self._foreground.current

    def is_idle(self) -> bool:
        """True when the bare Desktop is in front (nothing launched/open)."""
        return self._foreground.is_idle()

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def paused(self) -> bool:
        return self._paused

    # ── Transitions ──────────────────────────────────────────────────────────

    def go_to_desktop(self) -> bool:
        """The bare Desktop comes forward: nothing is in front, we are visible.
        Returns whether paused overlays must be restored (we were paused)."""
        self._foreground.clear()
        return self._become_visible()

    def resume(self) -> bool:
        """Come back after a controller reconnect, foreground untouched.
        Returns whether paused overlays must be restored (we were paused)."""
        return self._become_visible()

    def pause(self) -> None:
        """Minimize the Desktop but stay ready to resume."""
        self._paused = True
        self._visible = False

    def _become_visible(self) -> bool:
        was_paused = self._paused
        self._paused = False
        self._visible = True
        return was_paused
