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

GLYPH_SIZE = 26   # diameter of a button glyph / height of a direction arrow
ICON_PX    = 15   # inner icon size for icon-based glyphs (home / start / arrows)
BAR_HEIGHT = 56   # the rounded bar itself
BOTTOM_GAP = 10   # gap between the bar and the screen edge
SURFACE_H  = BAR_HEIGHT + BOTTOM_GAP   # total height of the bottom strip surface

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


class HintBar(QWidget, HintBarView, metaclass=ProtocolQtMeta):
    """Standalone bottom bar rendering the per-screen gamepad hints."""

    def __init__(self) -> None:
        super().__init__()
        # Own top-level window: frameless, translucent (only the rounded bar is
        # opaque, the surrounding strip is transparent), and click-through.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        self.setFixedHeight(SURFACE_H)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 0, 16, BOTTOM_GAP)
        outer.setSpacing(0)

        bar = QWidget()
        bar.setObjectName("hintbar")
        bar.setFixedHeight(BAR_HEIGHT)
        bar.setStyleSheet(
            "#hintbar {"
            "  background-color: rgba(15, 17, 25, 210);"
            "  border: 1px solid black;"
            "  border-radius: 12px;"
            "}"
        )
        outer.addWidget(bar)

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
            exclusive_zone=0,
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
        # Layer-shell positions/sizes the surface from its anchors; elsewhere
        # (Windows topmost window, X11) anchor it to the bottom strip by hand.
        if QGuiApplication.platformName() != "wayland":
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                self.setGeometry(area.x(), area.bottom() - SURFACE_H + 1,
                                 area.width(), SURFACE_H)

    # ── HintBarView port ─────────────────────────────────────────────────────

    def show_hints(self, hints: Hints) -> None:
        self._clear()
        self._row.addWidget(self._directions(hints.directions, hints.nav_label))
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

    def _button_glyph(self, button: Button) -> QLabel:
        if button in _LETTER_BUTTONS:
            letter, bg, fg = _LETTER_BUTTONS[button]
            return self._disc_letter(letter, bg, fg)
        return self._disc_icon(_ICON_BUTTONS[button])

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
