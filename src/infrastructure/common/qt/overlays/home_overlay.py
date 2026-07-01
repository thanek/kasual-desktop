"""Home Overlay — the map-on-demand, sectioned BTN_MODE menu (§7.10).

A standalone overlay-layer surface shown on BTN_MODE over a running app or a
minimized Kasual (contexts 2/3 in `UX.md` §8). It is a thin chrome wrapper —
translucent backdrop + centred card with a title — around the shared
:class:`~infrastructure.common.qt.overlays.home_menu_content.HomeMenuContent`,
which owns the zones, navigation, Quick-adjust sliders and the Power split-button.

The controller hands it only the foreground context plus the dispatch/cancel/hint
callbacks; the content reports activation back through ``on_action``. The Home
view's persistent collapse/expand surface (context 1) embeds the *same* content
widget — see :class:`infrastructure.common.qt.desktop.home_surface.HomeSurface`.
"""

import logging
from collections.abc import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy

from domain.catalog.target import Target
from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.item import MenuItem
from domain.shared.event_emitter import Unsubscribe
from domain.shared.feedback import Cue, Feedback
from domain.shell.overlay import SectionedHomeOverlay
from domain.system.brightness import BrightnessControl
from domain.system.hud import HudControl
from domain.system.power_menu import PowerMenu
from domain.system.volume import VolumeControl
from infrastructure.common.qt._meta import ProtocolQtMeta
from infrastructure.common.qt.ui import styles
from infrastructure.common.qt.ui.layer_shell import Layer, Anchor, Keyboard
from infrastructure.common.qt.ui.top_surface import promote_overlay_surface
from infrastructure.common.qt.overlays.home_menu_content import CARD_WIDTH, HomeMenuContent

logger = logging.getLogger(__name__)


class HomeOverlay(QWidget, SectionedHomeOverlay, metaclass=ProtocolQtMeta):
    """The sectioned Home Overlay (a standalone overlay-layer surface)."""

    closed = pyqtSignal()

    def __init__(
        self,
        gamepad: PadControl,
        feedback: Feedback,
        volume: VolumeControl,
        brightness: BrightnessControl,
        power: PowerMenu,
    ) -> None:
        super().__init__()
        self._gamepad = gamepad
        self._feedback = feedback
        # Kept as attributes so the offscreen tests can read the controls/power
        # menu straight off the overlay (they are the very objects handed to the
        # embedded content).
        self._volume = volume
        self._brightness = brightness
        self._power = power

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        # Overlay layer over everything, keyboard=NONE (gamepad-driven; grabbing
        # focus would uncover KWin panels).
        promote_overlay_surface(
            self, layer=Layer.OVERLAY, anchors=Anchor.ALL,
            exclusive_zone=-1, keyboard=Keyboard.NONE,
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._card = styles.make_card(CARD_WIDTH)
        self._card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(14)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(self.tr("Kasual Desktop"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; color: #88c0d0; font-weight: bold; background: transparent;"
        )
        card_layout.addWidget(title)

        self._content = HomeMenuContent(feedback, volume, brightness, power)
        card_layout.addWidget(self._content)
        outer.addWidget(self._card)

    # ── SectionedHomeOverlay port ────────────────────────────────────────────

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
        if self.isVisible():
            return
        self._content.configure(
            foreground, foreground_is_game, hud,
            on_action=on_action, on_cancel=on_cancel, set_hints=set_hints,
            request_hide=self.hide_overlay, desktop_minimized=desktop_minimized,
        )
        self._gamepad.push_handler(self._content.handle_pad)
        self._feedback.play(Cue.POPUP_OPEN)
        self.showFullScreen()
        self.raise_()

    def hide_overlay(self) -> None:
        if not self.isVisible():
            return
        self._content._close_dropdown()
        self._gamepad.pop_handler(self._content.handle_pad)
        self.hide()
        self.closed.emit()

    def is_showing(self) -> bool:
        return self.isVisible()

    def on_closed(self, handler: Callable[[], None]) -> Unsubscribe:
        self.closed.connect(handler)
        return Unsubscribe(lambda: self.closed.disconnect(handler))

    def dispose(self) -> None:
        self.deleteLater()

    # ── Embedded-content seam (also the offscreen tests' handle) ──────────────
    # The navigation/zone logic lives in HomeMenuContent; these forward the few
    # members the overlay's own input edges (and the tests) reach for, so the
    # overlay needn't re-expose the whole menu surface.

    @property
    def _zones(self):
        return self._content._zones

    @property
    def _active(self) -> int:
        return self._content._active

    @_active.setter
    def _active(self, value: int) -> None:
        self._content._active = value

    @property
    def _dropdown(self):
        return self._content._dropdown

    def _render(self) -> None:
        self._content._render()

    def _handle_pad(self, event: str) -> None:
        self._content.handle_pad(event)

    def _volume_state(self):
        return self._content._volume_state()

    # ── Keyboard (dev/testing; layer-shell surface has no Wayland focus) ──────

    _KEY_MAP = {
        Qt.Key.Key_Up:           Event.UP,
        Qt.Key.Key_Down:         Event.DOWN,
        Qt.Key.Key_Left:         Event.LEFT,
        Qt.Key.Key_Right:        Event.RIGHT,
        Qt.Key.Key_Return:       Event.SELECT,
        Qt.Key.Key_Enter:        Event.SELECT,
        Qt.Key.Key_Escape:       Event.CANCEL,
        Qt.Key.Key_BracketLeft:  Event.SECTION_PREV,
        Qt.Key.Key_BracketRight: Event.SECTION_NEXT,
        Qt.Key.Key_Q:            Event.SECTION_PREV,
        Qt.Key.Key_E:            Event.SECTION_NEXT,
        Qt.Key.Key_Minus:        Event.VOLUME_DOWN,
        Qt.Key.Key_Equal:        Event.VOLUME_UP,
        Qt.Key.Key_Tab:          Event.ACTIONS,
    }

    def keyPressEvent(self, event: QKeyEvent) -> None:
        mapped = self._KEY_MAP.get(event.key())
        if mapped is not None:
            self._content.handle_pad(mapped)

    def mousePressEvent(self, event) -> None:
        if not self._card.geometry().contains(event.pos()):
            self._content._cancel()
        else:
            super().mousePressEvent(event)


class HomeOverlayFactory:
    """Builds Home Overlay surfaces bound to the gamepad, feedback and the
    volume/brightness controls + power menu (a SectionedOverlayFactory)."""

    def __init__(
        self,
        gamepad: PadControl,
        feedback: Feedback,
        volume: VolumeControl,
        brightness: BrightnessControl,
        power: PowerMenu,
    ) -> None:
        self._gamepad = gamepad
        self._feedback = feedback
        self._volume = volume
        self._brightness = brightness
        self._power = power

    def create_home_overlay(self) -> SectionedHomeOverlay:
        return HomeOverlay(
            self._gamepad, self._feedback, self._volume, self._brightness, self._power)
