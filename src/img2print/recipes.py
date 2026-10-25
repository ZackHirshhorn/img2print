"""Ready-made recipes that turn artwork into printable models."""

from __future__ import annotations

import numpy as np
from shapely.affinity import translate
from shapely.geometry import Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .colors import parse_color, to_hex, unique_names
from .geometry import as_polygons, difference, extrude, rounded_rect, union
from .image import ImageSource
from .model import Model, Part
from .trace import Artwork, trace_colors, trace_image

SHAPES = ("box", "cylinder")
# Embossed shapes reach this far down into the surface they stand on, so they fuse with it, mm.
FUSE = 0.01
# The design's right, up and outward directions on each face, so it reads correctly from outside.
FACES = {
    "top": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "bottom": ((1, 0, 0), (0, -1, 0), (0, 0, -1)),
    "front": ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
    "back": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "right": ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
    "left": ((0, -1, 0), (0, 0, 1), (-1, 0, 0)),
}


def two_color_tile(
    artwork: Artwork,
    *,
    base: float = 1.2,
    layer: float = 0.8,
    corner_radius: float = 10.0,
    padding: float = 0.0,
    plate: Polygon | None = None,
    raised: bool = False,
    stacked: bool = False,
    thickness: float | None = None,
    base_color: str | None = None,
    ink: tuple[str, str] = ("black", "#000000"),
    paper: tuple[str, str] = ("white", "#ffffff"),
) -> Model:
    """Build a 2-colour plate from traced artwork.

    base           paper-colour base plate thickness, mm.
    layer          thickness of the 2-colour layer / ink relief height, mm.
    corner_radius  rounding of the default plate (the image rectangle), mm.
    padding        blank border around the image on the default plate, mm.
    plate          custom plate outline in mm; overrides the rounded rectangle and padding.
    raised         ink stands above a plain plate instead of being inlaid flush.
    stacked        colour by layer, see multi_color_tile(); with one ink this is raised, plus
                   the filament change.
    thickness      instead of base and layer: every colour runs this full thickness, mm.
    base_color     print the base as its own part in this colour, with the whole design
                   (paper included) in the layer on top. Default: the base is paper.
    ink, paper     (part name, display colour) of each material.
    """
    if stacked and (thickness is not None or base_color is not None):
        raise ValueError("colour by layer stacks on a base in the paper colour; drop thickness and base_color")
    plate, offset = _plate(plate, artwork, corner_radius, padding)
    ink_2d = translate(artwork.geometry, offset, offset).intersection(plate)

    ink_mesh = extrude(ink_2d, layer, z0=base) if thickness is None else extrude(ink_2d, thickness)
    if ink_mesh is None:
        raise ValueError("no ink regions inside the plate; try invert or a different threshold")

    return Model(_background(plate, ink_2d, paper[0], paper[1], base=base, layer=layer,
                             raised=raised or stacked, thickness=thickness, base_color=base_color)
                 + [Part(ink[0], ink_mesh, ink[1])],
                 [(base, ink[0])] if stacked else [])


def image_to_tile(
    source: ImageSource,
    *,
    width: float | None = None,
    height: float | None = None,
    longest: float | None = None,
    invert: bool = False,
    threshold: float = 0.5,
    min_area: float = 0.05,
    simplify: float = 0.02,
    page: int = 0,
    **tile_options,
) -> Model:
    """One call from an image (or SVG / PDF) to a 2-colour tile.

    See trace_image() for the tracing options; extra keyword arguments go to two_color_tile().
    """
    artwork = trace_image(source, width, invert, threshold, min_area, simplify,
                          height=height, longest=longest, page=page)
    return two_color_tile(artwork, **tile_options)


def multi_color_tile(
    layers: list[Artwork],
    *,
    base: float = 1.2,
    layer: float = 0.8,
    corner_radius: float = 10.0,
    padding: float = 0.0,
    plate: Polygon | None = None,
    raised: bool = False,
    stacked: bool = False,
    thickness: float | None = None,
    base_color: str | None = None,
    names: list[str] | None = None,
    reliefs: list[tuple[BaseGeometry, float]] = (),
) -> Model:
    """Build a plate with any number of colours, one filament each.

    layers   traced colours, e.g. from trace_colors(). The first is the background:
             it forms the base plate and fills every gap between the others. Where
             two later layers overlap, the later one wins.
    names    part names, one per layer. Default: the nearest colour name
             ('black', 'red', 'red-2', ...).
    stacked  colour by layer, for a printer with one nozzle and no colour changer: every
             layer of the print is one colour. The background is the base; then each colour
             in turn gets its own band, layer mm thick, one above the other. A colour's band
             also runs under every later colour, holding it up, so from above each area shows
             its own colour. The model's filament_changes say where to swap filament.
    reliefs  (shape, height) pairs in the layers' coordinates: each shape stands height mm out
             of the surface under it, in that surface's colour, or is cut -height mm into it
             when height is negative. Used for embossed and engraved text.
    The other options are as in two_color_tile().
    """
    if stacked and (thickness is not None or base_color is not None):
        raise ValueError("colour by layer stacks on a base in the background colour; "
                         "drop thickness and base_color")
    if len(layers) < 2:
        raise ValueError("need a background and at least one colour; try more colours")
    if names is None:
        names = unique_names([a.color or "#808080" for a in layers])
    if len(names) != len(layers) or len(set(names)) != len(names):
        raise ValueError("names must be distinct, one per layer")
    background = layers[0]
    plate, offset = _plate(plate, background, corner_radius, padding)

    # Clip each colour to the plate and remove what later colours cover.
    taken = Polygon()
    regions = []
    for art in reversed(layers[1:]):
        region = translate(art.geometry, offset, offset).intersection(plate).difference(taken)
        polys = [p for p in as_polygons(region.buffer(0)) if p.area > 1e-4]   # drop slivers
        region = unary_union(polys) if polys else Polygon()
        taken = taken.union(region)
        regions.append(region)
    regions.reverse()

    colours = [(art, name, region) for art, name, region in zip(layers[1:], names[1:], regions)
               if not region.is_empty]
    if not colours and not reliefs:   # a plain plate is fine when text is cut into it
        raise ValueError("no coloured regions inside the plate; try more colours or a different background")
    parts, changes = [], []
    for i, (art, name, region) in enumerate(colours):
        if stacked:
            z0 = base + i * layer
            mesh = extrude(unary_union([r for *_, r in colours[i:]]), layer, z0=z0)
            changes.append((z0, name))
        else:
            mesh = extrude(region, layer, z0=base) if thickness is None else extrude(region, thickness)
        parts.append(Part(name, mesh, art.color))

    model = Model(_background(plate, taken, names[0], background.color, base=base, layer=layer,
                              raised=raised or stacked, thickness=thickness, base_color=base_color) + parts,
                  changes)
    if reliefs:
        # The top surface: what shows from above, how high it is, and which part it belongs to.
        bg_top = thickness if thickness is not None else base if raised or stacked else base + layer
        bg_name = names[0] if any(p.name == names[0] for p in model) else "base"
        surface = [(plate.difference(taken), bg_top, bg_name)]
        for i, (_, name, region) in enumerate(colours):
            top = thickness if thickness is not None else base + (i + 1) * layer if stacked else base + layer
            surface.append((region, top, name))
        _relief(model, surface, [(translate(g, offset, offset), h) for g, h in reliefs])
    return model


def _relief(model: Model, surface, reliefs) -> None:
    """Emboss (height > 0) or engrave (height < 0) shapes into the surface, piece by piece."""
    added: dict[str, list] = {}
    cuts = []
    for geom, height in reliefs:
        for region, top, name in surface:
            polys = [p for p in as_polygons(geom.intersection(region).buffer(0)) if p.area > 1e-4]
            if not polys:
                continue
            piece = unary_union(polys)
            if height > 0:
                added.setdefault(name, []).append(extrude(piece, height + FUSE, z0=top - FUSE))
            else:
                cuts.append(extrude(piece, 1 - height, z0=top + height))   # open above the surface
    for p in model:
        if p.name in added:
            p.mesh = union(p.mesh, *added[p.name])
        if cuts:
            p.mesh = difference(p.mesh, *cuts)


def _plate(plate, artwork, corner_radius, padding) -> tuple[Polygon, float]:
    """The plate outline, and how far to shift the artwork onto it."""
    if plate is not None:
        return plate, 0.0
    return rounded_rect(artwork.width + 2 * padding, artwork.height + 2 * padding, corner_radius), padding


def _background(plate, taken, name, color, *, base, layer, raised, thickness, base_color) -> list[Part]:
    """The parts around and under the colours (taken): the background, and a separate
    base when base_color differs from the background colour."""
    around = plate.difference(taken)
    if thickness is not None:
        mesh = extrude(around, thickness)
        return [Part(name, mesh, color)] if mesh is not None else []
    under = extrude(plate, base)
    around = None if raised else extrude(around, layer, z0=base)
    if base_color is None or color is None or parse_color(base_color) == parse_color(color):
        return [Part(name, union(under, around), color)]
    base_part = Part("base", under, to_hex(parse_color(base_color)))
    return [base_part] + ([Part(name, around, color)] if around is not None else [])


def image_to_multi_color_tile(
    source: ImageSource,
    *,
    width: float | None = None,
    height: float | None = None,
    longest: float | None = None,
    colors: int | None = 3,
    palette: list[str] | None = None,
    background: str | None = None,
    smooth: float = 0.6,
    min_area: float = 0.05,
    simplify: float = 0.02,
    page: int = 0,
    **tile_options,
) -> Model:
    """One call from a colour image (or SVG / PDF) to a multi-colour tile.

    See trace_colors() for the tracing options; extra keyword arguments go to multi_color_tile().
    """
    layers = trace_colors(source, width, colors, palette, background, smooth, min_area, simplify,
                          height=height, longest=longest, page=page)
    return multi_color_tile(layers, **tile_options)


def face_size(shape: str, size: tuple[float, float, float], face: str) -> tuple[float, float, float]:
    """(width, height, depth) of one face of a shape: the face itself, and how deep the
    shape is behind it, mm. size is (x, y, z) for a box, (diameter, unused, height) for a cylinder."""
    if shape not in SHAPES:
        raise ValueError(f"unknown shape {shape!r}; choose from {', '.join(SHAPES)}")
    if face not in FACES:
        raise ValueError(f"unknown face {face!r}; choose from {', '.join(FACES)}")
    if shape == "cylinder" and face not in ("top", "bottom"):
        raise ValueError("a cylinder's side is curved; put the design on its top or bottom")
    extents = np.abs(np.array(FACES[face], dtype=float)) @ _extents(shape, size)
    return tuple(float(e) for e in extents)


def shape_with_design(
    layers: list[Artwork],
    *,
    shape: str = "box",
    size: tuple[float, float, float] = (40.0, 40.0, 40.0),
    face: str = "top",
    layer: float = 0.8,
    raised: bool = False,
    stacked: bool = False,
    full_depth: bool = False,
    base_color: str | None = None,
    names: list[str] | None = None,
    reliefs: list[tuple[BaseGeometry, float]] = (),
) -> Model:
    """A solid box or cylinder with the design on one of its faces.

    shape       "box" (size is x, y, z in mm) or "cylinder" (size is diameter, unused, height).
    face        top, bottom, front, back, left or right; a cylinder has only top and bottom.
                The design is centred on the face, reads correctly from outside, and is
                clipped to the face.
    layer       depth of the design, mm: inlaid flush into the face, or standing out of it when raised.
    stacked     colour by layer, as in multi_color_tile(): the colours stand out of the face, one
                band each. Print it with the design face up; filament_changes count from the
                opposite face, on the bed.
    full_depth  every colour runs right through the shape, to the opposite face.
    base_color  print the body as its own part in this colour, with the whole face (background
                included) in the layer. Default: the body is the background colour.
    layers, names, reliefs  as in multi_color_tile(); reliefs stand out of or cut into the face.

    The shape is built as a tile whose plate is the face, then turned onto that face.
    """
    face_w, face_h, depth = face_size(shape, size, face)
    raised = raised or stacked
    if not (raised or full_depth) and depth <= layer:
        raise ValueError(f"the {shape} is only {depth:g} mm deep behind its {face} face; "
                         f"the design layer ({layer:g} mm) needs more")
    w, h = layers[0].width, layers[0].height
    if shape == "box":
        outline = box(-face_w / 2, -face_h / 2, face_w / 2, face_h / 2)
    else:
        outline = Point(0, 0).buffer(face_w / 2, quad_segs=64)
    model = multi_color_tile(layers, base=depth if raised else depth - layer, layer=layer,
                             plate=translate(outline, w / 2, h / 2), raised=raised, stacked=stacked,
                             thickness=depth if full_depth else None, base_color=base_color, names=names,
                             reliefs=reliefs)

    # Tile coordinates: the face centre is at (w/2, h/2, depth), facing +z.
    right, up, out = (np.array(v, dtype=float) for v in FACES[face])
    centre = np.array(_extents(shape, size)) / 2 + out * depth / 2
    turn = np.eye(4)
    turn[:3, :3] = np.column_stack([right, up, out])
    turn[:3, 3] = centre - right * w / 2 - up * h / 2 - out * depth
    for p in model:
        p.mesh.apply_transform(turn)
    low = model.bounds[0]
    for p in model:
        p.mesh.apply_translation(-low)
    return model


def _extents(shape: str, size: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = size
    return (x, x, z) if shape == "cylinder" else (x, y, z)
