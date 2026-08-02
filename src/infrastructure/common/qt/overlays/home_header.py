"""HomeHeader — the navigable status header that replaces the top bar.

The collapsed chrome of the Home view and the top row of the expanded Home menu,
in one widget: a clock + date readout (status) plus two focusable buttons,
Network and Notifications (the top bar's old action buttons that stayed at the
top; Power moved into the menu's split-button). The notification badge rides the
bell button.

It is navigable in two alternating roles, never both at once:

  * **Collapsed Home view** — the FocusNavigator drives it as the ``TopBarView``
    (``count`` / ``set_selected`` / ``trigger``): "up" from the tiles enters it,
    ``A`` triggers the focused button.
  * **Expanded Home menu** — :class:`HomeMenuContent` treats it as zone 0
    (``nav_items``): "up" from the menu's top section flows into it, and a
    selection dispatches through the menu's ``on_action`` instead.

Both roles ultimately open the same Network / Notifications overlay, so a single
``on_activate(action)`` callback backs the FocusNavigator's ``trigger`` path.
"""

import qtawesome as qta
from collections.abc import Callable

from PyQt6.QtCore import Qt, QSize, QTimer, QLocale, QRectF, QEvent, pyqtSignal
from PyQt6.QtGui import QCursor, QColor, QPainter, QPixmap
from datetime import datetime
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from domain.menu.item import MenuItem
from domain.menu.entry import POWER
from domain.system.actions import ACTIONS, NETWORK, NOTIFICATIONS
from domain.shared.i18n import translate
from infrastructure.common.qt.ui import styles
from infrastructure.common.qt.ui.hover import HoverReporting

HEADER_H = 80    # matches the old top bar / hint bar height
_BTN     = 56
# Far right is Power: a chooser for the default sleep/restart/shutdown action.
# It carries the abstract POWER key; the host opens the dropdown.
_NAV_KEYS  = (NETWORK, NOTIFICATIONS, POWER)
_POWER_GLYPH = "fa5s.power-off"

# The focused-button look — a light translucent fill behind a thin accent border.
# The whole header wears it too (its resting background), so bar and buttons read
# as one family.
_FOCUS_FILL   = "rgba(136, 192, 208, 60)"
_FOCUS_BORDER = styles.COLOR_ACCENT

_BADGE_SIZE     = 18
_BADGE_GLYPH    = "fa5s.chevron-down"
_BADGE_INK      = "white"
_BADGE_INK_SEL  = styles.COLOR_BG_DARK
# _FOCUS_FILL flattened onto the header: a translucent fill is invisible while
# the button behind it is unselected.
_BADGE_FILL     = "#43555f"

# The grab handle: a wide-but-thin pull at the bottom of the pill (mouse path
# into the menu). Its hit target is generous; only the centred bar is drawn.
_HANDLE_W, _HANDLE_H         = 120, 16
_HANDLE_BAR_W, _HANDLE_BAR_H = 88, 5
_HANDLE_BOTTOM_INSET         = 5
_HANDLE_IDLE    = QColor(255, 255, 255, 46)    # discreet at rest
_HANDLE_HOVER   = QColor(159, 214, 226, 230)   # accent while the header is hovered
_HANDLE_FOCUSED = QColor(_FOCUS_BORDER)        # accent while the Home menu it opens is visible


class _GrabHandle(QWidget):
    """The pull at the bottom of the header pill: click toggles the Home menu. It
    rests as a faint notch and lifts to the accent while the pointer is anywhere
    over the header, so the whole bar reads as the handle."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_HANDLE_W, _HANDLE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prominent = False
        self._focused = False

    def pin_to(self, bottom_edge: int) -> None:
        """Centre on the current parent, riding *bottom_edge* in its coordinates."""
        self.move((self.parentWidget().width() - self.width()) // 2,
                  bottom_edge - self.height() - _HANDLE_BOTTOM_INSET)

    def set_prominent(self, prominent: bool) -> None:
        if prominent == self._prominent:
            return
        self._prominent = prominent
        self.update()

    def set_focused(self, focused: bool) -> None:
        """Wears the accent look while the Home menu it toggles is visible,
        independent of hover — it stays lit even once the pointer moves onto
        the menu itself."""
        if focused == self._focused:
            return
        self._focused = focused
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if self._focused:
            painter.setBrush(_HANDLE_FOCUSED)
        elif self._prominent:
            painter.setBrush(_HANDLE_HOVER)
        else:
            painter.setBrush(_HANDLE_IDLE)
        bar = QRectF((self.width() - _HANDLE_BAR_W) / 2,
                     (self.height() - _HANDLE_BAR_H) / 2,
                     _HANDLE_BAR_W, _HANDLE_BAR_H)
        painter.drawRoundedRect(bar, _HANDLE_BAR_H / 2, _HANDLE_BAR_H / 2)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.pos())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


def _header_style(docked: bool) -> str:
    bottom = 0 if docked else styles.PILL_RADIUS
    return "#homeheader {" + styles.pill_background(bottom=bottom) + "}"


def _btn_style(selected: bool) -> str:
    if selected:
        return (f"background-color: {_FOCUS_FILL}; border: 2px solid {_FOCUS_BORDER};"
                f" border-radius: {_BTN // 2}px;")
    return f"background: transparent; border: 2px solid transparent; border-radius: {_BTN // 2}px;"


def _badge_style(selected: bool) -> str:
    fill = _FOCUS_BORDER if selected else _BADGE_FILL
    return f"background-color: {fill}; border: none; border-radius: {_BADGE_SIZE // 2}px;"


def _badge_pixmap(selected: bool) -> QPixmap:
    ink = _BADGE_INK_SEL if selected else _BADGE_INK
    return qta.icon(_BADGE_GLYPH, color=ink).pixmap(QSize(10, 10))


class _HeaderButton(HoverReporting, QPushButton):
    right_clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:
        # Right-click opens the button's dropdown; the host decides which
        # buttons have one.
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
        else:
            super().mousePressEvent(event)


class HomeHeader(QWidget):
    """Clock + date + focusable Network / Notifications buttons (a TopBarView)."""

    # Mouse parity with the tile bar: hover moves the highlight onto a button,
    # a click activates it. Both carry the button index; the Desktop routes them
    # through the FocusNavigator, exactly like the gamepad path.
    button_hovered      = pyqtSignal(int)
    button_activated    = pyqtSignal(int)
    button_context_menu = pyqtSignal(int)   # right-click → the button's dropdown (Power)
    toggle_requested    = pyqtSignal()      # grab-handle click → open/close the menu

    def __init__(self, on_activate: Callable[[str], None], width: int) -> None:
        super().__init__()
        self._on_activate = on_activate
        self._selected: int | None = None

        self.setObjectName("homeheader")
        self.setFixedHeight(HEADER_H)
        self.setFixedWidth(width)
        # A QWidget subclass ignores an objectName-scoped background unless told to
        # honour it (unlike the plain-QWidget bars elsewhere) — without this the
        # header renders fully transparent over the wallpaper.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._docked = False
        self.setStyleSheet(_header_style(False))
        row = QHBoxLayout(self)
        row.setContentsMargins(24, 0, 16, 0)

        lbl_style = "font-size: 26px; color: white; background: transparent; border: none;"
        self._date_lbl = QLabel()
        self._date_lbl.setStyleSheet(lbl_style)
        row.addWidget(self._date_lbl)
        row.addSpacing(18)
        self._clock_lbl = QLabel()
        self._clock_lbl.setStyleSheet(lbl_style)
        row.addWidget(self._clock_lbl)

        row.addStretch(1)

        self._net_btn = self._make_button("fa5s.question")
        row.addWidget(self._net_btn)
        row.addSpacing(8)
        self._notif_btn = self._make_button("fa5s.bell")
        row.addWidget(self._notif_btn)
        row.addSpacing(8)
        # Far right: the Power chooser (sleep / restart / shut down — sets the
        # default). A on it opens the dropdown; the host does the rest.
        self._power_btn = self._make_button(_POWER_GLYPH)
        row.addWidget(self._power_btn)

        for i, btn in enumerate((self._net_btn, self._notif_btn, self._power_btn)):
            btn.hovered.connect(lambda i=i: self.button_hovered.emit(i))
            btn.clicked.connect(lambda _, i=i: self.button_activated.emit(i))
            btn.right_clicked.connect(lambda i=i: self.button_context_menu.emit(i))

        # Notification count badge in the bell button's corner (hidden at 0).
        self._notif_badge = QLabel(self._notif_btn)
        self._notif_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notif_badge.setStyleSheet(
            "background-color: #bf616a; color: white; font-size: 10px;"
            " font-weight: bold; border: none; border-radius: 9px;")
        self._notif_badge.setFixedSize(18, 18)
        self._notif_badge.move(_BTN - 20, 2)
        self._notif_badge.hide()

        # Chevron badge in the Power button's bottom-right corner — the cue that
        # it is a split-button (A opens the dropdown to change its default). Sits
        # opposite the notification count badge so the two never collide.
        self._power_badge = QLabel(self._power_btn)
        self._power_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._power_badge.setFixedSize(_BADGE_SIZE, _BADGE_SIZE)
        self._power_badge.move(_BTN - _BADGE_SIZE - 2, _BTN - _BADGE_SIZE - 2)
        self._style_power_badge(selected=False)

        self._buttons = [self._net_btn, self._notif_btn, self._power_btn]

        self._handle = _GrabHandle(self)
        self._handle.clicked.connect(self.toggle_requested)
        self.installEventFilter(self)
        for w in (*self._buttons, self._handle):
            w.installEventFilter(self)

        self._tick_clock()
        timer = QTimer(self)
        timer.timeout.connect(self._tick_clock)
        timer.start(1000)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._handle.parentWidget() is self:   # not while the surface has it
            self._handle.pin_to(self.height())
            self._handle.raise_()

    def eventFilter(self, obj, event) -> bool:
        # Re-evaluate on the next tick: the header gets no Leave when the pointer
        # exits a child straight to the outside, so trust the cursor position, not
        # which sub-widget the enter/leave came from.
        if event.type() in (QEvent.Type.Enter, QEvent.Type.Leave):
            QTimer.singleShot(0, self._sync_handle_prominence)
        return super().eventFilter(obj, event)

    def _sync_handle_prominence(self) -> None:
        inside = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        self._handle.set_prominent(inside)

    def _make_button(self, glyph: str) -> _HeaderButton:
        btn = _HeaderButton()
        btn.setFixedSize(_BTN, _BTN)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setIcon(qta.icon(glyph, color="white"))
        btn.setIconSize(QSize(24, 24))
        btn.setStyleSheet(_btn_style(False))
        return btn

    def _style_power_badge(self, *, selected: bool) -> None:
        self._power_badge.setStyleSheet(_badge_style(selected))
        self._power_badge.setPixmap(_badge_pixmap(selected))
        self._power_badge.raise_()

    def set_docked(self, docked: bool) -> None:
        """Docked: the Home menu panel stands on the bottom edge. The corners they
        share are square and the handle, which the host re-pins to that panel, wears
        the accent."""
        if docked == self._docked:
            return
        self._docked = docked
        self.setStyleSheet(_header_style(docked))
        self._handle.set_focused(docked)

    def grab_handle(self) -> _GrabHandle:
        """The pull that toggles the Home menu. The host re-pins it while docked."""
        return self._handle

    def power_button(self) -> QPushButton:
        """The Power button, so the host can anchor the chooser popover below it."""
        return self._power_btn

    # ── Status setters (driven by the Desktop, like the old top bar) ──────────

    def set_network_icon(self, glyph: str) -> None:
        self._net_btn.setIcon(qta.icon(glyph, color="white"))

    def set_power_icon(self, glyph: str) -> None:
        """Mirror the persisted default action on the Power button (e.g. a moon
        glyph when A would sleep), so the icon reads what a press will do."""
        self._power_btn.setIcon(qta.icon(glyph, color="white"))

    def set_notification_badge(self, count: int) -> None:
        if count <= 0:
            self._notif_badge.hide()
            return
        self._notif_badge.setText(str(count) if count <= 9 else "9+")
        self._notif_badge.show()
        self._notif_badge.raise_()

    # ── TopBarView (FocusNavigator drives the collapsed Home view) ────────────

    @property
    def count(self) -> int:
        return len(_NAV_KEYS)

    @property
    def default_index(self) -> int:
        """Entering the header lands on Power (the primary action), not the
        left-most Network button."""
        return _NAV_KEYS.index(POWER)

    def set_selected(self, index: int | None) -> None:
        self._selected = index
        for i, btn in enumerate(self._buttons):
            btn.setStyleSheet(_btn_style(i == index))
        self._style_power_badge(selected=index == _NAV_KEYS.index(POWER))

    def trigger(self, index: int) -> None:
        if 0 <= index < len(_NAV_KEYS):
            self._on_activate(_NAV_KEYS[index])

    def has_menu_at(self, index: int) -> bool:
        """Whether the button at *index* opens a dropdown on X — only Power does
        (A runs the current default; X opens the chooser), so the navigator
        advertises "Options" there."""
        return self.action_key_at(index) == POWER

    def action_key_at(self, index: int) -> str | None:
        return _NAV_KEYS[index] if 0 <= index < len(_NAV_KEYS) else None

    def button_at(self, index: int):
        return self._buttons[index] if 0 <= index < len(self._buttons) else None

    # ── Menu zone (HomeMenuContent drives the expanded menu's top row) ────────

    def nav_items(self) -> list[MenuItem]:
        """The header buttons as menu items, so the expanded menu can navigate into
        the header as its zone 0 and act on a selection (Network / Notifications
        dispatch; Power opens the chooser)."""
        return [self._nav_item(key) for key in _NAV_KEYS]

    @staticmethod
    def _nav_item(key: str) -> MenuItem:
        # POWER is abstract (no entry in ACTIONS); the others carry their action's
        # localized label + icon.
        if key == POWER:
            return MenuItem(translate("Kasual Desktop", "Power"), POWER, _POWER_GLYPH)
        return MenuItem(translate("Kasual Desktop", ACTIONS[key].label), key, ACTIONS[key].icon)

    # ── Clock ─────────────────────────────────────────────────────────────────

    def _tick_clock(self) -> None:
        now = datetime.now()
        loc = QLocale.system()
        day = loc.dayName(now.weekday() + 1, QLocale.FormatType.LongFormat)
        month = loc.monthName(now.month, QLocale.FormatType.ShortFormat)
        self._date_lbl.setText(f"{day}  {now.day:02d} {month}. {now.year}")
        self._clock_lbl.setText(now.strftime("%H:%M:%S"))
