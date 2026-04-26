COLOR_ACCENT   = "#88c0d0"
COLOR_BG_DARK  = "#0b140e"
COLOR_TEXT     = "white"
COLOR_TOPBAR   = "rgba(15, 17, 25, 210)"
COLOR_RUNNING  = "#a3be8c"
COLOR_CARD_BG  = "#2e3440"
CARD_RADIUS_PX = 12


def truncate(text: str, max_len: int) -> str:
    return text[:max_len - 1] + '…' if len(text) > max_len else text


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
    effect.setColor(QColor(color) if color is not None else QColor(0, 0, 0, alpha))
    effect.setBlurRadius(blur)
    widget.setGraphicsEffect(effect)


def tile_normal(color: str) -> str:
    return f"""
        QToolButton {{
            font-size: 18px;
            font-weight: bold;
            color: white;
            background-color: {color};
            border: none;
            border-radius: 8px;
            padding: 12px 8px 16px 8px;
        }}
    """


def tile_selected() -> str:
    return f"""
        QToolButton {{
            font-size: 18px;
            font-weight: bold;
            color: black;
            background-color: {COLOR_ACCENT};
            border: 3px solid white;
            border-radius: 8px;
            padding: 12px 8px 16px 8px;
        }}
    """


def topbar_normal(color: str) -> str:
    return f"""
        QPushButton {{
            background-color: {color};
            color: white;
            border: none;
            border-radius: 30px;
        }}
    """


def topbar_selected() -> str:
    return f"""
        QPushButton {{
            background-color: {COLOR_ACCENT};
            color: black;
            border: 3px solid white;
            border-radius: 30px;
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
            border-radius: 6px;
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
            border-radius: 6px;
            text-align: left;
        }}
    """
