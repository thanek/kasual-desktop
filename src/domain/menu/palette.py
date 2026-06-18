"""The predefined tile-colour palette offered by the Tile Management Popover.

Domain data, not presentation: the fixed set of colours a tile may be recoloured
to. The picker overlay renders these swatches; the chosen value is persisted to
the tile's ``.desktop`` ``X-Kasual-Color``.
"""

# Mostly Nord-derived swatches; edit freely — the picker renders whatever is here.
TILE_COLORS: tuple[str, ...] = (
    "#0B1220", # Midnight Blue
    "#112240", # Deep Navy
    "#1E293B", # Dark Slate
    "#155E75", # Ocean Blue
    "#0369A1", # Cyan Blue
    "#1D4ED8", # Accent Blue
    "#4338CA", # Accent Indigo
    "#6D28D9", # Accent Violet
    "#9D174D", # Accent Crimson
    "#166534", # Accent Green
    "#0EA5E9", # Neon Sky Blue
    "#2563EB", # Electric Blue
    "#4F46E5", # Vivid Indigo
    "#7C3AED", # Neon Purple
    "#A21CAF", # Deep Magenta
    "#DB2777", # Hot Pink
    "#DC2626", # Arcade Red
    "#EA580C", # Burnt Orange
    "#CA8A04", # Retro Gold
    "#16A34A"  # Neon Green
)
