"""From an image and Settings to traced layers and a printable model, in one place.

Used by the command line and the web app, so both build exactly the same model.
"""

from __future__ import annotations

import numpy as np
from shapely.geometry.base import BaseGeometry

from .colors import color_name, parse_color, to_hex
from .image import ImageSource
from .model import Model
from .recipes import multi_color_tile, shape_with_design, two_color_tile
from .settings import Settings
from .text import Text
from .trace import Artwork, trace_colors, trace_image

INK = ("black", "#000000")
PAPER = ("white", "#ffffff")
SAME_COLOR = 32.0   # text this close to a layer's colour (RGB distance) prints in that layer's filament


def trace_layers(source: ImageSource, settings: Settings) -> list[Artwork]:
    """Trace the artwork into one Artwork per filament, background first, each with .color set.

    In 2-colour mode this is [paper, ink]: the paper layer is the image rectangle minus the ink.
    """
    s = settings
    size = s.size()
    width = size.pop("width")
    if s.color_mode:
        layers = trace_colors(source, width, s.colors, s.palette, s.background,
                              s.smooth, s.min_area, s.simplify, **size)
    else:
        ink = trace_image(source, width, s.invert, s.threshold, s.min_area, s.simplify, **size)
        ink.color = INK[1]
        paper = Artwork(ink.frame.difference(ink.geometry), ink.width, ink.height, PAPER[1])
        layers = [paper, ink]
    fit = s.fit_box()
    if fit is not None and layers[0].height > fit[1]:   # traced to the fit width: too tall
        layers = [a.scaled(fit[1] / layers[0].height) for a in layers]
    return layers


def build_model(layers: list[Artwork], settings: Settings) -> Model:
    """Turn the layers from trace_layers() into a model, with the settings' recipe and texts."""
    names = None if settings.color_mode else [PAPER[0], INK[0]]
    reliefs = []
    texts = text_shapes(settings, layers[0].width, layers[0].height)
    for text, shape in texts:
        layers, names = _paint(text, shape, layers, names, settings.stacking == "layers")
        if text.style != "paint":
            reliefs.append((shape, text.depth if text.style == "emboss" else -text.depth))
    if settings.recipe == "shape":
        return shape_with_design(layers, names=names, reliefs=reliefs, **settings.shape_options())
    if settings.color_mode or texts:
        return multi_color_tile(layers, names=names, reliefs=reliefs, **settings.tile_options())
    return two_color_tile(layers[1], ink=INK, paper=PAPER, **settings.tile_options())


def text_shapes(settings: Settings, width: float, height: float) -> list[tuple[Text, BaseGeometry]]:
    """Each text with its shape on a design of this size (mm, y up); empty texts are left out."""
    out = []
    for text in settings.texts:
        shape = text.shape(width, height)
        if not shape.is_empty:
            out.append((text, shape))
    return out


def _paint(text: Text, shape: BaseGeometry, layers: list[Artwork], names: list[str] | None,
           stacked: bool) -> tuple[list[Artwork], list[str] | None]:
    """Put a text's colour into the layers: it covers what is under it, in the layer of the same
    colour or a new layer of its own. Text without a colour is left to the surface, except
    embossed text when colour by layer, which then takes the top colour (each layer of the print
    holds one filament)."""
    color = text.color
    if color is None:
        if not (stacked and text.style == "emboss"):
            return layers, names
        color = next((a.color for a in reversed(layers[1:]) if not a.is_empty), layers[0].color) or PAPER[1]
    rgb = np.array(parse_color(color), dtype=float)
    dist = [np.linalg.norm(np.array(parse_color(a.color or "#808080"), dtype=float) - rgb) for a in layers]
    match = int(np.argmin(dist)) if min(dist) <= SAME_COLOR else None
    layers = [Artwork(a.geometry.difference(shape), a.width, a.height, a.color) for a in layers]
    names = None if names is None else list(names)
    if match is None:
        layers.append(Artwork(shape, layers[0].width, layers[0].height, to_hex(rgb)))
        if names is not None:
            name = unique = color_name(color)
            n = 2
            while unique in names:
                unique, n = f"{name}-{n}", n + 1
            names.append(unique)
    elif match > 0:   # the background needs nothing: it fills whatever the colours leave
        art = layers[match]
        art.geometry = art.geometry.union(shape)
        if stacked:   # its band goes on top, so the text is the highest colour
            layers.append(layers.pop(match))
            if names is not None:
                names.append(names.pop(match))
    return layers, names


def build(source: ImageSource, settings: Settings) -> tuple[Model, list[Artwork]]:
    """Trace and build in one call. Returns (model, layers)."""
    layers = trace_layers(source, settings)
    return build_model(layers, settings), layers
