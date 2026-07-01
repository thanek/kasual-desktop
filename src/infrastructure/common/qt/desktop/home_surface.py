"""Persistent Home surface — the unified collapse/expand chrome and menu (§8 / Faza 5).

One surface serves the Home Overlay menu in every context (`UX.md` §8), so the
status header + menu + hint bar always read as one composition:

  * **Context 1 — Home view.** The surface is permanently mapped: a collapsed
    :class:`HomeHeader` (clock + date + Network/Notifications) that morphs open on
    BTN_MODE into header + §7.10 menu and back, on one never-unmapped surface (the
    property the Faza 5 PoC verified — no map/unmap, so KWin adds no animation).
    The Desktop drives it via :meth:`expand` / :meth:`collapse`, and hands the
    header to the FocusNavigator as the top bar so "up" from the tiles enters it.

  * **Contexts 2/3 — over an app / Kasual minimized.** The controller drives it as
    a :class:`~domain.shell.overlay.SectionedHomeOverlay`: :meth:`show_for_context`
    maps it straight to the expanded layout, :meth:`hide_overlay` unmaps it. No
    persistent surface lingers over a fullscreen game.

Either way the expanded menu embeds the shared :class:`HomeMenuContent` with the
header as its navigable zone 0, so "up" from the top section flows into the
header. The surface is gamepad-driven: showing/expanding pushes the content's pad
handler, hiding/collapsing pops it.
"""

import logging
from collections.abc import Callable

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, pyqtSignal,
)
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGraphicsOpacityEffect

from domain.catalog.target import Target
from domain.input.pad_control import PadControl
from domain.menu.item import MenuItem
from domain.shared.event_emitter import Unsubscribe
from domain.shared.feedback import Cue, Feedback
from domain.system.brightness import BrightnessControl
from domain.system.hud import HudControl
from domain.system.power_menu import PowerMenu
from domain.system.volume import VolumeControl
from infrastructure.common.qt.ui import styles
from infrastructure.common.qt.ui.layer_shell import Anchor, Keyboard, Layer
from infrastructure.common.qt.ui.top_surface import promote_overlay_surface
from infrastructure.common.qt.overlays.home_header import HEADER_H, HomeHeader
from infrastructure.common.qt.overlays.home_menu_content import CARD_WIDTH, HomeMenuContent

logger = logging.getLogger(__name__)

TOP_MARGIN  = 10    # gap from the screen top to the header (mirrors the hint bar)
CONTENT_H   = 380   # expanded panel's content area (the §7.10 menu sits within)
MORPH_MS    = 180   # collapse↔expand animation duration
# The surface is ALWAYS this tall (sized for the expanded state) and anchored to
# the top: collapse/expand only morphs the inner content, never the surface — so
# KWin never sees a resize/remap to animate (the PoC's verified property).
SURFACE_H   = TOP_MARGIN + HEADER_H + CONTENT_H + TOP_MARGIN


class _NullHud(HudControl):
    """A HUD that is never available — the Home view (context 1) never offers the
    in-game HUD toggle, and :func:`domain.menu.home.compose_home_sections` omits
    the HUD section when there is no foreground app, so this is only a
    type-satisfying placeholder for the embedded content."""

    def is_available(self) -> bool: return False
    def is_enabled(self) -> bool: return False
    def enable(self) -> None: ...
    def disable(self) -> None: ...


class HomeSurface(QWidget):
    """The Home view's persistent collapse/expand surface, doubling as the
    map-on-demand Home Overlay for contexts 2/3 (a SectionedHomeOverlay)."""

    closed = pyqtSignal()

    def __init__(
        self,
        gamepad: PadControl,
        feedback: Feedback,
        volume: VolumeControl,
        brightness: BrightnessControl,
        power: PowerMenu,
        header: HomeHeader,
        *,
        on_action: Callable[[MenuItem], None],
        on_power_chooser: Callable[[], None],
        begin_hints: Callable[[], None],
        set_hints: Callable,
        end_hints: Callable[[], None],
    ) -> None:
        super().__init__()
        self._gamepad = gamepad
        self._feedback = feedback
        self._on_action = on_action          # context-1 dispatch (Desktop)
        self._on_power_chooser = on_power_chooser   # header Power → default chooser
        self._begin_hints = begin_hints
        self._set_hints = set_hints
        self._end_hints = end_hints
        self._expanded = False               # morphed open in the Home view (ctx 1)
        self._on_demand = False              # mapped open over an app / minimized (ctx 2/3)

        self.setWindowTitle("Kasual Home")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Gamepad-driven, like the hint bar: never intercept the pointer, so the
        # transparent area below the collapsed header never blocks the tiles.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        self.setFixedHeight(SURFACE_H)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, TOP_MARGIN, 16, TOP_MARGIN)
        outer.setSpacing(12)
        outer.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        # The header is created early by the Desktop (it doubles as the
        # FocusNavigator's top bar before this surface exists) and reparented here.
        self._header = header
        outer.addWidget(self._header, alignment=Qt.AlignmentFlag.AlignHCenter)

        # The expanded §7.10 menu, embedded under the header inside a fixed-width
        # card. Its max-height + opacity are animated for the morph; collapsed it
        # is fully shrunk and transparent (but still mapped — no unmap).
        self._panel = styles.make_card(CARD_WIDTH)
        panel_col = QVBoxLayout(self._panel)
        panel_col.setContentsMargins(28, 22, 28, 22)
        self._content = HomeMenuContent(feedback, volume, brightness, power)
        panel_col.addWidget(self._content)
        outer.addWidget(self._panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)

        self._opacity = QGraphicsOpacityEffect(self._panel)
        self._opacity.setOpacity(0.0)
        self._panel.setGraphicsEffect(self._opacity)
        self._panel.setMaximumHeight(0)

        self._anim = QParallelAnimationGroup(self)
        self._a_h = QPropertyAnimation(self._panel, b"maximumHeight")
        self._a_h.setDuration(MORPH_MS)
        self._a_h.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a_o = QPropertyAnimation(self._opacity, b"opacity")
        self._a_o.setDuration(MORPH_MS)
        self._anim.addAnimation(self._a_h)
        self._anim.addAnimation(self._a_o)

    @property
    def header(self) -> HomeHeader:
        """The status header, handed to the FocusNavigator as the Home view's top
        bar (so "up" from the tiles enters it)."""
        return self._header

    def is_expanded(self) -> bool:
        """Whether the menu is morphed open in the Home view (context 1)."""
        return self._expanded

    def is_open(self) -> bool:
        """Whether the menu is currently shown — morphed open (ctx 1) or mapped on
        demand (ctx 2/3). The Desktop's visibility sync keeps the surface on screen
        while this holds even when the Desktop itself is down."""
        return self._expanded or self._on_demand

    # ── Surface ────────────────────────────────────────────────────────────────

    def install_surface(self) -> None:
        """Promote to a layer-shell surface anchored across the top edge, in the
        overlay layer so the expanded panel floats above the Desktop tiles. Off
        Wayland this is a no-op and :meth:`position_at_top` places the window."""
        promote_overlay_surface(
            self,
            layer=Layer.OVERLAY,
            anchors=Anchor.TOP | Anchor.LEFT | Anchor.RIGHT,
            exclusive_zone=0,
            keyboard=Keyboard.NONE,
        )

    def position_at_top(self) -> None:
        """Place the surface along the top strip of the primary screen (Windows /
        X11). On Wayland the compositor positions it via the layer-shell anchors,
        so this is a no-op there."""
        if QGuiApplication.platformName() == "wayland":
            return
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            g = screen.geometry()
            self.setGeometry(g.x(), g.y(), g.width(), SURFACE_H)

    # ── Context 1: persistent morph (driven by the Desktop) ──────────────────

    def expand(self) -> None:
        """Morph open in the Home view: build the §7.10 content (bare-Home context),
        take the pad, animate the panel in. The header stays put throughout."""
        if self._expanded:
            return
        self._expanded = True
        self._content.configure(
            foreground=None, foreground_is_game=False, hud=_NullHud(),
            on_action=self._on_action, on_cancel=None,
            set_hints=self._set_hints, request_hide=self.dismiss,
            header=self._header, on_power_chooser=self._on_power_chooser,
        )
        self._panel.show()   # unhide the panel collapsed teardown hid (see below)
        self._begin_hints()
        self._gamepad.push_handler(self._content.handle_pad)
        self._feedback.play(Cue.POPUP_OPEN)
        self._morph(open_=True)

    def collapse(self) -> None:
        """Morph closed: drop the pad, restore the screen hints, animate away.
        Silent — the content's own A/B feedback already played; a plain BTN_MODE
        close mirrors the overlay's silent hide."""
        if not self._expanded:
            return
        self._expanded = False
        self._teardown_menu()
        self._morph(open_=False)
        self._end_hints()

    def collapse_immediately(self) -> None:
        """Snap to the collapsed visuals with no animation and drop the menu if it
        was open (used when the Desktop hides, so the surface is already collapsed
        when it next appears). Free of hint-bar calls so it never re-enters the
        Desktop's visibility sync."""
        if self.is_open():
            self._teardown_menu()
            self._expanded = False
            self._on_demand = False
        self._anim.stop()
        self._panel.setMaximumHeight(0)
        self._opacity.setOpacity(0.0)
        # Hide the panel widget outright and force a fresh frame: a re-mapped
        # layer-shell surface keeps showing its last (expanded) buffer until Qt
        # commits a new one, and setting maxHeight/opacity while unmapped triggers
        # no repaint — so the old menu lingers as a dead (non-interactive) ghost.
        self._panel.hide()
        if self.isVisible():
            self.repaint()
            # And once more after the re-map settles: right after show() the
            # surface may not be ready to commit, so a synchronous repaint alone
            # can miss and leave the ghost.
            QTimer.singleShot(0, self.repaint)

    def dismiss(self) -> None:
        """Close whichever menu is live — the on-demand overlay (contexts 2/3) or
        the context-1 morph. Wired as the embedded content's ``request_hide`` in
        *both* contexts, so activating an item (e.g. "Return to Home screen") tears
        down the mode that is actually open rather than the one whose teardown
        happened to be wired last on the shared content — the two ``if not <flag>:
        return`` guards otherwise let a stale wiring no-op, leaving the menu up."""
        if self._on_demand:
            self.hide_overlay()
        elif self._expanded:
            self.collapse()

    # ── Contexts 2/3: SectionedHomeOverlay (driven by the controller) ─────────

    def show_for_context(
        self,
        foreground: Target | None,
        foreground_is_game: bool,
        hud: HudControl,
        on_action: Callable[[MenuItem], None],
        on_cancel: Callable[[], None] | None,
        set_hints: Callable | None,
        desktop_minimized: bool = False,
    ) -> None:
        """Map the surface straight to the expanded layout over an app / minimized
        Kasual. The controller wires the dispatch (its ``on_action`` handles app
        controls) and brackets the hint bar itself, as for the old overlay."""
        if self.is_open():
            return
        self._on_demand = True
        self._content.configure(
            foreground, foreground_is_game, hud,
            on_action=on_action, on_cancel=on_cancel, set_hints=set_hints,
            request_hide=self.dismiss, desktop_minimized=desktop_minimized,
            header=self._header, on_power_chooser=self._on_power_chooser,
        )
        self.position_at_top()
        self.show()
        self.raise_()
        # No morph here — the surface is being mapped already expanded.
        self._anim.stop()
        self._panel.show()   # undo any prior collapse's panel.hide()
        self._panel.setMaximumHeight(CONTENT_H)
        self._opacity.setOpacity(1.0)
        self._gamepad.push_handler(self._content.handle_pad)
        self._feedback.play(Cue.POPUP_OPEN)

    def hide_overlay(self) -> None:
        """Unmap the on-demand overlay (contexts 2/3). Idempotent."""
        if not self._on_demand:
            return
        self._on_demand = False
        self._teardown_menu()
        self._anim.stop()
        self._panel.setMaximumHeight(0)
        self._opacity.setOpacity(0.0)
        self._panel.hide()
        # Commit the collapsed (empty) frame *while still mapped*, then unmap. The
        # compositor keeps the surface's last buffer after unmap; if we hide()
        # straight from the expanded layout that retained buffer is the menu, which
        # then lingers as a dead, non-interactive ghost when the surface re-maps
        # over the Desktop. repaint() forces the empty frame out before we unmap.
        self.repaint()
        self.hide()
        self.closed.emit()

    def is_showing(self) -> bool:
        return self._on_demand

    def on_closed(self, handler: Callable[[], None]) -> Unsubscribe:
        self.closed.connect(handler)
        return Unsubscribe(lambda: self.closed.disconnect(handler))

    def dispose(self) -> None:
        """No-op: the surface is persistent and reused across presses (unlike the
        per-press overlay it stands in for), so it is never deleted."""

    # ── Shared helpers ────────────────────────────────────────────────────────

    def refresh_hints(self) -> None:
        """Re-push the menu's own hint set — used after a chooser popover that
        floated over the open menu closes (§8)."""
        self._content._sync_hints()

    def _teardown_menu(self) -> None:
        self._content._close_dropdown()
        self._gamepad.pop_handler(self._content.handle_pad)

    def _morph(self, *, open_: bool) -> None:
        self._anim.stop()
        self._a_h.setStartValue(self._panel.maximumHeight())
        self._a_h.setEndValue(CONTENT_H if open_ else 0)
        self._a_o.setStartValue(self._opacity.opacity())
        self._a_o.setEndValue(1.0 if open_ else 0.0)
        self._anim.start()

    # ── Status (delegated to the header — the top bar's old role) ─────────────

    def set_network_icon(self, glyph: str) -> None:
        self._header.set_network_icon(glyph)

    def set_notification_badge(self, count: int) -> None:
        self._header.set_notification_badge(count)


class PersistentOverlayFactory:
    """A SectionedOverlayFactory that always yields the one persistent HomeSurface
    (contexts 2/3), instead of a fresh overlay per press. The surface's
    :meth:`HomeSurface.dispose` is a no-op, so the controller's create/dispose
    lifecycle leaves the reused surface intact."""

    def __init__(self, surface: HomeSurface) -> None:
        self._surface = surface

    def create_home_overlay(self) -> HomeSurface:
        return self._surface
