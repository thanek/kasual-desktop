"""HomeHeader — the navigable status header that replaces the top bar (§8 / Faza 5).

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

from PyQt6.QtCore import Qt, QSize, QTimer, QLocale
from datetime import datetime
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from domain.menu.item import MenuItem
from domain.menu.entry import POWER
from domain.system.actions import ACTIONS, NETWORK, NOTIFICATIONS
from domain.shared.i18n import translate

HEADER_H = 80    # matches the old top bar / hint bar height
_BTN     = 56
# Far right is Power: a chooser for the default sleep/restart/shutdown action
# (§8). It carries the abstract POWER key; the host opens the dropdown.
_NAV_KEYS  = (NETWORK, NOTIFICATIONS, POWER)
_POWER_GLYPH = "fa5s.power-off"

# The focused-button look — a light translucent fill behind a thin accent border.
# The whole header wears it too (its resting background), so bar and buttons read
# as one family.
_FOCUS_FILL   = "rgba(136, 192, 208, 60)"
_FOCUS_BORDER = "#88c0d0"


def _btn_style(selected: bool) -> str:
    if selected:
        return (f"background-color: {_FOCUS_FILL}; border: 2px solid {_FOCUS_BORDER};"
                f" border-radius: {_BTN // 2}px;")
    return f"background: transparent; border: 2px solid transparent; border-radius: {_BTN // 2}px;"


class HomeHeader(QWidget):
    """Clock + date + focusable Network / Notifications buttons (a TopBarView)."""

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
        self.setStyleSheet(
            "#homeheader {"
            f"  background-color: {_FOCUS_FILL};"
            f"  border: 2px solid {_FOCUS_BORDER};"
            "  border-radius: 40px;"
            "}"
        )
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

        # Notification count badge in the bell button's corner (hidden at 0).
        self._notif_badge = QLabel(self._notif_btn)
        self._notif_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notif_badge.setStyleSheet(
            "background-color: #bf616a; color: white; font-size: 10px;"
            " font-weight: bold; border: none; border-radius: 9px;")
        self._notif_badge.setFixedSize(18, 18)
        self._notif_badge.move(_BTN - 20, 2)
        self._notif_badge.hide()

        self._buttons = [self._net_btn, self._notif_btn, self._power_btn]

        self._tick_clock()
        timer = QTimer(self)
        timer.timeout.connect(self._tick_clock)
        timer.start(1000)

    def _make_button(self, glyph: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(_BTN, _BTN)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setIcon(qta.icon(glyph, color="white"))
        btn.setIconSize(QSize(24, 24))
        btn.setStyleSheet(_btn_style(False))
        return btn

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

    def set_selected(self, index: int | None) -> None:
        self._selected = index
        for i, btn in enumerate(self._buttons):
            btn.setStyleSheet(_btn_style(i == index))

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
