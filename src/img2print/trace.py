"""Tracing artwork into 2D vector regions measured in millimetres.

Raster images are traced along sub-pixel contours; SVG and PDF files are read as shapes directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shapely.affinity import scale
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from skimage.filters import gaussian
from skimage.measure import find_contours

from .colors import parse_color
from .geometry import as_polygons
from .image import ImageSource, group_colors, load_darkness, load_rgb, quantize
from .vector import load_vector, vector_kind, vector_shapes_mm

DEFAULT_WIDTH = 100.0


@dataclass
class Artwork:
    """Traced 2D artwork in millimetres.

    The origin is the bottom-left corner of the image and y points up, so the
    artwork reads correctly when viewed from above.
    """

    geometry: BaseGeometry
    width: float
    height: float
    color: str | None = None  # "#rrggbb" when traced from a colour image

    @property
    def area(self) -> float:
        return self.geometry.area

    @property
    def frame(self) -> Polygon:
        """The full image rectangle."""
        return box(0, 0, self.width, self.height)

    @property
    def is_empty(self) -> bool:
        return self.geometry.is_empty

    def scaled(self, factor: float) -> "Artwork":
        """The same artwork, factor times the size."""
        return Artwork(scale(self.geometry, factor, factor, origin=(0, 0)),
                       self.width * factor, self.height * factor, self.color)


def output_scale(
    natural_width: float,
    natural_height: float,
    width: float | None = None,
    height: float | None = None,
    longest: float | None = None,
) -> float:
    """Millimetres per image unit for the requested size.

    Give at most one of width, height or longest (the longer side), in mm; the other
    side follows the aspect ratio. With none, the image is DEFAULT_WIDTH mm wide.
    """
    given = {k: v for k, v in (("width", width), ("height", height), ("longest", longest)) if v is not None}
    if len(given) > 1:
        raise ValueError(f"give only one of width, height or longest, not {' and '.join(given)}")
    for k, v in given.items():
        if not v > 0:
            raise ValueError(f"{k} must be positive, got {v}")
    if height is not None:
        return height / natural_height
    if longest is not None:
        return longest / max(natural_width, natural_height)
    return (DEFAULT_WIDTH if width is None else width) / natural_width


def _clean(region: BaseGeometry, min_area: float, simplify: float) -> BaseGeometry:
    region = region.buffer(0).simplify(simplify, preserve_topology=True)
    polys = [p for p in as_polygons(region) if p.area >= min_area]
    return unary_union(polys) if polys else Polygon()


def trace(
    darkness: np.ndarray,
    width: float | None = None,
    threshold: float = 0.5,
    min_area: float = 0.05,
    simplify: float = 0.02,
    *,
    height: float | None = None,
    longest: float | None = None,
) -> Artwork:
    """Trace sub-pixel contours of the dark regions of a darkness map.

    darkness   2D array in [0, 1] (1 = ink). A boolean mask works too.
    width, height, longest
               physical size of the whole image in mm: give one, the other side follows
               the aspect ratio. Default 100 mm wide.
    threshold  darkness level at which the contour is drawn.
    min_area   drop specks smaller than this, mm^2.
    simplify   contour simplification tolerance, mm.
    """
    darkness = np.asarray(darkness, dtype=np.float64)
    if darkness.ndim != 2:
        raise ValueError(f"darkness map must be 2D, got shape {darkness.shape}")
    rows, cols = darkness.shape
    mm_per_px = output_scale(cols, rows, width, height, longest)

    # Pad with "paper" so every contour is closed.
    padded = np.pad(darkness, 1, mode="constant", constant_values=0.0)
    contours = find_contours(padded, threshold)

    # Combine rings with the even-odd rule: nested rings automatically become holes.
    region = Polygon()
    for c in contours:
        if len(c) < 4:
            continue
        r = c[:, 0] - 1
        col = c[:, 1] - 1
        x = (col + 0.5) * mm_per_px
        y = (rows - (r + 0.5)) * mm_per_px  # flip so the image is not mirrored
        ring = Polygon(np.column_stack([x, y])).buffer(0)
        if not ring.is_empty:
            region = region.symmetric_difference(ring)

    return Artwork(_clean(region, min_area, simplify), cols * mm_per_px, rows * mm_per_px)


def trace_image(
    source: ImageSource,
    width: float | None = None,
    invert: bool = False,
    threshold: float = 0.5,
    min_area: float = 0.05,
    simplify: float = 0.02,
    *,
    height: float | None = None,
    longest: float | None = None,
    page: int = 0,
) -> Artwork:
    """Load an image and trace its dark regions. See trace() for the parameters.

    SVG and PDF files are read as shapes instead of traced, so edges stay exact: a shape
    counts as ink when the darkness of its colour is above threshold, and the unpainted
    page is white paper. page picks the PDF page (from 0).
    """
    if vector_kind(source):
        art = load_vector(source, page)
        scale = output_scale(art.width, art.height, width, height, longest)
        ink = []
        for color, geom in vector_shapes_mm(art, scale):
            dark = _color_darkness(color)
            if (1.0 - dark if invert else dark) > threshold:
                ink.append(geom)
        return Artwork(_clean(unary_union(ink), min_area, simplify), art.width * scale, art.height * scale)
    return trace(load_darkness(source, invert), width, threshold, min_area, simplify,
                 height=height, longest=longest)


def _color_darkness(color: str) -> float:
    # Same grey weighting as PIL's "L" mode, so vector and raster input agree.
    r, g, b = parse_color(color)
    return 1.0 - (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def trace_colors(
    source: ImageSource,
    width: float | None = None,
    colors: int | None = 3,
    palette: list[str] | None = None,
    background: str | None = None,
    smooth: float = 0.6,
    min_area: float = 0.05,
    simplify: float = 0.02,
    *,
    height: float | None = None,
    longest: float | None = None,
    page: int = 0,
) -> list[Artwork]:
    """Split a colour image into flat colours and trace each one.

    colors      number of colours to find automatically, background included.
    palette     or the exact colours to use ('#rrggbb' or names); overrides colors.
    background  colour of the base plate; nearest found colour is used.
                Default: the colour that covers most of the image border.
    smooth      blur of each colour mask before tracing, in pixels. Gives smooth
                sub-pixel edges instead of pixel steps; 0 turns it off. Not used for SVG/PDF.
    width, height, longest, min_area, simplify  as in trace(); page as in trace_image().

    SVG and PDF files are read as shapes: their fill and stroke colours are grouped the
    same way as pixel colours, and the unpainted page counts as white.

    Returns one Artwork per colour, each with .color set. The background comes first,
    then the other colours from largest to smallest area. Colours with nothing left
    after min_area are dropped.
    """
    n_colors = None if palette else colors
    if vector_kind(source):
        art = load_vector(source, page)
        scale = output_scale(art.width, art.height, width, height, longest)
        w, h = art.width * scale, art.height * scale
        shapes = vector_shapes_mm(art, scale)
        if not shapes:
            raise ValueError("the vector file has no visible shapes")
        groups, hexes = group_colors([parse_color(c) for c, _ in shapes], [g.area for _, g in shapes],
                                     n_colors, palette)
        frame = box(0, 0, w, h)
        border = frame.difference(frame.buffer(-0.01 * min(w, h)))
        traced, border_amount = [], []
        for i in range(len(hexes)):
            region = unary_union([g for (_, g), grp in zip(shapes, groups) if grp == i])
            traced.append(Artwork(_clean(region, min_area, simplify), w, h))
            border_amount.append(region.intersection(border).area)
    else:
        labels, hexes = quantize(load_rgb(source), colors=n_colors, palette=palette)
        border_labels = np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
        border_amount = np.bincount(border_labels, minlength=len(hexes))
        traced = []
        for i in range(len(hexes)):
            mask = (labels == i).astype(np.float64)
            if smooth > 0:
                # Blurring every mask by the same kernel keeps them summing to 1, so neighbouring
                # colours meet along the same 0.5 contour.
                mask = gaussian(mask, sigma=smooth, mode="nearest")
            traced.append(trace(mask, width, 0.5, min_area, simplify, height=height, longest=longest))

    if background is None:
        bg = int(np.argmax(border_amount))
    else:
        target = np.array(parse_color(background), dtype=float)
        bg = int(np.argmin([np.sum((np.array(parse_color(h), dtype=float) - target) ** 2) for h in hexes]))

    layers = []
    for i, (color, art) in enumerate(zip(hexes, traced)):
        art.color = color
        if i == bg or not art.is_empty:
            layers.append((i == bg, art))
    layers.sort(key=lambda t: (not t[0], -t[1].area))
    return [art for _, art in layers]
