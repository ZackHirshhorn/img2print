"""All options of a print job in one object, saved and loaded as JSON.

The command line, the web app and settings files share this one definition:

    settings = Settings(width=80, raised=True, colors=3)
    settings.save("logo.json")
    settings = Settings.load("logo.json")
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from os import PathLike
from pathlib import Path

from .colors import parse_color
from .trace import DEFAULT_WIDTH

RECIPES = ("tile",)
# "layers": a base in the background colour, the colours in a layer on top.
# "top":    a plain base in base_color, the whole design (background included) in a layer on top.
# "full":   every colour runs the full thickness.
STACKINGS = ("layers", "top", "full")


@dataclass
class Settings:
    """Every option of a print job. Give at most one of width, height or longest (mm):
    the size of the finished plate, padding included.

    Colour mode is used when colors or palette is set; otherwise the image becomes a
    2-colour (black / white) plate. page counts from 1, as on the command line.
    """

    recipe: str = "tile"
    # size, mm
    width: float | None = None
    height: float | None = None
    longest: float | None = None
    # plate: how the colours are stacked, see STACKINGS
    stacking: str = "layers"
    base: float = 1.2
    layer: float = 0.8
    thickness: float = 2.0
    base_color: str = "white"
    corner_radius: float = 10.0
    padding: float = 0.0          # blank border inside the size above
    raised: bool = False
    # 2-colour mode
    threshold: float = 0.5
    invert: bool = False
    # colour mode
    colors: int | None = None
    palette: list[str] | None = None
    background: str | None = None
    smooth: float = 0.6
    # tracing
    min_area: float = 0.05
    simplify: float = 0.02
    page: int = 1

    def __post_init__(self):
        self.validate()

    @property
    def color_mode(self) -> bool:
        return bool(self.colors or self.palette)

    def validate(self) -> None:
        """Raise ValueError with a readable message for any impossible option."""
        if self.recipe not in RECIPES:
            raise ValueError(f"unknown recipe {self.recipe!r}; choose from {', '.join(RECIPES)}")
        if self.stacking not in STACKINGS:
            raise ValueError(f"unknown stacking {self.stacking!r}; choose from {', '.join(STACKINGS)}")
        sizes = [k for k in ("width", "height", "longest") if getattr(self, k) is not None]
        if len(sizes) > 1:
            raise ValueError(f"give only one of width, height or longest, not {' and '.join(sizes)}")
        for k in sizes + ["base", "layer", "thickness"]:
            if not getattr(self, k) > 0:
                raise ValueError(f"{k} must be positive, got {getattr(self, k)}")
        for k in ("corner_radius", "padding", "smooth", "min_area", "simplify"):
            if getattr(self, k) < 0:
                raise ValueError(f"{k} cannot be negative, got {getattr(self, k)}")
        side = next((getattr(self, k) for k in sizes), DEFAULT_WIDTH)
        if side <= 2 * self.padding:
            raise ValueError(f"padding {self.padding} mm leaves no room for the design in {side} mm")
        if not 0 <= self.threshold <= 1:
            raise ValueError(f"threshold must be between 0 and 1, got {self.threshold}")
        if self.colors is not None and self.colors < 2:
            raise ValueError("colors must be at least 2 (the background and one more)")
        if self.page < 1:
            raise ValueError(f"page counts from 1, got {self.page}")
        for c in (self.palette or []) + ([self.background] if self.background else []) + [self.base_color]:
            parse_color(c)

    def size(self) -> dict:
        """Size and page keyword arguments for the tracing functions (page from 0).
        The design gets the plate size less the padding on both sides."""
        size = dict(width=self.width, height=self.height, longest=self.longest)
        if all(v is None for v in size.values()):
            size["width"] = DEFAULT_WIDTH
        size = {k: v if v is None else v - 2 * self.padding for k, v in size.items()}
        return dict(size, page=self.page - 1)

    def tile_options(self) -> dict:
        return dict(base=self.base, layer=self.layer, corner_radius=self.corner_radius,
                    padding=self.padding, raised=self.raised,
                    thickness=self.thickness if self.stacking == "full" else None,
                    base_color=self.base_color if self.stacking == "top" else None)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"unknown setting(s): {', '.join(unknown)}")
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Settings":
        return cls.from_dict(json.loads(text))

    def save(self, path: str | PathLike) -> None:
        Path(path).write_text(self.to_json() + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | PathLike) -> "Settings":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))
