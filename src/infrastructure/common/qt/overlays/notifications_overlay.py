"""Full-screen overlay listing the most recent system notifications.

Read-only (MVP): renders `NotificationCenter.recent(...)` as a scrollable list,
navigable by gamepad/keyboard, dismissed with B/Esc (or A). A `BaseOverlay`
managing its own layer-shell surface and pad lifetime, it reuses the domain
`MenuCursor` for selection, exactly like the Home Overlay, so navigation semantics
live in the domain, not here.
"""

import os
from datetime import datetime

import qtawesome as qta
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QIcon, QKeyEvent, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QSizePolicy,
)

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.cursor import MenuCursor
from domain.notifications.center import NotificationCenter
from domain.notifications.view import relative_age
from domain.shared.feedback import Cue, Feedback
from domain.shared.text import truncate
from domain.shared.i18n import translate
from infrastructure.common.qt.ui import styles
from .base_overlay import BaseOverlay

_MAX_ROWS        = 12     # how many recent notifications to show
_LIST_MAX_HEIGHT = 560    # px; the list scrolls only past this height
_ICON_SIZE       = 40     # px; per-row app-icon side


def _icon_name_candidates(icon_hint: str | None, app_name: str) -> list[str]:
    """Ordered, de-duplicated names to try when resolving a notification's icon.

    Pure (no Qt) so it is unit-testable: the freedesktop ``app_icon`` hint first,
    then the application name (as-is and lower-cased) as a theme-icon name."""
    out: list[str] = []
    seen: set[str] = set()

    def add(name: str | None) -> None:
        if not name:
            return
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)

    add(icon_hint)
    add(app_name)
    add(app_name.lower() if app_name else None)
    return out


def _load_icon(name: str) -> QIcon | None:
    """A QIcon for a theme name or a file path/URI, or None if it resolves to
    nothing. Mirrors WindowIconResolver._icon_from_name, plus ``file://`` URIs."""
    if name.startswith("file://"):
        name = QUrl(name).toLocalFile() or name[len("file://"):]
    if os.path.isabs(name):
        icon = QIcon(name)
        return icon if not icon.isNull() else None
    if QIcon.hasThemeIcon(name):
        return QIcon.fromTheme(name)
    return None


def _resolve_icon_pixmap(icon_hint: str | None, app_name: str, size: int) -> QPixmap:
    """A ``size``×``size`` app icon for a notification — the sender's hint, then
    the app name, then a neutral bell glyph so every row carries an icon."""
    for name in _icon_name_candidates(icon_hint, app_name):
        icon = _load_icon(name)
        if icon is not None and not icon.isNull():
            pixmap = icon.pixmap(size, size)
            if not pixmap.isNull():
                return pixmap
    return qta.icon("fa5s.bell", color="#9aa0aa").pixmap(size, size)

# Row background, scoped to #notifrow so the child labels (transparent) are
# untouched. Selection just swaps the frame's background + border.
_ROW_NORMAL = (
    "#notifrow { background-color: #2e3440; border-radius: 8px;"
    " border: 2px solid transparent; }"
)
# Unread (new since last viewed): lifted background + a left accent border, so
# new notifications stand out from already-seen ones even when not selected.
_ROW_UNREAD = (
    "#notifrow { background-color: #3b4252; border-radius: 8px;"
    " border: 2px solid transparent; border-left: 4px solid #88c0d0; }"
)
_ROW_SELECTED = (
    "#notifrow { background-color: #434c5e; border-radius: 8px;"
    " border: 2px solid #88c0d0; }"
)

_ACCENT = "#88c0d0"   # unread accent (border + dot)


class NotificationsOverlay(BaseOverlay):
    """Full-screen overlay with the recent-notifications list."""

    closed = pyqtSignal()

    def __init__(
        self,
        gamepad: PadControl,
        center: NotificationCenter,
        feedback: Feedback,
        parent: QWidget | None = None,
        dim: bool = True,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback, parent, dim=dim)
        self._items = center.recent(_MAX_ROWS)
        # The first `unread` rows are the new ones (newest-first ordering). Read
        # before the desktop clears the tally so the highlight survives the reset.
        self._unread = min(center.unread_count, len(self._items))
        self._rows: list[QFrame] = []

        # Vertical navigation lives in the domain; movement clamps at the ends
        # (wrap=False), A/B/Esc dismiss (read-only list — no per-item action).
        self._cursor = MenuCursor(
            count=lambda: len(self._rows),
            render=self._render_selection,
            on_activate=lambda _idx: self._close(),
            on_dismiss=self._close,
            feedback=feedback,
            wrap=False,
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = self.build_card(640)
        # Hug the content vertically (like the Home Overlay) so a short list does
        # not leave a tall empty card — the height tracks the number of rows.
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(18)

        # Title
        title_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa5s.bell", color="white").pixmap(28, 28))
        icon_lbl.setStyleSheet("background: transparent;")
        title = QLabel(translate("Kasual Desktop", "Recent notifications"))
        title.setStyleSheet("font-size: 24px; color: white; background: transparent;")
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        layout.addWidget(self._build_list())

        outer.addWidget(card)

        self._cursor.reset(0)
        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    # ── Building the list ────────────────────────────────────────────────────

    def _build_list(self) -> QWidget:
        if not self._items:
            empty = QLabel(translate("Kasual Desktop", "No notifications"))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                "font-size: 18px; color: #aaa; background: transparent; padding: 40px;"
            )
            return empty

        now = datetime.now()
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        col = QVBoxLayout(container)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        col.setAlignment(Qt.AlignmentFlag.AlignTop)

        for i, n in enumerate(self._items):
            row = self._make_row(n, now, i)
            col.addWidget(row)
            self._rows.append(row)

        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(styles.flat_scrollbar())
        # Size the viewport to the rows, capped: a few notifications give a short
        # card; a long list stops growing at _LIST_MAX_HEIGHT and scrolls.
        container.ensurePolished()
        content_h = container.sizeHint().height()
        scroll.setFixedHeight(min(content_h, _LIST_MAX_HEIGHT))
        self._scroll = scroll
        return scroll

    def _make_row(self, n, now: datetime, idx: int) -> QFrame:
        """One notification row: app + time (meta), summary (title) and body.

        Built from explicit labels rather than a single multi-line button so the
        summary/body always render (a QPushButton would only show the first
        line, collapsing every notify-send entry to its identical header)."""
        unread = self._is_unread(idx)
        row = QFrame()
        row.setObjectName("notifrow")
        row.setStyleSheet(_ROW_UNREAD if unread else _ROW_NORMAL)
        # Clicking a row selects it (mouse parity with the gamepad cursor).
        row.mousePressEvent = lambda _e, i=idx: self._cursor.hover(i)

        h = QHBoxLayout(row)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(_resolve_icon_pixmap(n.icon, n.app_name, _ICON_SIZE))
        icon_lbl.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        icon_lbl.setStyleSheet("background: transparent;")
        h.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)

        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        h.addLayout(v, 1)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(8)
        if unread:
            dot = QLabel("●")
            dot.setStyleSheet(f"font-size: 12px; color: {_ACCENT}; background: transparent;")
            meta_row.addWidget(dot)
        meta = QLabel(f"{n.app_name}   ·   {relative_age(n.timestamp, now)}")
        meta.setStyleSheet("font-size: 13px; color: #9aa0aa; background: transparent;")
        meta_row.addWidget(meta)
        meta_row.addStretch()
        v.addLayout(meta_row)

        title = QLabel(truncate(n.summary or n.app_name, 60))
        title.setStyleSheet(
            "font-size: 18px; color: white; font-weight: bold; background: transparent;"
        )
        v.addWidget(title)

        if n.body:
            body = QLabel(truncate(n.body, 80))
            body.setStyleSheet("font-size: 15px; color: #cfd3da; background: transparent;")
            v.addWidget(body)
        return row

    # ── Navigation (delegated to the domain cursor) ──────────────────────────

    def _handle_pad(self, event: str) -> None:
        self._cursor.handle_pad(event)

    def _is_unread(self, idx: int) -> bool:
        return idx < self._unread

    def _render_selection(self, index: int) -> None:
        for i, row in enumerate(self._rows):
            if i == index:
                row.setStyleSheet(_ROW_SELECTED)
            else:
                row.setStyleSheet(_ROW_UNREAD if self._is_unread(i) else _ROW_NORMAL)
        if 0 <= index < len(self._rows):
            self._scroll.ensureWidgetVisible(self._rows[index])

    _KEY_MAP = {
        Qt.Key.Key_Up:     Event.UP,
        Qt.Key.Key_Down:   Event.DOWN,
        Qt.Key.Key_Return: Event.SELECT,
        Qt.Key.Key_Enter:  Event.SELECT,
        Qt.Key.Key_Escape: Event.CANCEL,
    }

    def keyPressEvent(self, event: QKeyEvent) -> None:
        mapped = self._KEY_MAP.get(event.key())
        if mapped is not None:
            self._cursor.handle_pad(mapped)

    def _on_outside_click(self) -> None:
        self._close()

    # ── Closing ──────────────────────────────────────────────────────────────

    def _close(self) -> None:
        if self._dismiss(sound=Cue.POPUP_CLOSE):
            self.closed.emit()
