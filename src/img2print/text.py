"""Text on the model: lines of text in any font, as 2D shapes in millimetres.

    shape = text_shape("שלום עולם", "Heebo", size=10, weight=700)   # centred on (0, 0)

Text is shaped with HarfBuzz, so Hebrew (with niqqud), Arabic, kerning and ligatures come out as
the font intends, and mixed right-to-left / left-to-right lines are put in reading order.
"""

from __future__ import annotations

import math
import threading
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from .colors import parse_color
from .fonts import DEFAULT_FONT, font_file
from .geometry import as_polygons

# "paint":   flush with the surface, set apart only by its colour.
# "emboss":  stands depth mm out of the surface.
# "engrave": cut depth mm into the surface.
STYLES = ("paint", "emboss", "engrave")
ALIGNS = ("left", "center", "right")
TOLERANCE = 0.01   # mm: how closely glyph curves are followed
NOZZLE = 0.4       # mm: strokes thinner than this may not print


@dataclass
class Text:
    """One block of text on the design. The design is the traced artwork; padding is outside it.

    x, y      the centre of the text, as fractions of the design: x from its left edge, y from
              its top edge (0.5, 0.5 is the middle). Values outside 0..1 put text in the padding;
              anything past the plate's edge is cut off.
    size      letter height, mm: the height of capitals and Hebrew letters.
    rotation  degrees, counter-clockwise.
    style     paint, emboss or engrave, see STYLES.
    color     the text's filament. None (emboss and engrave only) keeps the colour of the surface.
    depth     how far embossed text stands out, or engraved text is cut in, mm.
    thicken   makes every stroke this much wider, mm, so thin fonts print (see thin_strokes()).
    """

    text: str = ""
    font: str = DEFAULT_FONT
    weight: int = 700
    italic: bool = False
    size: float = 10.0
    x: float = 0.5
    y: float = 0.5
    rotation: float = 0.0
    align: str = "center"
    line_spacing: float = 1.0
    letter_spacing: float = 0.0   # extra space between letters, mm
    style: str = "paint"
    color: str | None = "black"
    depth: float = 0.6
    thicken: float = 0.0

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        if self.style not in STYLES:
            raise ValueError(f"unknown text style {self.style!r}; choose from {', '.join(STYLES)}")
        if self.align not in ALIGNS:
            raise ValueError(f"unknown text align {self.align!r}; choose from {', '.join(ALIGNS)}")
        for k in ("size", "line_spacing", "depth"):
            if not getattr(self, k) > 0:
                raise ValueError(f"text {k} must be positive, got {getattr(self, k)}")
        if self.thicken < 0:
            raise ValueError(f"text thicken cannot be negative, got {self.thicken}")
        if not 1 <= self.weight <= 1000:
            raise ValueError(f"text weight must be between 1 and 1000, got {self.weight}")
        if self.color is None:
            if self.style == "paint":
                raise ValueError("painted text needs a colour")
        else:
            parse_color(self.color)
        if not self.font.strip():
            raise ValueError("text needs a font")

    def shape(self, width: float, height: float) -> BaseGeometry:
        """The text as 2D shapes on a design of this size (mm, origin bottom-left, y up)."""
        geom = text_shape(self.text, self.font, self.size, weight=self.weight, italic=self.italic,
                          align=self.align, line_spacing=self.line_spacing, letter_spacing=self.letter_spacing)
        if self.thicken:
            geom = geom.buffer(self.thicken / 2)
        if self.rotation:
            geom = affinity.rotate(geom, self.rotation, origin=(0, 0))
        return affinity.translate(geom, self.x * width, (1 - self.y) * height)


def thin_strokes(shape: BaseGeometry, width: float = NOZZLE) -> float:
    """The share of a shape (0..1) in strokes thinner than width mm: what an opening by half
    the width wipes away. Above a few percent, the text needs thicken or a bolder weight.
    Strokes within 5% of the width count as wide enough: curves are only followed to 0.01 mm."""
    if shape.is_empty:
        return 0.0
    r = 0.95 * width / 2
    kept = shape.buffer(-r).buffer(r)
    return max(0.0, 1 - kept.area / shape.area)


def text_shape(
    text: str,
    font: str = DEFAULT_FONT,
    size: float = 10.0,
    *,
    weight: int = 400,
    italic: bool = False,
    align: str = "center",
    line_spacing: float = 1.0,
    letter_spacing: float = 0.0,
) -> BaseGeometry:
    """Lines of text as shapely polygons in mm, y up, centred on (0, 0).

    font            a family name (see fonts.font_file) or the path of a font file.
    size            letter height, mm (capitals, Hebrew letters).
    align           left, center or right, for text with several lines.
    line_spacing    times the font's own line height.
    letter_spacing  extra space after each letter, mm.

    The centre is the middle of the block from the top of the first line's letters to the
    last line's baseline, so it stays put while you type.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    if not text.strip():
        return Polygon()
    path, axes = (Path(font), {}) if Path(font).suffix.lower() in (".ttf", ".otf") and Path(font).is_file() \
        else font_file(font, weight, italic)
    f = _load(str(path), tuple(sorted(axes.items())))
    scale = size / f.cap_height
    spacing = letter_spacing / scale
    line_height = f.line_height * line_spacing

    placed = []   # (glyph id, x, y) in font units
    widths = []
    for n, line in enumerate(lines):
        x, glyphs = 0.0, []
        for run, rtl in _visual_runs(line):
            for gid, dx, dy, advance in f.shape(run, rtl):
                glyphs.append((gid, x + dx, dy - n * line_height))
                x += advance + (spacing if advance else 0)
        widths.append(x)
        placed.append(glyphs)
    block = max(widths)

    polys = []
    for glyphs, w in zip(placed, widths):
        shift = {"left": 0.0, "center": (block - w) / 2, "right": block - w}[align]
        for gid, x, y in glyphs:
            outline = f.outline(gid)
            if not outline.is_empty:
                polys.append(affinity.translate(outline, x + shift, y))
    if not polys:
        return Polygon()
    top, bottom = f.cap_height, -(len(lines) - 1) * line_height
    geom = unary_union(polys)
    geom = affinity.translate(geom, -block / 2, -(top + bottom) / 2)
    return affinity.scale(geom, scale, scale, origin=(0, 0))


# --- fonts -----------------------------------------------------------------------------------------

class _Font:
    """A font loaded for shaping (HarfBuzz) and drawing (fontTools), in font units."""

    def __init__(self, path: str, axes: tuple[tuple[str, float], ...]):
        data = Path(path).read_bytes()
        self.hb = hb.Font(hb.Face(data))
        if axes:
            self.hb.set_variations(dict(axes))
        tt = TTFont(path)
        self.glyphs = tt.getGlyphSet(location=dict(axes) if axes else None)
        self.order = tt.getGlyphOrder()
        self._outlines: dict[int, BaseGeometry] = {}
        self._lock = threading.Lock()
        upem = tt["head"].unitsPerEm
        self.cap_height = 0.7 * upem    # until measured: sets the curve tolerance below
        os2 = tt["OS/2"] if "OS/2" in tt else None
        cap = getattr(os2, "sCapHeight", 0) or 0
        if cap <= 0:   # older fonts: measure a capital H, or a Hebrew alef
            cmap = tt.getBestCmap() or {}
            cap = next((self.outline(cmap[c]).bounds[3] for c in (0x48, 0x5D0)
                        if c in cmap and not self.outline(cmap[c]).is_empty), 0.7 * upem)
        self.cap_height = cap
        hhea = tt["hhea"]
        self.line_height = (hhea.ascent - hhea.descent + hhea.lineGap) or 1.2 * upem

    def shape(self, run: str, rtl: bool) -> list[tuple[int, float, float, float]]:
        """(glyph id, x offset, y offset, advance) per glyph, left to right."""
        buf = hb.Buffer()
        buf.add_str(run)
        buf.direction = "rtl" if rtl else "ltr"
        buf.guess_segment_properties()
        with self._lock:
            hb.shape(self.hb, buf, {"kern": True, "liga": True})
        return [(i.codepoint, p.x_offset, p.y_offset, p.x_advance)
                for i, p in zip(buf.glyph_infos, buf.glyph_positions)]

    def outline(self, gid: int) -> BaseGeometry:
        if isinstance(gid, str):
            gid = self.order.index(gid)
        with self._lock:
            if gid not in self._outlines:
                # Flatten in font units at a tolerance that is TOLERANCE mm at a 10 mm letter.
                pen = _FlattenPen(self.glyphs, tolerance=self.cap_height / 10 * TOLERANCE)
                self.glyphs[self.order[gid]].draw(pen)
                pen.closePath()
                self._outlines[gid] = _nonzero(pen.rings)
            return self._outlines[gid]


@lru_cache(maxsize=32)
def _load(path: str, axes: tuple[tuple[str, float], ...]) -> _Font:
    return _Font(path, axes)


class _FlattenPen(BasePen):
    """Collects glyph contours as point lists, with curves split into short straight pieces."""

    def __init__(self, glyphset, tolerance: float):
        super().__init__(glyphset)
        self.tolerance = tolerance
        self.rings: list[list[tuple[float, float]]] = []
        self._ring: list[tuple[float, float]] = []

    def _moveTo(self, pt):
        self._flush()
        self._ring = [pt]

    def _lineTo(self, pt):
        self._ring.append(pt)

    def _qCurveToOne(self, p1, p2):
        p0 = self._ring[-1]
        n = self._steps(abs(p0[0] - 2 * p1[0] + p2[0]) + abs(p0[1] - 2 * p1[1] + p2[1]))
        for i in range(1, n + 1):
            t = i / n
            a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t * t
            self._ring.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))

    def _curveToOne(self, p1, p2, p3):
        p0 = self._ring[-1]
        d = max(abs(p0[0] - 2 * p1[0] + p2[0]) + abs(p0[1] - 2 * p1[1] + p2[1]),
                abs(p1[0] - 2 * p2[0] + p3[0]) + abs(p1[1] - 2 * p2[1] + p3[1]))
        n = self._steps(1.5 * d)
        for i in range(1, n + 1):
            t = i / n
            a, b, c, e = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
            self._ring.append((a * p0[0] + b * p1[0] + c * p2[0] + e * p3[0],
                               a * p0[1] + b * p1[1] + c * p2[1] + e * p3[1]))

    def _steps(self, bend: float) -> int:
        # A curve's distance from its chord shrinks with the square of the number of pieces.
        return max(1, min(64, math.ceil(math.sqrt(bend / (4 * self.tolerance)))))

    def _closePath(self):
        self._flush()

    def _endPath(self):
        self._flush()

    def _flush(self):
        if len(self._ring) >= 3:
            self.rings.append(self._ring)
        self._ring = []


def _nonzero(rings: list[list[tuple[float, float]]]) -> BaseGeometry:
    """Fill contours with the nonzero winding rule, as fonts do. Variable fonts often keep
    overlapping contours, which an even-odd fill would punch holes into."""
    polys = [(Polygon(r), _signed_area(r)) for r in rings]
    polys = [(p, a) for p, a in polys if abs(a) > 0]
    if not polys:
        return Polygon()
    if len(polys) == 1:
        return polys[0][0].buffer(0)
    # Cut the plane along every contour, then keep the faces the contours wind around.
    edges = unary_union([LineString(list(p.exterior.coords)) for p, _ in polys])
    faces = []
    for face in polygonize(edges):
        pt = face.representative_point()
        winding = sum(1 if a > 0 else -1 for p, a in polys if p.contains(pt))
        if winding:
            faces.append(face)
    geom = unary_union(faces) if faces else Polygon()
    return unary_union([p for p in as_polygons(geom.buffer(0))])


def _signed_area(ring) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])) / 2


# --- right-to-left text ----------------------------------------------------------------------------

def _visual_runs(line: str) -> list[tuple[str, bool]]:
    """Split a line into runs of one direction, in the order they appear left to right.

    A compact form of the Unicode bidi algorithm that covers signs and labels: the line's
    direction comes from its first strong letter; numbers read left to right; spaces and
    punctuation take the direction of the letters on both sides, or the line's direction
    where those differ. Returns (text, right_to_left) pairs; each run's text is in logical order.
    """
    if not line:
        return []
    kinds = []
    for ch in line:
        b = unicodedata.bidirectional(ch)
        kinds.append("R" if b in ("R", "AL") else "L" if b == "L" else
                     "N" if b in ("EN", "AN") else "M" if b == "NSM" else "X")
    for i, k in enumerate(kinds):   # marks belong to the letter before them
        if k == "M":
            kinds[i] = kinds[i - 1] if i else "X"
    for i in range(1, len(kinds) - 1):   # 1,000 / 12.5 / 3:30 are one number
        if kinds[i] == "X" and kinds[i - 1] == kinds[i + 1] == "N" and \
                unicodedata.bidirectional(line[i]) in ("CS", "ES"):
            kinds[i] = "N"
    rtl_line = next((k == "R" for k in kinds if k in "RL"), False)
    base = 1 if rtl_line else 0

    # Numbers: inside right-to-left text (or after it) they sit one level up, read left to right.
    strong = ["R" if k == "N" and _last_strong(kinds, i, rtl_line) == "R" else ("L" if k == "N" else k)
              for i, k in enumerate(kinds)]
    levels = [0] * len(kinds)
    for i, k in enumerate(kinds):
        if k == "N":
            levels[i] = 2 if base == 1 or strong[i] == "R" else 0
        elif k == "R":
            levels[i] = 1
        elif k == "L":
            levels[i] = 2 if base == 1 else 0
    # Neutrals: the direction of the strong letters on both sides, else the line's.
    i = 0
    while i < len(kinds):
        if kinds[i] != "X":
            i += 1
            continue
        j = i
        while j < len(kinds) and kinds[j] == "X":
            j += 1
        before = strong[i - 1] if i else ("R" if rtl_line else "L")
        after = strong[j] if j < len(kinds) else ("R" if rtl_line else "L")
        level = (1 if before == "R" else (2 if base == 1 else 0)) if before == after else base
        for n in range(i, j):
            levels[n] = level
        i = j

    runs = []   # (text, level), logical order
    for ch, lv in zip(line, levels):
        if runs and runs[-1][1] == lv:
            runs[-1][0].append(ch)
        else:
            runs.append(([ch], lv))
    # Reverse every sequence at each level and above, from the highest level down to the lowest odd one.
    order = list(range(len(runs)))
    top = max(lv for _, lv in runs)
    lowest_odd = min((lv for _, lv in runs if lv % 2), default=top + 1)
    for level in range(top, lowest_odd - 1, -1):
        i = 0
        while i < len(order):
            if runs[order[i]][1] >= level:
                j = i
                while j < len(order) and runs[order[j]][1] >= level:
                    j += 1
                order[i:j] = reversed(order[i:j])
                i = j
            else:
                i += 1
    return [("".join(runs[k][0]), runs[k][1] % 2 == 1) for k in order]


def _last_strong(kinds: list[str], i: int, rtl_line: bool) -> str:
    for k in reversed(kinds[:i]):
        if k in "RL":
            return k
    return "R" if rtl_line else "L"
