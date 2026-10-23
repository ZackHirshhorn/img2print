"""Colour helpers: parsing, hex formatting and friendly names for filament parts."""

from __future__ import annotations

import numpy as np

# Common filament colours, used to name parts ("red" reads better than "#d42a1f").
NAMED_COLORS = {
    "black": "#000000",
    "white": "#ffffff",
    "grey": "#808080",
    "silver": "#c0c0c0",
    "red": "#e02020",
    "dark-red": "#8b0000",
    "orange": "#ff8c00",
    "yellow": "#ffd700",
    "gold": "#d4af37",
    "green": "#2e9e3e",
    "dark-green": "#1a5c2a",
    "blue": "#1f5fd6",
    "navy": "#1b2a4a",
    "cyan": "#20b8d8",
    "purple": "#7b3fa0",
    "pink": "#ff7eb6",
    "brown": "#7a4a24",
    "beige": "#e8d8b0",
}


def parse_color(color: str) -> tuple[int, int, int]:
    """'#rrggbb', 'rrggbb', '#rgb' or a name from NAMED_COLORS -> (r, g, b)."""
    c = NAMED_COLORS.get(color.strip().lower(), color).strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        raise ValueError(f"not a colour: {color!r}")
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        raise ValueError(f"not a colour: {color!r}") from None


def to_hex(rgb) -> str:
    r, g, b = (int(round(float(v))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def color_name(color: str) -> str:
    """Nearest name in NAMED_COLORS."""
    rgb = np.array(parse_color(color), dtype=float)
    return min(NAMED_COLORS, key=lambda n: np.sum((np.array(parse_color(n), dtype=float) - rgb) ** 2))


def unique_names(colors: list[str]) -> list[str]:
    """Friendly, distinct part names: ['black', 'red', 'red-2', ...]."""
    names, seen = [], {}
    for c in colors:
        n = color_name(c)
        seen[n] = seen.get(n, 0) + 1
        names.append(n if seen[n] == 1 else f"{n}-{seen[n]}")
    return names
