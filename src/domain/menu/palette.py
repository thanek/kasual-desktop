"""The predefined tile-colour palette offered by the Tile Management Popover.

Domain data, not presentation: the fixed set of colours a tile may be recoloured
to. The picker overlay renders these swatches; the chosen value is persisted to
the tile's ``.desktop`` ``X-Kasual-Color``.
"""

# Mostly Nord-derived swatches; edit freely — the picker renders whatever is here.
TILE_COLORS: tuple[str, ...] = (
    "#3B88C3", # 🟦
    "#DD2E44", # 🟥
    "#F4900C", # 🟨
    "#78B159", # 🟩
    "#AA8ED6", # 🟪
    "#E67E22", # 🟧
    "#2C2F33", # ⬛
    "#744E3B", # 🟫
    "#ffffff", # white
)
