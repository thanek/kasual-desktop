"""The sectioned Home menu content (§7.10) — zones, navigation, and rendering.

A plain ``QWidget`` holding the two-zone (Quick adjust ⇄ Actions ⇄ HUD) menu the
gamepad drives. It owns *no* surface and pushes *no* handler: the host decides
how it appears and feeds it pad events. Two hosts embed it:

  * :class:`~infrastructure.common.qt.overlays.home_overlay.HomeOverlay` — the
    map-on-demand overlay shown on BTN_MODE over a running app or a minimized
    Kasual (contexts 2/3);
  * :class:`~infrastructure.common.qt.desktop.home_surface.HomeSurface` — the
    persistent collapse/expand surface in the Home view (context 1, §8 / Faza 5).

The widget composes its own sections (via :func:`domain.menu.home.compose_home_sections`)
from the volume/brightness controls and the power menu handed in; everything the
host must react to is funneled through the callbacks passed to :meth:`configure`
(``on_action`` / ``on_cancel`` / ``set_hints`` / ``request_hide``). Quick-adjust
sliders and the Power split-button are handled internally.
"""

import logging
from collections.abc import Callable

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize, QPoint
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QSlider,
)

from domain.input.vocabulary import Event
from domain.catalog.target import Target
from domain.menu.entry import POWER, RETURN_TO_APP, RETURN_TO_DESKTOP
from domain.menu.home import (
    HomeSection, SectionKind, compose_home_sections, power_dropdown_items,
)
from domain.menu.item import MenuItem
from domain.navigation import hints as nav_hints
from domain.shared.feedback import Cue, Feedback
from domain.system.actions import HIDE_DESKTOP, VOLUME
from domain.system.brightness import BrightnessControl
from domain.system.hud import HudControl
from domain.system.power_menu import PowerMenu
from domain.system.volume import VolumeControl
from infrastructure.common.qt.ui import styles

logger = logging.getLogger(__name__)

# The Actions section is a single-column vertical list navigated up/down (the
# Quick-adjust sliders keep their own left/right handling).
_ACTIONS_COLUMNS = 1
CARD_WIDTH  = 832
# The list and the sliders share this width, centred within the wider card so the
# header can still span it — the menu reads as one centred column.
_LIST_WIDTH = round(CARD_WIDTH * 2 / 3)
_QUICK_WIDTH = _LIST_WIDTH

_SLIDER_QSS = """
    QSlider::groove:horizontal { height: 8px; background: #4c566a; border-radius: 4px; }
    QSlider::sub-page:horizontal { background: #88c0d0; border-radius: 4px; }
    QSlider::handle:horizontal {
        width: 22px; height: 22px; margin: -7px 0; background: white; border-radius: 11px;
    }
"""


def _quick_row_style(selected: bool) -> str:
    if selected:
        return "background-color: rgba(136,192,208,40); border-radius: 12px;"
    return "background: transparent; border-radius: 12px;"


class _Zone:
    """A rendered section: its kind, the source items, the row/card widgets, the
    grid width, and the current selection within it."""

    def __init__(self, kind: SectionKind, items: list[MenuItem],
                 widgets: list[QWidget], columns: int = 1) -> None:
        self.kind = kind
        self.items = items
        self.widgets = widgets
        self.columns = columns
        self.index = 0


class HomeMenuContent(QWidget):
    """The sectioned Home menu (§7.10) as an embeddable, surface-less widget.

    The Power card is a split-button: ``A`` runs the current default, ``X`` expands
    the Sleep / Restart / Shut Down chooser (the same button that opens a tile's
    popover; picking one runs it and, once confirmed,
    makes it the new default — see :class:`domain.system.power_menu.PowerMenu`). The
    LT/RT triggers adjust global volume regardless of zone or focus.
    """

    def __init__(
        self,
        feedback: Feedback,
        volume: VolumeControl,
        brightness: BrightnessControl,
        power: PowerMenu,
    ) -> None:
        super().__init__()
        self._feedback = feedback
        self._volume = volume
        self._brightness = brightness
        self._power = power

        self._zones: list[_Zone] = []
        self._active = 0
        self._quick_state: list[dict] = []   # aligned with the quick zone's items
        self._power_card: QWidget | None = None  # the Power split-button (X opens its dropdown)
        self._dropdown: dict | None = None   # the open Power dropdown, while expanded
        self._on_action: Callable[[MenuItem], None] | None = None
        self._on_cancel: Callable[[], None] | None = None
        self._set_hints: Callable | None = None
        # Optional status header rendered above the content (§8). When present it
        # is navigated as zone 0 — "up" from the top section flows into it — and a
        # selection (Network / Notifications) dispatches through ``on_action``. Its
        # selection highlight is painted on the header itself, not on a zone widget.
        self._header = None
        # Funnel back to the host so it can tear down/collapse its own surface when
        # an item is activated or B is pressed; defaults to a no-op until configure.
        self._request_hide: Callable[[], None] = lambda: None
        # Opens the Power chooser when the header carries Power (§8); the inline
        # split-button dropdown is used instead when there is no header.
        self._on_power_chooser: Callable[[], None] | None = None

        self.setStyleSheet("background: transparent;")
        self._zones_layout = QVBoxLayout(self)
        self._zones_layout.setContentsMargins(0, 0, 0, 0)
        self._zones_layout.setSpacing(14)

    # ── Host API ───────────────────────────────────────────────────────────────

    def configure(
        self,
        foreground: Target | None,
        foreground_is_game: bool,
        hud: HudControl,
        *,
        on_action: Callable[[MenuItem], None],
        on_cancel: Callable[[], None] | None,
        set_hints: Callable | None,
        request_hide: Callable[[], None],
        desktop_minimized: bool = False,
        header=None,
        on_power_chooser: Callable[[], None] | None = None,
    ) -> None:
        """Compose the sections for the current context, build them, and pre-focus
        the card most likely wanted. The host then shows itself and starts feeding
        pad events to :meth:`handle_pad`. ``header`` (a ``HomeHeader``) is added as
        navigable zone 0 when given (§8); ``on_power_chooser`` opens the default-
        power chooser for the header's Power button."""
        self._on_action = on_action
        self._on_cancel = on_cancel
        self._set_hints = set_hints
        self._request_hide = request_hide
        self._header = header
        self._on_power_chooser = on_power_chooser
        sections = compose_home_sections(
            foreground, hud,
            brightness_controllable=self._brightness.is_controllable(),
            power_default=self._power.default_key(),
            foreground_is_game=foreground_is_game,
            # Network / Notifications live on the header when one is present, so
            # don't repeat them in the Actions grid.
            include_status_actions=header is None,
        )
        self._build(sections.sections)
        self._focus_default(foreground, desktop_minimized)
        self._render()
        self._sync_hints()

    # ── Building ─────────────────────────────────────────────────────────────

    def _build(self, sections: list[HomeSection]) -> None:
        while self._zones_layout.count():
            item = self._zones_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._zones = []
        self._quick_state = []
        self._close_dropdown()
        self._power_card = None

        # The header (when present) is zone 0 — a navigable row whose buttons live
        # on the external header widget, so it contributes no widgets to the layout
        # and is painted via header.set_selected (see _render).
        if self._header is not None:
            items = self._header.nav_items()
            self._zones.append(_Zone(SectionKind.HEADER, items, widgets=[],
                                     columns=len(items)))

        for i, section in enumerate(sections):
            if i:
                self._zones_layout.addWidget(self._separator())
            if section.kind == SectionKind.QUICK:
                self._zones.append(self._build_quick(section))
            else:
                self._zones.append(self._build_cards(section))

    def _build_quick(self, section: HomeSection) -> _Zone:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        col = QVBoxLayout(container)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(18)
        rows: list[QWidget] = []
        for item in section.items:
            control = self._control_for(item.action)
            value = control.get()
            row = QFrame()
            row.setStyleSheet(_quick_row_style(False))
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 8, 12, 8)
            rl.setSpacing(12)
            icon = QLabel()
            icon.setPixmap(qta.icon(item.icon, color="white").pixmap(24, 24))
            icon.setStyleSheet("background: transparent;")
            rl.addWidget(icon)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(value.value)
            slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            slider.setStyleSheet(_SLIDER_QSS)
            rl.addWidget(slider, 1)
            vlabel = QLabel(f"{value.value}%")
            vlabel.setFixedWidth(52)
            vlabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            vlabel.setStyleSheet("color: white; font-size: 18px; background: transparent;")
            rl.addWidget(vlabel)
            col.addWidget(row)
            rows.append(row)
            self._quick_state.append(
                {"control": control, "value": value, "slider": slider, "vlabel": vlabel})
        # Fix the width (not just a max) so the sliders actually span two-thirds —
        # under AlignHCenter a mere maximum collapses to the slider's tiny size
        # hint. The wider card is for the Actions grid, not for edge-to-edge sliders.
        container.setFixedWidth(_QUICK_WIDTH)
        self._zones_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        return _Zone(SectionKind.QUICK, section.items, rows)

    def _build_cards(self, section: HomeSection) -> _Zone:
        columns = _ACTIONS_COLUMNS if section.kind == SectionKind.ACTIONS else 1
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        cards: list[QWidget] = []
        for idx, item in enumerate(section.items):
            # The Power card is a split-button: a trailing chevron (and the hint
            # bar's "Options") advertise the dropdown so it stays discoverable.
            is_power = item.action == POWER
            label = "  " + item.label + ("   ▾" if is_power else "")
            card = QPushButton(label)
            card.setMinimumHeight(58)
            card.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if item.icon:
                card.setIcon(qta.icon(item.icon, color="white"))
                card.setIconSize(QSize(22, 22))
            card.setStyleSheet(styles.home_menu_item_normal())
            grid.addWidget(card, idx // columns, idx % columns)
            cards.append(card)
            if is_power:
                self._power_card = card
        # Single-column list, centred at the shared width so it lines up under the
        # Quick-adjust sliders (matching AlignHCenter there).
        container.setFixedWidth(_LIST_WIDTH)
        self._zones_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        return _Zone(section.kind, section.items, cards, columns)

    def _separator(self) -> QWidget:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #3b4252;")
        return line

    def _control_for(self, action: str):
        return self._volume if action == VOLUME else self._brightness

    def _focus_default(self, foreground: Target | None, desktop_minimized: bool) -> None:
        """Pre-focus the card most likely wanted on open: "Return to {app}" over a
        running app, "Minimize" when Kasual is minimized, else "Return to Home
        screen". Lands in the Actions zone; falls back to the first zone/item."""
        if foreground is not None:
            key = RETURN_TO_APP
        elif desktop_minimized:
            key = HIDE_DESKTOP
        else:
            key = RETURN_TO_DESKTOP
        for zi, zone in enumerate(self._zones):
            if zone.kind in (SectionKind.QUICK, SectionKind.HEADER):
                continue
            for ci, item in enumerate(zone.items):
                if item.action == key:
                    self._active = zi
                    zone.index = ci
                    return
        # Fall back to the first non-chrome zone (never open focused on the header
        # or a slider) — the Actions zone in every composed context.
        self._active = next(
            (zi for zi, z in enumerate(self._zones)
             if z.kind not in (SectionKind.QUICK, SectionKind.HEADER)),
            0,
        )

    # ── Navigation ───────────────────────────────────────────────────────────

    def handle_pad(self, event: str) -> None:
        # Triggers (LT/RT) adjust volume regardless of zone or focus — an
        # always-at-hand shortcut, so they take priority even over the dropdown.
        if event == Event.VOLUME_DOWN:
            self._nudge_volume(-1)
            return
        if event == Event.VOLUME_UP:
            self._nudge_volume(+1)
            return
        if self._dropdown is not None:
            self._dropdown_event(event)
            return
        if event == Event.SECTION_PREV:
            self._switch_zone(-1)
            return
        if event == Event.SECTION_NEXT:
            self._switch_zone(+1)
            return
        if event == Event.CANCEL:
            self._cancel()
            return
        zone = self._zones[self._active] if self._zones else None
        if event == Event.CLOSE:
            # X opens the Power chooser when focused on Power — the same button that
            # opens a tile's popover — otherwise it dismisses the menu like B.
            if (zone is not None and zone.items
                    and zone.items[zone.index].action == POWER):
                self._open_dropdown(zone.items[zone.index])
            else:
                self._cancel()
            return
        if zone is None:
            return
        if zone.kind == SectionKind.QUICK:
            self._quick_event(zone, event)
        else:
            self._cards_event(zone, event)

    def _switch_zone(self, delta: int) -> None:
        new = max(0, min(self._active + delta, len(self._zones) - 1))
        if new != self._active:
            self._active = new
            self._render()
            self._sync_hints()
            self._feedback.play(Cue.CURSOR)

    def _cross_to_zone(self, delta: int, *, landing: str) -> None:
        """D-pad up/down spilling past a section's edge moves into the adjacent
        section, landing on its first (when entering from above) or last (from
        below) widget — so the whole overlay reads as one vertical flow. Clamps
        silently at the first/last section."""
        new = self._active + delta
        if not 0 <= new < len(self._zones):
            return
        self._active = new
        zone = self._zones[new]
        zone.index = 0 if landing == "first" else len(zone.items) - 1
        self._render()
        self._sync_hints()
        self._feedback.play(Cue.CURSOR)

    def _quick_event(self, zone: _Zone, event: str) -> None:
        if event == Event.UP:
            if zone.index == 0:
                self._cross_to_zone(-1, landing="last")
            else:
                self._move_within(zone, -1)
        elif event == Event.DOWN:
            if zone.index == len(zone.items) - 1:
                self._cross_to_zone(+1, landing="first")
            else:
                self._move_within(zone, +1)
        elif event == Event.LEFT:
            self._adjust(zone.index, -1)
        elif event == Event.RIGHT:
            self._adjust(zone.index, +1)

    def _cards_event(self, zone: _Zone, event: str) -> None:
        n = len(zone.items)
        cols = zone.columns
        i = zone.index
        target = i
        last_row_start = ((n - 1) // cols) * cols
        if event == Event.LEFT and i % cols > 0:
            target = i - 1
        elif event == Event.RIGHT and i % cols < cols - 1 and i + 1 < n:
            target = i + 1
        elif event == Event.UP:
            if i - cols >= 0:
                target = i - cols
            else:
                self._cross_to_zone(-1, landing="last")   # top row → previous section
                return
        elif event == Event.DOWN:
            if i + cols < n:
                target = i + cols
            elif i < last_row_start:
                target = n - 1            # partial last row, not under this column → its last card
            else:
                self._cross_to_zone(+1, landing="first")  # bottom row → next section
                return
        elif event == Event.SELECT:
            self._activate(zone.items[zone.index])
            return
        if target != i:
            zone.index = target
            self._render()
            self._feedback.play(Cue.CURSOR)

    def _move_within(self, zone: _Zone, delta: int) -> None:
        target = max(0, min(zone.index + delta, len(zone.items) - 1))
        if target != zone.index:
            zone.index = target
            self._render()
            self._feedback.play(Cue.CURSOR)

    def _adjust(self, slider_index: int, sign: int) -> None:
        self._adjust_state(self._quick_state[slider_index], sign)

    def _adjust_state(self, state: dict, sign: int) -> None:
        value = state["value"]
        new = value.adjusted(sign * type(value).STEP)
        if new.value == value.value:
            return
        state["value"] = new
        state["control"].set(new)
        state["slider"].setValue(new.value)
        state["vlabel"].setText(f"{new.value}%")
        self._feedback.play(Cue.CURSOR)

    def _nudge_volume(self, sign: int) -> None:
        """Adjust global volume from the LT/RT triggers, reflecting it in the
        Quick-adjust slider when one is on screen (it always is, in practice)."""
        state = self._volume_state()
        if state is not None:
            self._adjust_state(state, sign)
            return
        value = self._volume.get()
        new = value.adjusted(sign * type(value).STEP)
        if new.value != value.value:
            self._volume.set(new)
            self._feedback.play(Cue.CURSOR)

    def _volume_state(self) -> dict | None:
        for state in self._quick_state:
            if state["control"] is self._volume:
                return state
        return None

    def _activate(self, item: MenuItem) -> None:
        if item.action == POWER:
            # A always runs the current default (header Power or in-grid split-
            # button); X opens the chooser to change it (§8). Hide first — the
            # power action (and its confirm) supersedes the menu.
            self._feedback.play(Cue.SELECT)
            self._request_hide()
            self._power.activate_default()
            return
        self._feedback.play(Cue.SELECT)
        self._request_hide()
        if self._on_action is not None:
            self._on_action(item)

    def _cancel(self) -> None:
        self._feedback.play(Cue.POPUP_CLOSE)
        self._request_hide()
        if self._on_cancel is not None:
            self._on_cancel()

    # ── Power dropdown (X on the Power card) ─────────────────────────────────

    def _open_dropdown(self, item: MenuItem) -> None:
        """X on the Power card expands the Sleep/Restart/Shut Down chooser (the same
        button that opens a tile's popover); a no-op on any other card."""
        if item.action != POWER:
            return
        # When the header carries Power, route to the header chooser (there is no
        # in-grid power card to anchor an inline dropdown to).
        if self._header is not None and self._on_power_chooser is not None:
            self._on_power_chooser()
            return
        if self._power_card is None:
            return
        items = power_dropdown_items()
        default = self._power.default_key()
        # Open with the cursor on the current default (highlighted + focused) —
        # no separate marker needed to show which one is active (§8).
        index = next((i for i, it in enumerate(items) if it.action == default), 0)

        frame = QFrame(self)
        frame.setStyleSheet(
            "background-color: #2e3440; border: 1px solid #4c566a; border-radius: 12px;"
        )
        col = QVBoxLayout(frame)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(4)
        buttons: list[QPushButton] = []
        for it in items:
            button = QPushButton(it.label)
            button.setMinimumHeight(46)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if it.icon:
                button.setIcon(qta.icon(it.icon, color="white"))
                button.setIconSize(QSize(20, 20))
            col.addWidget(button)
            buttons.append(button)

        self._dropdown = {"items": items, "index": index, "buttons": buttons, "frame": frame}
        frame.adjustSize()
        anchor = self._power_card.mapTo(self, QPoint(0, self._power_card.height() + 6))
        frame.move(anchor)
        frame.show()
        frame.raise_()
        self._render_dropdown()
        self._feedback.play(Cue.POPUP_OPEN)

    def _dropdown_event(self, event: str) -> None:
        dd = self._dropdown
        if dd is None:
            return
        if event == Event.UP:
            self._move_dropdown(-1)
        elif event == Event.DOWN:
            self._move_dropdown(+1)
        elif event == Event.SELECT:
            self._choose_power(dd["items"][dd["index"]])
        elif event in (Event.CANCEL, Event.CLOSE, Event.ACTIONS):
            self._close_dropdown()
            self._feedback.play(Cue.POPUP_CLOSE)

    def _move_dropdown(self, delta: int) -> None:
        dd = self._dropdown
        target = max(0, min(dd["index"] + delta, len(dd["items"]) - 1))
        if target != dd["index"]:
            dd["index"] = target
            self._render_dropdown()
            self._feedback.play(Cue.CURSOR)

    def _render_dropdown(self) -> None:
        dd = self._dropdown
        for i, button in enumerate(dd["buttons"]):
            button.setStyleSheet(
                styles.home_menu_item_selected() if i == dd["index"]
                else styles.home_menu_item_normal()
            )

    def _choose_power(self, item: MenuItem) -> None:
        """A picked action runs *and* (once confirmed) becomes the new default —
        the persist-only-on-confirm rule lives in PowerMenu.select. Hide first so
        the confirm dialog owns the pad (the menu merely floated over it)."""
        self._feedback.play(Cue.SELECT)
        self._close_dropdown()
        self._request_hide()
        self._power.select(item.action)

    def _close_dropdown(self) -> None:
        if self._dropdown is not None:
            self._dropdown["frame"].deleteLater()
            self._dropdown = None

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render(self) -> None:
        for zi, zone in enumerate(self._zones):
            active = zi == self._active
            if zone.kind == SectionKind.HEADER:
                # The header paints its own selection; None clears it when the zone
                # isn't active.
                self._header.set_selected(zone.index if active else None)
                continue
            for wi, widget in enumerate(zone.widgets):
                selected = active and wi == zone.index
                if zone.kind == SectionKind.QUICK:
                    widget.setStyleSheet(_quick_row_style(selected))
                else:
                    widget.setStyleSheet(
                        styles.home_menu_item_selected() if selected
                        else styles.home_menu_item_normal()
                    )

    def _sync_hints(self) -> None:
        if self._set_hints is None or not self._zones:
            return
        kind = self._zones[self._active].kind
        if kind == SectionKind.QUICK:
            hints = nav_hints.OVERLAY_QUICK
        elif kind == SectionKind.HEADER:
            hints = nav_hints.OVERLAY_HEADER   # the header row navigates left/right
        else:
            hints = nav_hints.OVERLAY_ACTIONS
        self._set_hints(hints)
