"""From an image and Settings to traced layers and a printable model, in one place.

Used by the command line and the web app, so both build exactly the same model.
"""

from __future__ import annotations

from .image import ImageSource
from .model import Model
from .recipes import multi_color_tile, two_color_tile
from .settings import Settings
from .trace import Artwork, trace_colors, trace_image

INK = ("black", "#000000")
PAPER = ("white", "#ffffff")


def trace_layers(source: ImageSource, settings: Settings) -> list[Artwork]:
    """Trace the artwork into one Artwork per filament, background first, each with .color set.

    In 2-colour mode this is [paper, ink]: the paper layer is the image rectangle minus the ink.
    """
    s = settings
    if s.color_mode:
        return trace_colors(source, s.width, s.colors, s.palette, s.background,
                            s.smooth, s.min_area, s.simplify, **s.size())
    ink = trace_image(source, s.width, s.invert, s.threshold, s.min_area, s.simplify, **s.size())
    ink.color = INK[1]
    paper = Artwork(ink.frame.difference(ink.geometry), ink.width, ink.height, PAPER[1])
    return [paper, ink]


def build_model(layers: list[Artwork], settings: Settings) -> Model:
    """Turn the layers from trace_layers() into a model, with the settings' recipe."""
    if settings.color_mode:
        return multi_color_tile(layers, **settings.tile_options())
    return two_color_tile(layers[1], ink=INK, paper=PAPER, **settings.tile_options())


def build(source: ImageSource, settings: Settings) -> tuple[Model, list[Artwork]]:
    """Trace and build in one call. Returns (model, layers)."""
    layers = trace_layers(source, settings)
    return build_model(layers, settings), layers
