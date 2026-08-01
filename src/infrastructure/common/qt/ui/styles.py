from domain.shared.text import truncate  # noqa: F401 - re-exported: callers use styles.truncate

COLOR_ACCENT    = "#88c0d0"
COLOR_ACCENT_HI = "#9fd6e2"   # accent lifted for the mouse-hover echo
COLOR_BG_DARK   = "#0b140e"
COLOR_TEXT      = "white"
COLOR_TOPBAR    = "rgba(15, 17, 25, 210)"
COLOR_RUNNING   = "#a3be8c"
COLOR_CARD_BG   = "#2e3440"
COLOR_CHROME_BG = "rgba(46, 52, 64, 204)"   # transparency test: 20%
COLOR_SURFACE_HI = "#3b4252"
COLOR_SEPARATOR = COLOR_SURFACE_HI
COLOR_BTN_BG    = "#434c5e"
COLOR_TRACK     = "#4c566a"                 # slider/scrollbar track; also the button hover fill
COLOR_BTN_HI    = "#5b6884"
CARD_RADIUS_PX = 40
PILL_RADIUS    = 40
_TOPBAR_RADIUS = 30
_DIALOG_RADIUS = 25
# Kept ≤ half the menu row's min-height (58px) — Qt QSS squares corners past that.
_MENU_RADIUS   = 24


def apply_card_shadow(
    widget,
    *,
    offset_x: int = 0,
    offset_y: int = 8,
    blur: int = 40,
    alpha: int = 200,
    color: str | None = None,
) -> None:
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QGraphicsDropShadowEffect

    effect = QGraphicsDropShadowEffect(widget)
    effect.setOffset(offset_x, offset_y)
    c = QColor(color) if color is not None else QColor(0, 0, 0)
    c.setAlpha(alpha)
    effect.setColor(c)
    effect.setBlurRadius(blur)
    widget.setGraphicsEffect(effect)


def pill_background(*, top: int = PILL_RADIUS, bottom: int = PILL_RADIUS) -> str:
    return (
        f"background-color: {COLOR_CHROME_BG};"
        f" border-top-left-radius: {top}px; border-top-right-radius: {top}px;"
        f" border-bottom-left-radius: {bottom}px; border-bottom-right-radius: {bottom}px;"
    )


def make_card(width: int):
    """Build the standard centred dialog card: fixed width, dark rounded
    background and a drop shadow. Callers add their own inner layout.

    Shared by every centred overlay (Confirm/Info/Volume/Home) so the look stays
    consistent in one place instead of being re-specified per dialog.
    """
    from PyQt6.QtWidgets import QWidget

    card = QWidget()
    card.setFixedWidth(width)
    card.setStyleSheet(
        f"background-color: {COLOR_CARD_BG}; border-radius: {CARD_RADIUS_PX}px;"
    )
    apply_card_shadow(card)
    return card


def separator():
    from PyQt6.QtWidgets import QFrame

    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: {COLOR_SEPARATOR};")
    return line


def tile_normal(color: str) -> str:
    return f"""
        QToolButton {{
            font-size: 18px;
            font-weight: bold;
            color: white;
            background-color: {color};
            border: none;
            border-radius: 32px;
            padding: 12px 8px 16px 8px;
        }}
    """


def tile_selected(color: str) -> str:
    """The focused tile — its own colour with a solid white selection border
    (size still comes from the grow animation)."""
    return f"""
        QToolButton {{
            font-size: 18px;
            font-weight: bold;
            color: white;
            background-color: {color};
            border: 3px solid white;
            border-radius: 32px;
            padding: 12px 8px 16px 8px;
        }}
    """


def tile_moving(color: str) -> str:
    """The focused tile while in move mode — its normal look plus a dashed border
    as the only move cue (size still comes from the grow animation)."""
    return f"""
        QToolButton {{
            font-size: 18px;
            font-weight: bold;
            color: white;
            background-color: {color};
            border: 3px dashed white;
            border-radius: 32px;
            padding: 12px 8px 16px 8px;
        }}
    """


def add_tile(selected: bool) -> str:
    """The synthetic ``[＋]`` add-app tile: a transparent, dashed-outline
    affordance (the same dashed cue as move mode) so it never reads as a real
    app. Its border brightens to the accent colour when focused."""
    border = COLOR_ACCENT if selected else "#6b7280"
    return f"""
        QToolButton {{
            color: {border};
            background-color: transparent;
            border: 3px dashed {border};
            border-radius: 32px;
            padding: 12px 8px 16px 8px;
        }}
    """


def topbar_normal(color: str) -> str:
    return f"""
        QPushButton {{
            background-color: {color};
            color: white;
            border: none;
            border-radius: {_TOPBAR_RADIUS}px;
        }}
    """


def topbar_selected() -> str:
    return f"""
        QPushButton {{
            background-color: {COLOR_ACCENT};
            color: black;
            border: 3px solid white;
            border-radius: {_TOPBAR_RADIUS}px;
        }}
    """


# Role (fill) and focus (white ring) are independent axes, so primary can stay
# accent-filled without looking like the cursor.

def _dialog_button(bg: str, fg: str, hover_bg: str, *,
                   focused: bool, border: str = "transparent") -> str:
    ring = "3px solid white" if focused else f"2px solid {border}"
    return f"""
        QPushButton {{
            font-size: 22px;
            font-weight: 600;
            padding: 14px 24px;
            background-color: {bg};
            color: {fg};
            border-radius: {_DIALOG_RADIUS}px;
            border: {ring};
        }}
        QPushButton:hover {{ background-color: {hover_bg}; }}
    """


def dialog_primary(focused: bool = False) -> str:
    """The default / affirmative action — accent-filled even when unfocused."""
    return _dialog_button(COLOR_ACCENT, "black", COLOR_ACCENT_HI, focused=focused)


def dialog_secondary(focused: bool = False) -> str:
    return _dialog_button(COLOR_BTN_BG, "white", COLOR_TRACK, focused=focused)


def dialog_selected(focused: bool = False) -> str:
    """A chosen radio value: accent *outline*, not fill, so it marks the pick
    without reading as a primary action."""
    return _dialog_button(COLOR_TRACK, "white", COLOR_BTN_HI,
                          focused=focused, border=COLOR_ACCENT)


def dialog_disabled() -> str:
    return _dialog_button(COLOR_SURFACE_HI, "#6b7280", COLOR_SURFACE_HI, focused=False)


_DIALOG_ROLES = {
    "primary": dialog_primary,
    "secondary": dialog_secondary,
    "selected": dialog_selected,
}


def apply_focus_glow(widget, on: bool) -> None:
    """The accent halo behind a focused button, drawn as a graphics effect since
    Qt style sheets have no box-shadow."""
    if not on:
        widget.setGraphicsEffect(None)
        return
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QGraphicsDropShadowEffect

    glow = QGraphicsDropShadowEffect(widget)
    glow.setOffset(0, 0)
    glow.setBlurRadius(28)
    color = QColor(COLOR_ACCENT)
    color.setAlpha(180)
    glow.setColor(color)
    widget.setGraphicsEffect(glow)


def style_dialog_button(btn, *, role: str = "primary", focused: bool = False) -> None:
    """Paint one button. ``role``: primary / secondary / selected / disabled."""
    if role == "disabled":
        btn.setStyleSheet(dialog_disabled())
        apply_focus_glow(btn, False)
        return
    btn.setStyleSheet(_DIALOG_ROLES[role](focused))
    apply_focus_glow(btn, focused)


def home_menu_item_normal() -> str:
    return f"""
        QPushButton {{
            font-size: 24px;
            padding: 18px 32px;
            background-color: {COLOR_CARD_BG};
            color: white;
            border: 2px solid transparent;
            border-radius: {_MENU_RADIUS}px;
            text-align: left;
        }}
    """


def home_menu_item_selected() -> str:
    return f"""
        QPushButton {{
            font-size: 24px;
            padding: 18px 32px;
            background-color: {COLOR_ACCENT};
            color: black;
            border: 2px solid white;
            border-radius: {_MENU_RADIUS}px;
            text-align: left;
        }}
    """


def flat_scrollbar() -> str:
    """A flat scrollbar: solid rounded track and handle, no native pseudo-3D
    frame, no arrow buttons. Apply to a QScrollArea (the rule also clears the
    area's own border/background)."""
    return f"""
        QScrollArea {{ background: transparent; border: none; }}
        QScrollBar:vertical {{
            background: {COLOR_CARD_BG};
            width: 10px;
            margin: 0;
            border: none;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical {{
            background: {COLOR_TRACK};
            min-height: 30px;
            border: none;
            border-radius: 5px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0; border: none; background: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}
    """
