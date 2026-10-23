"""Loading artwork as a "darkness" map (1 = ink, 0 = paper) or as colour labels."""

from __future__ import annotations

import io
from os import PathLike
from typing import BinaryIO, Union

import numpy as np
from PIL import Image
from skimage.color import rgb2lab

from .colors import parse_color, to_hex

ImageSource = Union[str, PathLike, bytes, bytearray, BinaryIO, Image.Image]


def open_image(source: ImageSource) -> Image.Image:
    """Open an image from a path, raw bytes, a binary file object or a PIL image."""
    if isinstance(source, Image.Image):
        return source
    if isinstance(source, (bytes, bytearray)):
        return Image.open(io.BytesIO(source))
    return Image.open(source)


def _on_white(source: ImageSource) -> Image.Image:
    """Composite transparent pixels onto white, so a logo exported with a
    transparent background behaves like one on white paper."""
    im = open_image(source)
    if im.mode in ("RGBA", "LA", "P", "PA"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    return im


def load_darkness(source: ImageSource, invert: bool = False) -> np.ndarray:
    """Return a float array in [0, 1] where 1 = black ink, 0 = white paper."""
    gray = np.asarray(_on_white(source).convert("L"), dtype=np.float64) / 255.0
    dark = 1.0 - gray
    return 1.0 - dark if invert else dark


def load_rgb(source: ImageSource) -> np.ndarray:
    """Return an (rows, cols, 3) uint8 array, transparency composited onto white."""
    return np.asarray(_on_white(source).convert("RGB"), dtype=np.uint8)


def quantize(
    rgb: np.ndarray,
    colors: int | None = None,
    palette: list[str] | None = None,
    iterations: int = 30,
    seed: int = 0,
) -> tuple[np.ndarray, list[str]]:
    """Group the pixels of an RGB image into a few flat colours.

    colors   find this many colours automatically (k-means in Lab colour space).
    palette  or give the colours ('#rrggbb' or names); every pixel goes to the nearest.

    Returns (labels, hex_colours): labels is a (rows, cols) int array indexing hex_colours.
    With colors, each hex colour is the average of its pixels; with palette, it is the
    palette colour as given.
    """
    rgb = np.asarray(rgb, dtype=np.uint8)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"expected an (rows, cols, 3) RGB array, got shape {rgb.shape}")
    # Work on the distinct colours with their pixel counts: logos have few of them.
    uniq, inverse, counts = np.unique(rgb.reshape(-1, 3), axis=0, return_inverse=True, return_counts=True)
    nearest, hexes = group_colors(uniq, counts, colors, palette, iterations, seed)
    return nearest[inverse.reshape(-1)].reshape(rgb.shape[:2]), hexes


def group_colors(
    rgb: np.ndarray,
    weights: np.ndarray,
    colors: int | None = None,
    palette: list[str] | None = None,
    iterations: int = 30,
    seed: int = 0,
) -> tuple[np.ndarray, list[str]]:
    """Group a list of colours, each with a weight (pixel count, area...), into a few.

    Same options as quantize(). Returns (group of each colour, hex_colours).
    """
    rgb = np.asarray(rgb, dtype=np.float64).reshape(-1, 3)
    weights = np.asarray(weights, dtype=np.float64).reshape(-1)
    lab = _lab(rgb)

    if palette is not None:
        if not palette:
            raise ValueError("palette is empty")
        pal_rgb = np.array([parse_color(c) for c in palette], dtype=np.uint8)
        return _nearest(lab, _lab(pal_rgb)), [to_hex(c) for c in pal_rgb]

    if colors is None or colors < 1:
        raise ValueError("give a palette or a number of colours >= 1")
    k = min(colors, len(rgb))
    centres = _kmeans(lab, weights, k, iterations, seed)
    nearest = _nearest(lab, centres)
    # Drop clusters that ended up empty and report each colour as the weighted mean of its members.
    used = np.unique(nearest)
    remap = np.full(k, -1)
    remap[used] = np.arange(len(used))
    nearest = remap[nearest]
    hexes = []
    for i in range(len(used)):
        w = weights * (nearest == i)
        hexes.append(to_hex((rgb * w[:, None]).sum(axis=0) / w.sum()))
    return nearest, hexes


def _lab(rgb: np.ndarray) -> np.ndarray:
    return rgb2lab(np.asarray(rgb, dtype=np.float64).reshape(-1, 1, 3) / 255.0).reshape(-1, 3)


def _nearest(points: np.ndarray, centres: np.ndarray, chunk: int = 100_000) -> np.ndarray:
    # Chunked so photos with millions of distinct colours do not need a huge distance matrix.
    out = np.empty(len(points), dtype=np.intp)
    for i in range(0, len(points), chunk):
        p = points[i:i + chunk]
        out[i:i + chunk] = ((p[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    return out


def _kmeans(points: np.ndarray, weights: np.ndarray, k: int, iterations: int, seed: int) -> np.ndarray:
    """Weighted k-means with k-means++ seeding; deterministic for a given seed."""
    rng = np.random.default_rng(seed)
    centres = [points[weights.argmax()]]   # start from the most common colour
    for _ in range(1, k):
        d = np.min([((points - c) ** 2).sum(axis=1) for c in centres], axis=0) * weights
        if d.sum() == 0:
            break
        centres.append(points[rng.choice(len(points), p=d / d.sum())])
    centres = np.array(centres)
    for _ in range(iterations):
        nearest = _nearest(points, centres)
        new = centres.copy()
        for i in range(len(centres)):
            w = weights * (nearest == i)
            if w.sum() > 0:
                new[i] = (points * w[:, None]).sum(axis=0) / w.sum()
        if np.allclose(new, centres):
            break
        centres = new
    return centres
