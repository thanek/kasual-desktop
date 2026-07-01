"""Bottom hint bar: what the gamepad buttons do on the current screen.

A standalone surface — its own layer-shell window anchored to the bottom edge,
the sibling of the Desktop and the Home Overlay rather than a child of either.
That independence is the point: when the (animated) Home Overlay appears the
hint bar stays put and merely swaps its content, instead of fading out with one
host and back in with the next.

The left side shows the available directional navigation and the BTN_MODE / home
button; the right side shows the action buttons with what they do. Which hints to
show is the navigation domain's decision (:mod:`domain.navigation.hints`); this
widget only renders the :class:`Hints` pushed via :meth:`show_hints` (the
``HintBarView`` port). The Desktop owns the single instance and drives its
show/hide (see ``Desktop._sync_hint_visibility``).
"""

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QGuiApplication, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from domain.navigation.bar_views import HintBarView
from domain.navigation.hints import Button, Direction, Hints
from domain.shared.i18n import translate
from infrastructure.common.qt._meta import ProtocolQtMeta
from infrastructure.common.qt.ui.layer_shell import Anchor, Keyboard, Layer
from infrastructure.common.qt.ui.top_surface import promote_overlay_surface
from infrastructure.common.qt.overlays.home_menu_content import CARD_WIDTH

GLYPH_SIZE = 26      # diameter of a button glyph / height of a direction arrow
ICON_PX    = 15      # inner icon size for icon-based glyphs (home / start / arrows)
BAR_HEIGHT = 60      # the rounded bar itself
BOTTOM_MARGIN = 10   # gap from the bar bottom to the screen edge (matches TopBar top margin)
SURFACE_H  = BAR_HEIGHT + BOTTOM_MARGIN   # total height of the bottom strip surface

# Direction → Font Awesome arrow glyph.
_ARROWS = {
    Direction.LEFT:  "fa5s.arrow-left",
    Direction.RIGHT: "fa5s.arrow-right",
    Direction.UP:    "fa5s.arrow-up",
    Direction.DOWN:  "fa5s.arrow-down",
}

# A face button → its lettered, colour-coded glyph (Xbox convention).
_LETTER_BUTTONS = {
    Button.A: ("A", "#3a9b35", "white"),   # green
    Button.B: ("B", "#cc3a3a", "white"),   # red
    Button.Y: ("Y", "#e0b00f", "black"),   # yellow
}

# A button drawn as an icon in a neutral disc instead of a letter.
_ICON_BUTTONS = {
    Button.START: "fa5s.bars",
    Button.HOME:  "fa5s.home",
}

# Shoulder buttons (bumpers / triggers) drawn as a short label in a rounded pill.
_SHOULDER_BUTTONS = {
    Button.LB: "LB",
    Button.RB: "RB",
    Button.LT: "LT",
    Button.RT: "RT",
}


class HintBar(QWidget, HintBarView, metaclass=ProtocolQtMeta):
    """Standalone bottom bar rendering the per-screen gamepad hints."""

    def __init__(self) -> None:
        super().__init__()
        self._current_hints: Hints | None = None
        # Own top-level window: frameless, translucent (only the rounded bar is
        # opaque, the surrounding strip is transparent), and click-through.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        self.setFixedHeight(SURFACE_H)

        outer = QVBoxLayout(self)
        # Pin the bar to the BOTTOM of the surface with a fixed BOTTOM_MARGIN gap.
        # The stretch sits *above* the bar, so if the compositor hands the surface
        # more height than SURFACE_H (seen on some layer-shell setups), the extra
        # space opens above the bar and the gap below it stays exactly
        # BOTTOM_MARGIN — symmetric with the TopBar's top margin.
        outer.setContentsMargins(16, 0, 16, BOTTOM_MARGIN)
        outer.setSpacing(0)

        bar = QWidget()
        bar.setObjectName("hintbar")
        bar.setFixedHeight(BAR_HEIGHT)
        bar.setFixedWidth(CARD_WIDTH)
        bar.setStyleSheet(
            "#hintbar {"
            "  background-color: #2e3440;"
            "  border-radius: 30px;"
            "}"
        )
        outer.addStretch(1)   # absorbs any surplus surface height above the bar
        outer.addWidget(bar, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Cleared and rebuilt on every show_hints — the screens differ in which
        # actions they offer, so re-laying out is simpler than diffing.
        self._row = QHBoxLayout(bar)
        self._row.setContentsMargins(20, 0, 20, 0)
        self._row.setSpacing(0)

    # ── Surface ──────────────────────────────────────────────────────────────

    def install_surface(self) -> None:
        """Promote to a layer-shell surface anchored across the bottom edge, in
        the overlay layer so it floats above the Desktop (and above fullscreen
        apps when the Home Overlay summons it). Off Wayland this is a no-op and
        :meth:`showEvent` positions the plain top-level window instead."""
        promote_overlay_surface(
            self,
            layer=Layer.OVERLAY,
            anchors=Anchor.BOTTOM | Anchor.LEFT | Anchor.RIGHT,
            # -1 (not 0): anchor to the *true* bottom edge and don't let the
            # compositor shove us up to clear another panel's exclusive zone
            # (e.g. a KDE bottom panel in a dev session lifted the bar by its
            # whole height). Matches the Desktop surface, which anchors flush.
            exclusive_zone=-1,
            keyboard=Keyboard.NONE,
        )

    def paintEvent(self, event) -> None:
        # The bar background is semi-transparent, so a repaint that doesn't first
        # wipe the layer-shell buffer composites the new background over the old
        # one and darkens the bar (seen once, on the first content swap). Clear
        # the whole surface to transparent — Source mode replaces rather than
        # blends — before the child widgets paint over it.
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(event.rect(), Qt.GlobalColor.transparent)

    def showEvent(self, event) -> None:
        super().showEvent(event)

    # ── Positioning ──────────────────────────────────────────────────────────

    def position_at_bottom(self) -> None:
        """Move the bar to the bottom strip of the primary screen.

        Called by the Desktop *before* show() on platforms that do not support
        layer-shell positioning (Windows / X11).  On Wayland the compositor
        places the surface via its layer-shell anchors, so this is a no-op
        there — those anchors were already set in :meth:`install_surface`."""
        if QGuiApplication.platformName() == "wayland":
            return
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            g = screen.geometry()
            self.setGeometry(
                g.x(), g.bottom() - SURFACE_H + 1,
                g.width(), SURFACE_H,
            )

    # ── HintBarView port ─────────────────────────────────────────────────────

    def show_hints(self, hints: Hints) -> None:
        if hints is self._current_hints:
            return
        self._current_hints = hints
        self._clear()
        if hints.directions:
            self._row.addWidget(self._directions(hints.directions, hints.nav_label))
            self._row.addSpacing(20)
        # A second directional cluster (e.g. ◄► Adjust on the slider screen),
        # rendered right after the first so the two axes read apart.
        if hints.adjust:
            self._row.addWidget(self._directions(hints.adjust, hints.adjust_label))
            self._row.addSpacing(20)
        # Bumpers (LB/RB) switch overlay sections — rendered as a glyph pair with a
        # single shared label, right after the directional cluster.
        if hints.bumpers:
            self._row.addWidget(self._pair(hints.bumpers))
            self._row.addSpacing(20)
        self._row.addWidget(self._hint(self._button_glyph(hints.overlay.button),
                                       hints.overlay.label))
        self._row.addStretch(1)
        for i, action in enumerate(hints.actions):
            if i:
                self._row.addSpacing(22)
            self._row.addWidget(self._hint(self._button_glyph(action.button),
                                           action.label))
        # Lay out the new glyphs and redraw the whole surface *now*, in one go.
        # A deferred update() repaints only on the next event-loop tick — long
        # enough, on the first transition, for the stale frame (old content) to
        # stay on screen. Activating the layout first means the immediate repaint
        # already draws the new glyphs at their final positions.
        self.layout().activate()
        self.repaint()

    # ── Building blocks ──────────────────────────────────────────────────────

    def _clear(self) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Hide now (so it stops painting immediately) but keep it parented
                # — setParent(None) would briefly turn each old glyph into its own
                # stray top-level window on KWin. deleteLater() then disposes it.
                widget.hide()
                widget.deleteLater()

    def _hint(self, glyph: QWidget, label: str) -> QWidget:
        """A glyph followed by its localized description."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(glyph)
        row.addWidget(self._label(translate("HintBar", label)))
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        holder.setLayout(row)
        return holder

    def _directions(self, directions: tuple[Direction, ...], nav_label: str) -> QWidget:
        """The available direction arrows followed by their cluster label."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for direction in directions:
            row.addWidget(self._arrow(direction))
        row.addSpacing(4)
        row.addWidget(self._label(translate("HintBar", nav_label)))
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        holder.setLayout(row)
        return holder

    def _arrow(self, direction: Direction) -> QLabel:
        lbl = QLabel()
        lbl.setFixedSize(GLYPH_SIZE, GLYPH_SIZE)
        lbl.setStyleSheet("background: transparent;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setPixmap(qta.icon(_ARROWS[direction], color="white")
                      .pixmap(QSize(ICON_PX + 3, ICON_PX + 3)))
        return lbl

    def _pair(self, pair: tuple, ) -> QWidget:
        """Two shoulder-button glyphs sharing one label (e.g. ``LB RB  Section``)."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for hint in pair:
            row.addWidget(self._button_glyph(hint.button))
        row.addSpacing(4)
        row.addWidget(self._label(translate("HintBar", pair[0].label)))
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        holder.setLayout(row)
        return holder

    def _button_glyph(self, button: Button) -> QLabel:
        if button in _LETTER_BUTTONS:
            letter, bg, fg = _LETTER_BUTTONS[button]
            return self._disc_letter(letter, bg, fg)
        if button in _SHOULDER_BUTTONS:
            return self._pill(_SHOULDER_BUTTONS[button])
        return self._disc_icon(_ICON_BUTTONS[button])

    def _pill(self, text: str) -> QLabel:
        """A short label (LB/RB/LT/RT) in a rounded pill, wider than a disc."""
        lbl = QLabel(text)
        lbl.setFixedSize(GLYPH_SIZE + 12, GLYPH_SIZE)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"background-color: #3b4252; color: white;"
            f" border-radius: {GLYPH_SIZE // 2}px;"
            "  font-weight: bold; font-size: 12px;"
        )
        return lbl

    def _disc_letter(self, letter: str, bg: str, fg: str) -> QLabel:
        lbl = QLabel(letter)
        lbl.setFixedSize(GLYPH_SIZE, GLYPH_SIZE)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"background-color: {bg}; color: {fg};"
            f" border-radius: {GLYPH_SIZE // 2}px;"
            "  font-weight: bold; font-size: 14px;"
        )
        return lbl

    def _disc_icon(self, glyph: str) -> QLabel:
        lbl = QLabel()
        lbl.setFixedSize(GLYPH_SIZE, GLYPH_SIZE)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"background-color: #3b4252; border-radius: {GLYPH_SIZE // 2}px;"
        )
        lbl.setPixmap(qta.icon(glyph, color="white").pixmap(QSize(ICON_PX, ICON_PX)))
        return lbl

    @staticmethod
    def _label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #d8dee9; font-size: 14px; background: transparent;"
        )
        return lbl
