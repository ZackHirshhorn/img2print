"""Ready-made recipes that turn artwork into printable models."""

from __future__ import annotations

from shapely.geometry import Polygon
from shapely.ops import unary_union

from .colors import unique_names
from .geometry import as_polygons, extrude, rounded_rect, union
from .image import ImageSource
from .model import Model, Part
from .trace import Artwork, trace_colors, trace_image


def two_color_tile(
    artwork: Artwork,
    *,
    base: float = 1.2,
    layer: float = 0.8,
    corner_radius: float = 10.0,
    plate: Polygon | None = None,
    raised: bool = False,
    face_down: bool = False,
    ink: tuple[str, str] = ("black", "#000000"),
    paper: tuple[str, str] = ("white", "#ffffff"),
) -> Model:
    """Build a 2-colour plate from traced artwork.

    base           paper-colour base plate thickness, mm.
    layer          thickness of the 2-colour layer / ink relief height, mm.
    corner_radius  rounding of the default plate (the image rectangle), mm.
    plate          custom plate outline in mm; overrides the rounded rectangle.
    raised         ink stands above a plain plate instead of being inlaid flush.
    face_down      flip so the 2-colour face prints on the build plate.
    ink, paper     (part name, display colour) of each material.
    """
    if plate is None:
        plate = rounded_rect(artwork.width, artwork.height, corner_radius)
    ink_2d = artwork.geometry.intersection(plate)

    ink_mesh = extrude(ink_2d, layer, z0=base)
    if ink_mesh is None:
        raise ValueError("no ink regions inside the plate; try invert or a different threshold")

    paper_mesh = extrude(plate, base)
    if not raised:
        paper_mesh = union(paper_mesh, extrude(plate.difference(ink_2d), layer, z0=base))

    model = Model([Part(paper[0], paper_mesh, paper[1]), Part(ink[0], ink_mesh, ink[1])])
    return model.flip_face_down() if face_down else model


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
    plate: Polygon | None = None,
    raised: bool = False,
    face_down: bool = False,
    names: list[str] | None = None,
) -> Model:
    """Build a plate with any number of colours, one filament each.

    layers   traced colours, e.g. from trace_colors(). The first is the background:
             it forms the base plate and fills every gap between the others. Where
             two later layers overlap, the later one wins.
    names    part names, one per layer. Default: the nearest colour name
             ('black', 'red', 'red-2', ...).
    The other options are as in two_color_tile().
    """
    if len(layers) < 2:
        raise ValueError("need a background and at least one colour; try more colours")
    if names is None:
        names = unique_names([a.color or "#808080" for a in layers])
    if len(names) != len(layers) or len(set(names)) != len(names):
        raise ValueError("names must be distinct, one per layer")
    background = layers[0]
    if plate is None:
        plate = rounded_rect(background.width, background.height, corner_radius)

    # Clip each colour to the plate and remove what later colours cover.
    taken = Polygon()
    regions = []
    for art in reversed(layers[1:]):
        region = art.geometry.intersection(plate).difference(taken)
        polys = [p for p in as_polygons(region.buffer(0)) if p.area > 1e-4]   # drop slivers
        region = unary_union(polys) if polys else Polygon()
        taken = taken.union(region)
        regions.append(region)
    regions.reverse()

    parts = []
    for art, name, region in zip(layers[1:], names[1:], regions):
        mesh = extrude(region, layer, z0=base)
        if mesh is not None:
            parts.append(Part(name, mesh, art.color))
    if not parts:
        raise ValueError("no coloured regions inside the plate; try more colours or a different background")

    paper_mesh = extrude(plate, base)
    if not raised:
        paper_mesh = union(paper_mesh, extrude(plate.difference(taken), layer, z0=base))

    model = Model([Part(names[0], paper_mesh, background.color)] + parts)
    return model.flip_face_down() if face_down else model


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
