"""Tile-scoped dialogs and top-bar overlay hosting — extracted from the Desktop.

Owns the confirm dialog, the Tile Settings modal, and the tile popover (each
with its own named handle) plus the generic top-bar overlay tracker used by
Network/Notifications. Desktop stays the router — it decides *what* to do
(e.g. which tile-menu picks are "management" actions); this controller only
opens/closes the widgets and keeps the hint bar and registry in sync.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Trigger
from domain.menu.item import MenuItem
from domain.menu.palette import TILE_COLORS
from domain.menu.tile import tile_menu_for
from domain.navigation import hints as home_hints
from domain.shared.feedback import Feedback
from domain.shell.open_overlays import OpenOverlays
from infrastructure.common.qt.overlays.base_overlay import BaseOverlay
from infrastructure.common.qt.overlays.confirm_dialog import ConfirmDialog
from infrastructure.common.qt.overlays.tile_popover import TilePopoverMenu
from infrastructure.common.qt.overlays.tile_settings import TileSettings

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

    from domain.catalog.tile_settings_editor import TileSettingsEditor
    from domain.navigation.focus_navigator import FocusNavigator
    from .hint_bar import HintBar
    from .surface import DesktopSurface
    from .tile_bar import TileBar

logger = logging.getLogger(__name__)


class DialogHostController:
    """Opens and tracks the tile-scoped dialogs and top-bar overlays."""

    def __init__(
        self,
        gamepad: PadControl,
        feedback: Feedback,
        overlays: OpenOverlays,
        hintbar: HintBar,
        nav: FocusNavigator,
        surface: DesktopSurface,
        tilebar: TileBar,
        tile_settings_editor: TileSettingsEditor,
        parent: QWidget,
        on_tile_select: Callable[[MenuItem], None],
        sync_hint_visibility: Callable[[], None],
    ) -> None:
        self._gamepad = gamepad
        self._feedback = feedback
        self._overlays = overlays
        self._hintbar = hintbar
        self._nav = nav
        self._surface = surface
        self._tilebar = tilebar
        self._tile_settings_editor = tile_settings_editor
        self._parent = parent
        self._on_tile_select = on_tile_select
        self._sync_hint_visibility = sync_hint_visibility
        self._confirm_dialog: ConfirmDialog | None = None
        self._tile_settings: TileSettings | None = None
        self._tile_popover: TilePopoverMenu | None = None

    @property
    def tile_popover_open(self) -> bool:
        return self._tile_popover is not None

    @property
    def active_tile_popover(self) -> 'TilePopoverMenu | None':
        return self._tile_popover

    def cancel(self) -> None:
        """Drop the confirm/settings handles when the overlay group is torn
        down externally (the registry clears the widgets themselves)."""
        self._confirm_dialog = None
        self._tile_settings = None

    # ── Confirmation dialog ─────────────────────────────────────────────────

    def show_confirm(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None] | None = None,
    ) -> None:
        """Open a ConfirmDialog, ignoring the call if one is already up.

        The callbacks are wrapped to forget the dialog before handing control on,
        so its slot and registry entry clear on whichever button is pressed.
        """
        if self._confirm_dialog is not None:
            return

        def _wrap(cb: Callable[[], None] | None) -> Callable[[], None]:
            def _inner() -> None:
                self._forget_confirm()
                if cb:
                    cb()
            return _inner

        self._confirm_dialog = ConfirmDialog(
            question=question,
            on_confirmed=_wrap(on_confirmed),
            on_cancelled=_wrap(on_cancelled),
            gamepad=self._gamepad,
            feedback=self._feedback,
            parent=self._parent,
            dim=False,
        )
        self._overlays.register(self._confirm_dialog)
        self._hintbar.show_hints(home_hints.CONFIRM)
        self._hintbar.show()

    def _forget_confirm(self) -> None:
        """Drop the confirm dialog from the registry and clear its slot.

        Restore the screen hints that were replaced when the dialog opened, so
        the hint bar doesn't show stale confirm controls after it closes.
        """
        self._overlays.forget(self._confirm_dialog)
        self._confirm_dialog = None
        if self._surface.is_visible():
            self._nav.render()
        self._sync_hint_visibility()

    @property
    def active_confirm(self) -> 'ConfirmDialog | None':
        """The confirmation currently on screen, for whoever reports the shell's state."""
        return self._confirm_dialog

    def close_active_dialog(self) -> None:
        if self._confirm_dialog is not None:
            logger.warning("Dialog window still active after app ending – forcing to close")
            self._confirm_dialog.cancel()
            self._forget_confirm()

    # ── Tile settings ───────────────────────────────────────────────────────

    def show_tile_settings(self) -> None:
        """Open the Tile Settings modal for the focused app tile.

        Both sections (recall trigger + colour) are visible at once. Staging a
        colour previews it live on the tile; *Save* persists both values to the
        ``.desktop`` file; *Cancel* (or B / Escape / backdrop / BTN_MODE) reverts
        the preview. The capture of the tile index is safe: the modal is modal,
        so the focus cannot move underneath it."""
        if self._tile_settings is not None or not self._tilebar.current_is_app():
            return
        index = self._tilebar.current_app_index()
        original_color = self._tilebar.current_app_color()

        def _on_color_preview(color: str) -> None:
            self._tilebar.set_app_color(index, color)

        def _on_save(color: str, trigger: str) -> None:
            self._forget_tile_settings()
            self._tile_settings_editor.apply(index, color, trigger)

        def _on_cancel() -> None:
            self._forget_tile_settings()
            if original_color is not None:
                self._tilebar.set_app_color(index, original_color)

        self._tile_settings = TileSettings(
            app_name=self._tilebar.current_app_name() or "",
            colors=TILE_COLORS,
            original_color=original_color,
            original_trigger=self._tilebar.current_app_recall_trigger() or Trigger.CLICK,
            on_color_preview=_on_color_preview,
            on_save=_on_save,
            on_cancel=_on_cancel,
            gamepad=self._gamepad,
            feedback=self._feedback,
            parent=self._parent,
        )
        self._overlays.register(self._tile_settings)
        self._hintbar.show_hints(home_hints.TILE_SETTINGS)

    def _forget_tile_settings(self) -> None:
        self._overlays.forget(self._tile_settings)
        self._tile_settings = None
        self._nav.render()   # restore the tiles-screen hints

    # ── Tile popover ────────────────────────────────────────────────────────

    def show_tile_popover(self) -> None:
        """Show the single, state-dependent tile popover above the focused tile.

        The menu (which items appear, by running state and tile kind) is the
        domain's — `tile_menu_for` composes the merged lifecycle + management
        list. Activation is routed to the callback injected at construction.
        """
        ctx = self._tilebar.current_context()
        if ctx is None:
            return
        items = tile_menu_for(
            ctx, lambda idx: self._tilebar.is_tile_running(idx, self._tilebar.last_windows))
        # The [＋] add tile (and any future menu-less target) has no popover —
        # don't open an empty one.
        if not items:
            return
        popover = TilePopoverMenu(
            items=items,
            on_select=self._on_tile_select,
            gamepad=self._gamepad,
            feedback=self._feedback,
            parent=self._parent,
        )
        self._tile_popover = popover
        self._overlays.register(popover)
        popover.closed.connect(self._on_tile_popover_closed)
        # Swap the hint bar to the popover's own controls (incl. Y to close the
        # menu it opened); restored to the tiles screen on close.
        self._hintbar.show_hints(home_hints.TILE_POPOVER)
        popover.show_above(self._tilebar.current_tile())

    def _on_tile_popover_closed(self) -> None:
        self._overlays.forget(self._tile_popover)
        self._tile_popover = None
        self._nav.render()   # restore the tiles-screen hints

    # ── Generic top-bar overlays (Network / Notifications) ─────────────────

    def present(self, overlay: BaseOverlay) -> None:
        """Track a freshly opened top-bar overlay; return focus to the bar when
        it closes. The registry then pauses/resumes/cancels it with the group."""
        self._overlays.register(overlay)
        overlay.closed.connect(lambda: self._on_overlay_closed(overlay))

    def _on_overlay_closed(self, overlay: BaseOverlay) -> None:
        self._overlays.forget(overlay)
        self._nav.focus_topbar()
