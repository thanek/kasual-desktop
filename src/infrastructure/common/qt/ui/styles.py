from domain.shared.text import truncate  # noqa: F401 - re-exported: callers use styles.truncate

COLOR_ACCENT   = "#88c0d0"
COLOR_BG_DARK  = "#0b140e"
COLOR_TEXT     = "white"
COLOR_TOPBAR   = "rgba(15, 17, 25, 210)"
COLOR_RUNNING  = "#a3be8c"
COLOR_CARD_BG  = "#2e3440"
CARD_RADIUS_PX = 12


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
            border-radius: 13px;
        }}
    """


def topbar_selected() -> str:
    return f"""
        QPushButton {{
            background-color: {COLOR_ACCENT};
            color: black;
            border: 3px solid white;
            border-radius: 13px;
        }}
    """


def dialog_idle() -> str:
    return """
        QPushButton {
            font-size: 22px;
            padding: 14px 24px;
            background-color: #4c566a;
            color: white;
            border-radius: 6px;
            border: 2px solid transparent;
        }
    """


def dialog_focused() -> str:
    return f"""
        QPushButton {{
            font-size: 22px;
            padding: 14px 24px;
            background-color: {COLOR_ACCENT};
            color: black;
            border-radius: 6px;
            border: 2px solid white;
        }}
    """


def home_menu_item_normal() -> str:
    return """
        QPushButton {
            font-size: 24px;
            padding: 18px 32px;
            background-color: #2e3440;
            color: white;
            border: 2px solid transparent;
            text-align: left;
        }
    """


def home_menu_item_selected() -> str:
    return f"""
        QPushButton {{
            font-size: 24px;
            padding: 18px 32px;
            background-color: {COLOR_ACCENT};
            color: black;
            border: 2px solid white;
            text-align: left;
        }}
    """


def flat_scrollbar() -> str:
    """A flat scrollbar: solid rounded track and handle, no native pseudo-3D
    frame, no arrow buttons. Apply to a QScrollArea (the rule also clears the
    area's own border/background)."""
    return """
        QScrollArea { background: transparent; border: none; }
        QScrollBar:vertical {
            background: #2e3440;
            width: 10px;
            margin: 0;
            border: none;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical {
            background: #4c566a;
            min-height: 30px;
            border: none;
            border-radius: 5px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0; border: none; background: none;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
    """
