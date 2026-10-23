"""Reading vector artwork (SVG, PDF) as filled shapes, without pixel tracing."""

from __future__ import annotations

import gzip
import io
import math
import warnings
import zlib
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

import numpy as np
from shapely.geometry import LinearRing, LineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from .geometry import as_polygons

VECTOR_SUFFIXES = {".svg": "svg", ".svgz": "svg", ".pdf": "pdf"}


@dataclass
class VectorArt:
    """Painted shapes of a vector document, bottom to top, in document units with y up.

    shapes  (colour '#rrggbb', geometry) pairs; later shapes cover earlier ones.
    The document frame runs from (0, 0) to (width, height); anything outside is cut off.
    """

    shapes: list[tuple[str, BaseGeometry]]
    width: float
    height: float

    def visible(self) -> list[tuple[str, BaseGeometry]]:
        """What can be seen of each colour once later shapes cover earlier ones, plus white
        paper wherever nothing is painted. Colours that are fully hidden are left out."""
        frame = Polygon([(0, 0), (self.width, 0), (self.width, self.height), (0, self.height)])
        taken = Polygon()
        by_color: dict[str, list[BaseGeometry]] = {}
        for color, geom in reversed(self.shapes):
            seen = geom.intersection(frame).difference(taken)
            if seen.area > 0:
                by_color.setdefault(color, []).append(seen)
                taken = taken.union(seen)
        paper = frame.difference(taken)
        if paper.area > 0:
            by_color.setdefault("#ffffff", []).append(paper)
        return [(c, unary_union(g)) for c, g in by_color.items()]


def vector_kind(source) -> str | None:
    """'svg' or 'pdf' when the source is a vector document, else None."""
    if isinstance(source, (str, PathLike)):
        return VECTOR_SUFFIXES.get(Path(source).suffix.lower())
    if isinstance(source, (bytes, bytearray)):
        return _sniff(bytes(source[:2048]))
    if hasattr(source, "read") and hasattr(source, "seek"):
        pos = source.tell()
        head = source.read(2048)
        source.seek(pos)
        return _sniff(head) if isinstance(head, bytes) else None
    return None


def _sniff(head: bytes) -> str | None:
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\x1f\x8b"):   # .svgz: decompress what the first bytes give
        try:
            head = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(head)
        except zlib.error:
            return None
    return "svg" if b"<svg" in head.lower() else None


def _read_bytes(source) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    if isinstance(source, (str, PathLike)):
        return Path(source).read_bytes()
    return source.read()


def load_vector(source, page: int = 0, tolerance: float = 0.002) -> VectorArt:
    """Read an SVG or PDF (path, bytes or binary file object) into painted shapes.

    page       PDF page number, from 0.
    tolerance  how closely curves are followed, as a fraction of the document's larger side.

    Fills and strokes in flat colours are supported. Gradients, embedded images and SVG
    text are skipped with a warning: convert text to outlines before exporting.
    """
    kind = vector_kind(source)
    data = _read_bytes(source)
    if kind == "pdf":
        data = _pdf_to_svg(data, page)
    elif data.startswith(b"\x1f\x8b"):
        data = gzip.decompress(data)
    return _parse_svg(data, tolerance)


def _pdf_to_svg(data: bytes, page: int) -> bytes:
    try:
        import pymupdf
    except ImportError:
        raise ImportError("PDF input needs PyMuPDF: pip install img2print[pdf]") from None
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if not 0 <= page < len(doc):
            raise ValueError(f"PDF has {len(doc)} page(s), no page {page}")
        # Text as outlines, so lettering is kept as shapes.
        return doc[page].get_svg_image(text_as_path=True).encode("utf-8")


def _parse_svg(data: bytes, tolerance: float) -> VectorArt:
    import svgelements as se

    svg = se.SVG.parse(io.BytesIO(data), reify=True)
    width, height = float(svg.width), float(svg.height)
    if not (width > 0 and height > 0):
        raise ValueError("SVG has no size: give it width/height or a viewBox")
    step = tolerance * max(width, height)

    shapes: list[tuple[str, BaseGeometry]] = []
    skipped: set[str] = set()
    for el in svg.elements():
        if isinstance(el, se.Text):
            skipped.add("text (convert it to outlines)")
            continue
        if isinstance(el, se.Image):
            skipped.add("embedded images")
            continue
        if not isinstance(el, se.Shape):
            continue
        path = se.Path(el)
        if len(path) == 0:
            continue
        subpaths = [_flatten(sp, step) for sp in path.as_subpaths()]
        subpaths = [(pts, closed) for pts, closed in subpaths if len(pts) >= 2]
        if not subpaths:
            continue

        fill = _paint(el, "fill", skipped)
        if fill is not None:
            evenodd = str(el.values.get("fill-rule", "nonzero")).strip() == "evenodd"
            area = _fill_area([pts for pts, _ in subpaths], evenodd)
            if not area.is_empty:
                shapes.append((fill, area))

        stroke = _paint(el, "stroke", skipped)
        width_attr = getattr(el, "implicit_stroke_width", None) or el.stroke_width or 0
        if stroke is not None and width_attr > 0:
            area = _stroke_area(subpaths, float(width_attr), el.values)
            if not area.is_empty:
                shapes.append((stroke, area))

    if skipped:
        warnings.warn("ignored in vector input: " + ", ".join(sorted(skipped)))
    # Flip so y points up, as in traced raster artwork.
    flipped = [(c, _flip(g, height)) for c, g in shapes]
    return VectorArt(flipped, width, height)


def _paint(el, attr: str, skipped: set[str]) -> str | None:
    """Flat colour of an element's fill or stroke, blended onto white by its opacity."""
    raw = str(el.values.get(attr, "")).strip()
    if raw.startswith("url("):
        skipped.add("gradients and patterns")
        return None
    color = getattr(el, attr)
    if color is None or color.value is None:
        return None
    opacity = color.alpha / 255.0
    try:
        opacity *= float(el.values.get("opacity", 1))
    except (TypeError, ValueError):
        pass
    if opacity <= 0.01:
        return None
    rgb = np.array([color.red, color.green, color.blue], dtype=float)
    rgb = rgb * opacity + 255.0 * (1 - opacity)
    return "#" + "".join(f"{int(round(v)):02x}" for v in rgb)


def _flatten(subpath, step: float) -> tuple[np.ndarray, bool]:
    """Points along one subpath, curves sampled about every `step` units."""
    import svgelements as se

    pts: list[tuple[float, float]] = []
    closed = False
    for seg in subpath:
        if isinstance(seg, se.Move):
            pts.append((seg.end.x, seg.end.y))
        elif isinstance(seg, (se.Line, se.Close)):
            if seg.start is not None and not pts:
                pts.append((seg.start.x, seg.start.y))
            pts.append((seg.end.x, seg.end.y))
            closed = closed or isinstance(seg, se.Close)
        else:
            try:
                length = seg.length(error=1e-4)
            except Exception:
                length = step * 32
            n = int(min(max(math.ceil(length / step), 4), 400))
            for p in seg.npoint(np.linspace(0, 1, n + 1)[1:]):
                pts.append((p[0], p[1]))
    arr = np.array(pts, dtype=np.float64).reshape(-1, 2)
    # Drop repeated points: they make zero-length edges.
    if len(arr) > 1:
        keep = np.r_[True, np.any(np.abs(np.diff(arr, axis=0)) > 1e-9, axis=1)]
        arr = arr[keep]
    return arr, closed


def _fill_area(rings: list[np.ndarray], evenodd: bool) -> BaseGeometry:
    """Area painted by a fill, with the SVG fill rule. Open subpaths are closed implicitly."""
    rings = [r for r in rings if len(r) >= 3]
    if not rings:
        return Polygon()
    if len(rings) == 1:
        return Polygon(rings[0]).buffer(0) if evenodd else _nonzero(rings)
    if evenodd:
        out = Polygon()
        for r in rings:
            out = out.symmetric_difference(Polygon(r).buffer(0))
        return out
    return _nonzero(rings)


def _nonzero(rings: list[np.ndarray]) -> BaseGeometry:
    """Nonzero winding rule: split the plane along every edge and keep the faces that the
    rings wind around. Handles overlapping subpaths and self-crossing outlines."""
    edges = unary_union([LinearRing(r) for r in rings])
    faces = []
    for face in polygonize(edges):
        p = face.representative_point()
        if sum(_winding(r, p.x, p.y) for r in rings) != 0:
            faces.append(face)
    return unary_union(faces) if faces else Polygon()


def _winding(ring: np.ndarray, x: float, y: float) -> int:
    closed = np.vstack([ring, ring[:1]])
    x0, y0 = closed[:-1].T
    x1, y1 = closed[1:].T
    side = (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0)
    up = (y0 <= y) & (y1 > y) & (side > 0)
    down = (y0 > y) & (y1 <= y) & (side < 0)
    return int(up.sum() - down.sum())


_CAPS = {"butt": "flat", "round": "round", "square": "square"}
_JOINS = {"miter": "mitre", "miter-clip": "mitre", "arcs": "round", "round": "round", "bevel": "bevel"}


def _stroke_area(subpaths: list[tuple[np.ndarray, bool]], width: float, values: dict) -> BaseGeometry:
    cap = _CAPS.get(str(values.get("stroke-linecap", "butt")).strip(), "flat")
    join = _JOINS.get(str(values.get("stroke-linejoin", "miter")).strip(), "mitre")
    try:
        limit = float(values.get("stroke-miterlimit", 4))
    except (TypeError, ValueError):
        limit = 4.0
    parts = []
    for pts, closed in subpaths:
        line = LinearRing(pts) if closed and len(pts) >= 3 else LineString(pts)
        parts.append(line.buffer(width / 2, cap_style=cap, join_style=join, mitre_limit=limit))
    return unary_union(parts)


def _flip(geom: BaseGeometry, height: float) -> BaseGeometry:
    from shapely.affinity import affine_transform

    return affine_transform(geom, [1, 0, 0, -1, 0, height])


def vector_shapes_mm(art: VectorArt, scale: float) -> list[tuple[str, BaseGeometry]]:
    """Visible area of each colour scaled to millimetres, as polygons only."""
    from shapely.affinity import scale as scale_geom

    out = []
    for color, geom in art.visible():
        polys = as_polygons(scale_geom(geom, scale, scale, origin=(0, 0)))
        if polys:
            out.append((color, unary_union(polys)))
    return out
