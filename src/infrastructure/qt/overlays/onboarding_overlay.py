"""First-run app picker — the Qt side of provisioning (a ``ProvisioningView``).

A full-screen layer-shell surface, same shape as the other overlays: a centred
card listing the starter candidates, each a toggle row, plus a final Confirm
action. Pure presentation — it renders the domain candidates, drives an
:class:`AppSelection` for the toggle state and a :class:`MenuCursor` for
navigation, and reports the chosen candidates through ``on_confirm``. i18n lives
here (``tr`` on the canonical English names the domain supplies).

Unlike the other overlays this one is **modal and confirm-only**: B / Escape /
clicking the backdrop do nothing — the only way out is the Confirm action (which
is allowed with zero apps selected). Because nothing is fullscreen on first run,
it opts into keyboard interactivity so it is fully navigable by keyboard
(arrows + Space to toggle) as well as gamepad and mouse.

The view takes a candidate list + callbacks, so it is reusable beyond first-run
(e.g. a future "Add apps" panel), not just for onboarding.
"""

import logging
from collections.abc import Callable
from typing import _ProtocolMeta  # type: ignore[attr-defined]

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QLabel, QSizePolicy,
    QScrollArea, QFrame, QApplication,
)

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.cursor import MenuCursor
from domain.provisioning.candidate import CandidateApp
from domain.provisioning.ports import ProvisioningView
from domain.provisioning.selection import AppSelection
from domain.shared.feedback import Cue, Feedback
from infrastructure.qt.ui import styles
from infrastructure.qt.ui.layer_shell import Keyboard
from infrastructure.qt.ui.toggle_switch import ToggleSwitch
from .base_overlay import BaseOverlay

logger = logging.getLogger(__name__)

# Row icon size — sits comfortably within the 62px-tall toggle rows.
_ROW_ICON_PX     = 36
# Gap from the toggle to the row's right edge. Wide enough to clear the 10px
# scrollbar (shown when the list is long) and still leave comfortable spacing.
_TOGGLE_MARGIN_R = 36


class _ToggleRow(QPushButton):
    """A picker row: a full-width clickable button with an on/off
    :class:`ToggleSwitch` anchored to its right edge. The button keeps the
    styling, hover and click; the switch only reflects the selection state."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.toggle = ToggleSwitch(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        x = self.width() - self.toggle.width() - _TOGGLE_MARGIN_R
        y = (self.height() - self.toggle.height()) // 2
        self.toggle.move(x, y)


class _Meta(type(BaseOverlay), _ProtocolMeta): pass


class OnboardingOverlay(BaseOverlay, ProvisioningView, metaclass=_Meta):
    """The first-run app picker. Created once via its factory, shown by
    :meth:`present`, which feeds it the candidates and result callback."""

    def __init__(self, gamepad: PadControl, feedback: Feedback) -> None:
        # Opt into keyboard input: onboarding runs with nothing fullscreen, so
        # grabbing focus is safe and lets the picker be driven by keyboard.
        super().__init__(gamepad, self._handle_pad, feedback,
                         keyboard=Keyboard.ON_DEMAND)
        self._candidates: list[CandidateApp] = []
        self._selection: AppSelection | None = None
        self._on_confirm: Callable[[list[CandidateApp]], None] | None = None
        self._rows:    list[_ToggleRow] = []
        self._confirm: QPushButton | None = None
        self._return_row: int = 0   # row to return to when Left leaves Confirm

        # Navigation spans the toggle rows plus the trailing Confirm action;
        # clamped (wrap=False) like the tile popover — a fixed-length form.
        # on_dismiss is a no-op: this overlay is confirm-only (see module docs).
        self._cursor = MenuCursor(
            count=lambda: len(self._rows) + 1,
            render=self._render,
            on_activate=self._activate,
            on_dismiss=lambda: None,
            feedback=feedback,
            wrap=False,
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = self.build_card(560)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(self.tr("Welcome — pick your apps"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 28px; color: #88c0d0; font-weight: bold;"
            " background: transparent; padding-bottom: 8px;"
        )
        layout.addWidget(title)

        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)

        # Scrollable so a long candidate list (e.g. a full Start Menu scan) stays
        # within the screen; for a short list the area shrinks to fit (see present()).
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._rows_container)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.viewport().setStyleSheet("background: transparent;")
        self._scroll.setStyleSheet(styles.flat_scrollbar())
        layout.addWidget(self._scroll)

        # Confirm lives OUTSIDE the scroll area, so it is always visible at the
        # bottom no matter how far the list is scrolled. Navigation-wise it is the
        # cursor's last index (reached by Down from the last row, or Right from any
        # row); see _handle_pad.
        self._confirm = QPushButton(self.tr("Confirm"))
        self._confirm.setMinimumHeight(62)
        self._confirm.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._confirm.clicked.connect(self._confirm_clicked)
        layout.addWidget(self._confirm)

        outer.addWidget(card)

    # ── ProvisioningView ─────────────────────────────────────────────────────

    def present(
        self,
        candidates: list[CandidateApp],
        on_confirm: Callable[[list[CandidateApp]], None],
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        # on_cancel is part of the reusable port but unused here — this overlay
        # is confirm-only, so there is no dismissal path to report.
        self._candidates = list(candidates)
        self._selection = AppSelection(self._candidates)
        self._on_confirm = on_confirm
        self._build_rows()
        self._fit_scroll_height()
        self._cursor.reset(0)
        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    def _fit_scroll_height(self) -> None:
        """Size the scroll area to its rows, capped to ~55% of screen height so a
        long list scrolls while a short one shrinks to fit (no empty space).
        Confirm sits below the scroll, so it is not counted here."""
        n = max(1, len(self._rows))
        content = n * 62 + (n - 1) * 8
        screen = QApplication.primaryScreen()
        cap = int(screen.availableGeometry().height() * 0.55) if screen else 560
        self._scroll.setFixedHeight(min(content, cap))

    # ── Building ─────────────────────────────────────────────────────────────

    def _build_rows(self) -> None:
        assert self._selection is not None
        self._rows.clear()
        for i, candidate in enumerate(self._candidates):
            btn = _ToggleRow()
            btn.setMinimumHeight(62)
            # Ignore the text's natural width so a long name never widens the row
            # past the card (it clips inside instead of overflowing the dialog).
            btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            icon = self._candidate_icon(candidate)
            if icon is not None:
                btn.setIcon(icon)
                btn.setIconSize(QSize(_ROW_ICON_PX, _ROW_ICON_PX))
            btn.toggle.set_on(self._selection.is_selected(i), animate=False)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _checked=False, idx=i: self._row_clicked(idx))
            self._bind_hover(btn, i)
            self._rows_layout.addWidget(btn)
            self._rows.append(btn)

        # Confirm is created once (outside the scroll, in __init__); re-bind its
        # hover index now that the row count — its cursor index — is known.
        self._bind_hover(self._confirm, len(self._candidates))

    @staticmethod
    def _candidate_icon(candidate: CandidateApp) -> QIcon | None:
        """The row icon for a candidate, mirroring the tile bar's resolution: the
        Font Awesome glyph or themed ``Icon`` when set, else — for apps whose
        command is a real file (e.g. a Windows ``.lnk``/exe) — the OS shell icon."""
        app = candidate.app
        if app.icon:
            return qta.icon(app.icon, color="white")
        if app.icon_theme:
            themed = QIcon.fromTheme(app.icon_theme)
            if not themed.isNull():
                return themed
        return _shell_icon(app.command)

    def _bind_hover(self, btn: QPushButton, index: int) -> None:
        """Move the cursor onto *index* when the pointer enters *btn* (with the
        cursor sound + repaint), so mouse hover highlights like keyboard/pad."""
        def _enter(event) -> None:
            QPushButton.enterEvent(btn, event)
            self._cursor.hover(index)
        btn.enterEvent = _enter

    # ── Navigation (delegated to the domain cursor) ──────────────────────────

    def _handle_pad(self, event: str) -> None:
        # Left/Right jump between the list and the always-visible Confirm button:
        # Right from any row → Confirm; Left from Confirm → the row last left.
        if event == Event.RIGHT and self._rows and self._cursor.index < len(self._rows):
            self._return_row = self._cursor.index
            self._cursor.hover(len(self._rows))
            return
        if event == Event.LEFT and self._cursor.index == len(self._rows) and self._rows:
            self._cursor.hover(min(self._return_row, len(self._rows) - 1))
            return
        self._cursor.handle_pad(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Up:
            self._handle_pad(Event.UP)
        elif key == Qt.Key.Key_Down:
            self._handle_pad(Event.DOWN)
        elif key == Qt.Key.Key_Left:
            self._handle_pad(Event.LEFT)
        elif key == Qt.Key.Key_Right:
            self._handle_pad(Event.RIGHT)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._cursor.handle_pad(Event.SELECT)
        elif key == Qt.Key.Key_Space:
            # Space toggles the highlighted row's checkbox; a no-op on Confirm.
            index = self._cursor.index
            if index < len(self._rows):
                self._toggle(index)

    def _row_clicked(self, index: int) -> None:
        """Pointer click on a row: move the cursor there, then toggle it."""
        self._cursor.hover(index)
        self._activate(index)

    def _confirm_clicked(self) -> None:
        self._activate(len(self._rows))   # the Confirm row is last

    # ── Actions ──────────────────────────────────────────────────────────────

    def _activate(self, index: int) -> None:
        if index < len(self._rows):
            self._toggle(index)
        else:
            self._confirm_selection()

    def _toggle(self, index: int) -> None:
        assert self._selection is not None
        self._selection.toggle(index)
        self._rows[index].toggle.set_on(self._selection.is_selected(index))
        self._feedback.play(Cue.SELECT)
        self._render(self._cursor.index)

    def _confirm_selection(self) -> None:
        assert self._selection is not None
        chosen = self._selection.chosen()
        if self._dismiss(sound=Cue.SELECT) and self._on_confirm is not None:
            self._on_confirm(chosen)

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render(self, index: int) -> None:
        for i, btn in enumerate(self._rows):
            btn.setText(f"  {self.tr(self._candidates[i].app.name)}")
            btn.setStyleSheet(
                styles.home_menu_item_selected() if i == index
                else styles.home_menu_item_normal()
            )
        if self._confirm is not None:
            on_confirm_row = index == len(self._rows)
            self._confirm.setStyleSheet(
                styles.dialog_focused() if on_confirm_row else styles.dialog_idle()
            )
        # Keep the focused row visible as the cursor moves. Confirm sits outside
        # the scroll area (always visible), so it needs no scrolling.
        if index < len(self._rows):
            self._scroll.ensureWidgetVisible(self._rows[index])


class OnboardingOverlayFactory:
    """Builds the onboarding overlay bound to the gamepad + feedback, so the
    composition root can create the view without knowing its wiring."""

    def __init__(self, gamepad: PadControl, feedback: Feedback) -> None:
        self._gamepad = gamepad
        self._feedback = feedback

    def create(self) -> OnboardingOverlay:
        return OnboardingOverlay(self._gamepad, self._feedback)


_icon_provider: 'QFileIconProvider | None' = None


def _shell_icon(path: str) -> QIcon | None:
    """The operating system's icon for *path* (a .lnk resolves to its target's
    icon), or None when *path* is not an existing file. Cross-platform via Qt;
    on Linux a shell-command 'path' simply isn't a file, so this is a no-op there."""
    if not path:
        return None
    from PyQt6.QtCore import QFileInfo
    from PyQt6.QtWidgets import QFileIconProvider
    info = QFileInfo(path)
    if not info.exists():
        return None
    global _icon_provider
    if _icon_provider is None:
        _icon_provider = QFileIconProvider()
    icon = _icon_provider.icon(info)
    return icon if not icon.isNull() else None
