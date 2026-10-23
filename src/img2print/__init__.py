"""img2print: turn flat graphic designs into multi-colour 3D prints.

Quick start:

    import img2print
    model = img2print.image_to_tile("logo.png", width=100)
    model.export("out/logo")   # out/logo_white.stl, out/logo_black.stl, out/logo.3mf

Step by step:

    art = img2print.trace_image("logo.png", width=100, threshold=0.5)
    model = img2print.two_color_tile(art, raised=True, corner_radius=5)

More colours:

    model = img2print.image_to_multi_color_tile("logo.png", width=100, colors=4)
    layers = img2print.trace_colors("logo.png", palette=["white", "black", "#d42a1f"])

Vector input and other sizes:

    model = img2print.image_to_tile("logo.svg", height=40)        # SVG / PDF: exact shapes
    model = img2print.image_to_multi_color_tile("logo.pdf", longest=120, colors=3)
"""

from .geometry import extrude, rounded_rect, union
from .image import group_colors, load_darkness, load_rgb, open_image, quantize
from .model import Model, Part
from .recipes import image_to_multi_color_tile, image_to_tile, multi_color_tile, two_color_tile
from .trace import Artwork, output_scale, trace, trace_colors, trace_image
from .vector import VectorArt, load_vector

__version__ = "0.1.0"

__all__ = [
    "Artwork",
    "Model",
    "Part",
    "extrude",
    "group_colors",
    "image_to_multi_color_tile",
    "image_to_tile",
    "load_darkness",
    "load_rgb",
    "load_vector",
    "multi_color_tile",
    "open_image",
    "output_scale",
    "quantize",
    "rounded_rect",
    "trace",
    "trace_colors",
    "trace_image",
    "two_color_tile",
    "union",
    "VectorArt",
]
