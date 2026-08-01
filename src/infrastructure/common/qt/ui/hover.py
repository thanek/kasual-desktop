from PyQt6.QtCore import QPoint, pyqtSignal
from PyQt6.QtGui import QCursor


class HoverReporting:
    """Emits ``hovered`` on real pointer entries only — an enter at the position
    latched by the last leave is Qt mapping the widget under a parked cursor.

    Mix in before the QWidget base: PyQt dispatches virtual events to class
    methods only.
    """

    hovered = pyqtSignal()

    _pos_at_leave: QPoint | None = None

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        synthetic = event.globalPosition().toPoint() == self._pos_at_leave
        self._pos_at_leave = None
        if not synthetic:
            self.hovered.emit()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._pos_at_leave = QCursor.pos()
