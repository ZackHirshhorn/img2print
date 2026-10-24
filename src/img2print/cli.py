"""Command line: img2print logo.png --width 80 --raised   (add --colors 4 for more colours)"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from .pipeline import build_model, trace_layers
from .recipes import FACES, SHAPES
from .settings import Settings

SIZES = ("width", "height", "longest")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="img2print",
        description="Convert a black-and-white design into a printable 2-colour 3D model "
                    "(<name>_white.stl, <name>_black.stl and a combined <name>.3mf). "
                    "With --colors or --palette, a colour design becomes one STL per colour. "
                    "SVG and PDF files are read as shapes, without pixel tracing.",
        # Only options given on the command line are set, so they can override a --settings file.
        argument_default=argparse.SUPPRESS,
    )
    ap.add_argument("image", help="input image (PNG, JPG, BMP, ...) or vector file (SVG, PDF)")
    size = ap.add_mutually_exclusive_group()
    size.add_argument("--width", type=float, help="model width in mm (default 100)")
    size.add_argument("--height", type=float, help="model height in mm, instead of --width")
    size.add_argument("--longest", type=float, help="length of the longer side in mm, instead of --width")
    ap.add_argument("--base", type=float, help="white base plate thickness, mm (default 1.2)")
    ap.add_argument("--layer", type=float,
                    help="thickness of the 2-colour layer / black relief height; by default (colour by "
                         "layer) the height of each colour's band, mm (default 0.8)")
    ap.add_argument("--thickness", type=float,
                    help="instead of --base and --layer: every colour runs this full plate thickness, mm")
    ap.add_argument("--base-color",
                    help="print the base plain in this colour, with the whole design in --layer on top")
    ap.add_argument("--corner-radius", type=float, help="plate corner rounding radius, mm (default 10)")
    ap.add_argument("--padding", type=float,
                    help="blank border around the design, mm, inside the size given (default 0)")
    ap.add_argument("--raised", action="store_true", help="black stands above a plain white plate")
    ap.add_argument("--shape", choices=SHAPES,
                    help="put the design on one face of a solid box or cylinder instead of a plate; "
                         "the size options then size the design, which by default fits the face")
    ap.add_argument("--shape-size",
                    help="size of the shape, mm: WxDxH for a box, DIAMETERxH for a cylinder (default 40x40x40)")
    ap.add_argument("--face", choices=FACES,
                    help="which face of the shape carries the design (default top; a cylinder: top or bottom)")
    ap.add_argument("--threshold", type=float,
                    help="darkness threshold 0..1, 2-colour mode only (default 0.5)")
    ap.add_argument("--invert", action="store_true",
                    help="treat light pixels as the black material, 2-colour mode only")
    ap.add_argument("--colors", type=int,
                    help="split a colour image into this many filaments, background included")
    ap.add_argument("--palette",
                    help="exact filament colours, comma separated: '#ffffff,#000000,#d42a1f' or 'white,black,red'")
    ap.add_argument("--background",
                    help="colour of the base plate (default: the colour around the image border)")
    ap.add_argument("--smooth", type=float,
                    help="edge smoothing in pixels for colour mode, 0 = off (default 0.6)")
    ap.add_argument("--min-area", type=float, help="drop specks smaller than this, mm^2 (default 0.05)")
    ap.add_argument("--simplify", type=float, help="contour simplification tolerance, mm (default 0.02)")
    ap.add_argument("--page", type=int, help="PDF page to use, from 1 (default 1)")
    ap.add_argument("--settings", help="read all options from a JSON settings file; other options override it")
    ap.add_argument("--save-settings", help="also write the options used to this JSON settings file")
    ap.add_argument("--out", help="output path prefix (default: next to the image)")
    args = vars(ap.parse_args(argv))
    # Non-Latin file names (e.g. Hebrew) must not crash printing to a cp1252 pipe on Windows.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    img_path = Path(args.pop("image"))
    out = args.pop("out", None)
    save_to = args.pop("save_settings", None)
    if "palette" in args:
        args["palette"] = [c.strip() for c in args["palette"].split(",") if c.strip()]
    shape_size = args.pop("shape_size", None)
    if "shape" in args or "face" in args or shape_size:
        args["recipe"] = "shape"
    try:
        settings = Settings.load(args.pop("settings")) if "settings" in args else Settings()
        if any(k in args for k in SIZES):
            settings = replace(settings, width=None, height=None, longest=None)
        if "thickness" in args:
            args["stacking"] = "full"
        elif "base_color" in args:
            args["stacking"] = "top"
        elif any(k in args for k in ("base", "layer", "raised")) and settings.stacking == "full":
            args["stacking"] = "layers"
        settings = replace(settings, **args)
        if shape_size:
            settings = replace(settings, **_shape_size(shape_size, settings.shape))

        layers = trace_layers(img_path, settings)
        frame = layers[0].frame.area
        if settings.color_mode:
            print(f"Image {img_path.name} -> {layers[0].width:.1f} x {layers[0].height:.1f} mm, "
                  f"{len(layers)} colours (background {layers[0].color})")
            for art in layers[1:]:
                print(f"  {art.color}: {art.area:.0f} mm^2 ({100 * art.area / frame:.1f}% of image)")
        else:
            art = layers[1]
            print(f"Image {img_path.name} -> {art.width:.1f} x {art.height:.1f} mm, "
                  f"ink area {art.area:.0f} mm^2 ({100 * art.area / frame:.1f}% of image)")
        model = build_model(layers, settings)
    except (ValueError, ImportError, OSError) as e:
        ap.exit(1, f"error: {e}\n")

    if save_to:
        settings.save(save_to)
    written = model.export(out or img_path.with_suffix(""))
    print(model.summary())
    grams = sum(s["grams"] for s in model.stats())
    print(f"Filament (solid, PLA): about {grams:.1f} g")
    for z, name in model.filament_changes:
        print(f"Colour by layer: pause at {z:g} mm and load {name}")
    print("Wrote " + ", ".join(str(p) for p in written) + (f", {save_to}" if save_to else ""))


def _shape_size(text: str, shape: str) -> dict:
    """'40x30x20' (box) or '50x20' (cylinder: diameter x height) as Settings fields."""
    try:
        sides = [float(v) for v in text.lower().split("x")]
    except ValueError:
        sides = []
    if shape == "cylinder" and len(sides) == 2:
        return dict(shape_width=sides[0], shape_height=sides[1])
    if shape == "box" and len(sides) == 3:
        return dict(shape_width=sides[0], shape_depth=sides[1], shape_height=sides[2])
    expected = "DIAMETERxHEIGHT, e.g. 50x20" if shape == "cylinder" else "WxDxH, e.g. 40x30x20"
    raise ValueError(f"--shape-size {text!r}: a {shape} needs {expected}")


if __name__ == "__main__":
    main()
