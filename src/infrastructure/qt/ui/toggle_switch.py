"""An animated on/off toggle switch — a pill with a sliding circle.

A presentation-only control: it renders a checked/unchecked state and animates
the slide between them, but does not own the state. Callers drive it with
:meth:`ToggleSwitch.set_on` (the onboarding picker, for instance, keeps the
truth in its :class:`AppSelection` and reflects it here), so the switch is
transparent to mouse events and never decides its own value.
"""

from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QAbstractButton

from infrastructure.qt.ui import styles

_MARGIN     = 3      # gap between the circle and the pill edge
_ANIM_MS    = 220


class ToggleSwitch(QAbstractButton):
    """A pill-shaped on/off switch with a knob that slides smoothly between states."""

    def __init__(
        self,
        parent=None,
        width: int = 64,
        height: int = 30,
        off_color: str = "#4c566a",
        knob_color: str = styles.COLOR_TEXT,
        # Deeper Nord frost blue: coherent with KD yet distinct from the accent
        # used to highlight the focused row, so the switch stays visible on it.
        on_color: str = "#5e81ac",
    ) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        # The switch only displays state; the row beneath it handles the click.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.resize(width, height)

        self._off_color  = off_color
        self._knob_color = knob_color
        self._on_color   = on_color
        self._circle_position = float(_MARGIN)

        self._anim = QPropertyAnimation(self, b"circle_position")
        self._anim.setDuration(_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── State (driven by the caller) ─────────────────────────────────────────

    def set_on(self, on: bool, *, animate: bool = True) -> None:
        """Reflect *on*, sliding the knob there (or snapping when ``animate`` is
        False — used to seed the initial state without a startup animation)."""
        self.setChecked(on)
        target = self._on_position() if on else float(_MARGIN)
        if animate:
            self._anim.stop()
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.circle_position = target

    def _on_position(self) -> float:
        """Left edge of the knob in its 'on' (right) resting place."""
        return float(self.width() - self.height() + _MARGIN)

    # ── Animated property ─────────────────────────────────────────────────────

    @pyqtProperty(float)
    def circle_position(self) -> float:
        return self._circle_position

    @circle_position.setter
    def circle_position(self, pos: float) -> None:
        self._circle_position = pos
        self.update()

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        radius = self.height() / 2
        painter.setBrush(QColor(self._on_color if self.isChecked() else self._off_color))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), radius, radius)

        painter.setBrush(QColor(self._knob_color))
        knob = self.height() - 2 * _MARGIN
        painter.drawEllipse(int(self._circle_position), _MARGIN, knob, knob)
