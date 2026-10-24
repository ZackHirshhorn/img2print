"""HTTP routes: upload an image, trace it for a 2D preview, build the model, download files."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from PIL import Image

from .. import __version__
from ..colors import parse_color, to_hex, unique_names
from ..geometry import as_polygons
from ..image import group_colors, load_rgb, open_image
from ..model import DENSITY, Model
from ..pipeline import INK, PAPER, build_model, trace_layers
from ..settings import Settings
from ..trace import Artwork
from ..vector import load_vector, vector_kind
from .cache import Cache
from .schemas import (BuildRequest, BuiltModel, FilamentChange, Info, Layer, PartStats, Swatch, Trace,
                      TraceRequest, Upload)

MAX_UPLOAD_MB = 25
MAX_PIXELS = 40_000_000       # larger raster images are refused (decompression bombs)
MAX_SIDE = 2000               # raster uploads are shrunk to this longest side, to bound build memory
MAX_BUILDS = 2                # builds running at once
BUILD_TIMEOUT = 120.0         # seconds

# Options that only change the plate, not the tracing: builds that differ only in these reuse the trace.
PLATE_OPTIONS = {"stacking", "base", "layer", "thickness", "base_color", "corner_radius", "raised"}

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass
class Source:
    data: bytes
    filename: str
    kind: str

    @property
    def stem(self) -> str:
        return Path(self.filename).stem or "model"


@dataclass
class Built:
    model: Model
    stem: str
    files: dict[str, bytes] = field(default_factory=dict)

    def file(self, key: str, make) -> bytes:
        if key not in self.files:
            self.files[key] = make()
        return self.files[key]


uploads = Cache(max_bytes=200 * 2**20)
traces = Cache(max_bytes=100 * 2**20)
models = Cache(max_bytes=300 * 2**20)
_builds = asyncio.Semaphore(MAX_BUILDS)

router = APIRouter(prefix="/api")


@router.get("/info", response_model=Info)
def info() -> Info:
    return Info(version=__version__, pdf=_has_pdf(), materials=list(DENSITY), max_upload_mb=MAX_UPLOAD_MB)


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.post("/uploads", response_model=Upload)
async def upload(file: UploadFile = File(...)) -> Upload:
    data = await file.read(MAX_UPLOAD_MB * 2**20 + 1)
    if len(data) > MAX_UPLOAD_MB * 2**20:
        raise HTTPException(413, f"file is larger than {MAX_UPLOAD_MB} MB")
    if not data:
        raise HTTPException(422, "the file is empty")
    source = Source(data, file.filename or "model", vector_kind(data) or "raster")
    if source.kind == "raster":
        source.data = await _run(_downscale, data)
    result = await _run(_analyze, source)
    uploads.put(result.id, source, len(source.data))
    return result


@router.post("/trace", response_model=Trace)
async def trace(req: TraceRequest) -> Trace:
    source = _source(req.upload_id)
    layers = await _run(_layers, req.upload_id, source, req.settings)
    return _trace_body(layers, req.settings)


@router.post("/models", response_model=BuiltModel)
async def build(req: BuildRequest) -> BuiltModel:
    if req.material not in DENSITY:
        raise HTTPException(422, f"unknown material {req.material!r}; choose from {', '.join(DENSITY)}")
    source = _source(req.upload_id)

    def work():
        layers = _layers(req.upload_id, source, req.settings)
        return build_model(layers, req.settings), layers

    async with _builds:
        model, layers = await _run(work, timeout=BUILD_TIMEOUT)
    model_id = uuid.uuid4().hex
    models.put(model_id, Built(model, source.stem), _model_bytes(model))

    base = f"/api/models/{model_id}"
    (x0, y0, z0), (x1, y1, z1) = model.bounds
    return BuiltModel(
        id=model_id,
        size=(x1 - x0, y1 - y0, z1 - z0),
        material=req.material,
        parts=[PartStats(**s, stl_url=f"{base}/parts/{quote(s['name'])}.stl") for s in model.stats(req.material)],
        filament_changes=[FilamentChange(height=z, name=name, color=model[name].color)
                          for z, name in model.filament_changes],
        trace=_trace_body(layers, req.settings),
        glb_url=f"{base}/preview.glb",
        threemf_url=f"{base}/model.3mf",
        zip_url=f"{base}/bundle.zip",
    )


@router.get("/models/{model_id}/preview.glb")
def preview(model_id: str) -> Response:
    built = _built(model_id)
    return Response(built.file("glb", built.model.to_glb), media_type="model/gltf-binary")


@router.get("/models/{model_id}/model.3mf")
def threemf(model_id: str) -> Response:
    built = _built(model_id)
    return _download(built.file("3mf", built.model.to_3mf), f"{built.stem}.3mf", "model/3mf")


@router.get("/models/{model_id}/parts/{name}.stl")
def stl(model_id: str, name: str) -> Response:
    built = _built(model_id)
    try:
        part = built.model[name]
    except KeyError:
        raise HTTPException(404, f"no part named {name!r}") from None
    return _download(built.file(f"stl:{name}", part.to_stl), f"{built.stem}_{name}.stl", "model/stl")


@router.get("/models/{model_id}/bundle.zip")
def bundle(model_id: str) -> Response:
    built = _built(model_id)

    def make() -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"{built.stem}.3mf", built.file("3mf", built.model.to_3mf))
            for p in built.model:
                z.writestr(f"{built.stem}_{p.name}.stl", built.file(f"stl:{p.name}", p.to_stl))
        return buf.getvalue()

    return _download(built.file("zip", make), f"{built.stem}.zip", "application/zip")


# --- helpers -------------------------------------------------------------------------------------

async def _run(fn, *args, timeout: float | None = None):
    """Run library code off the event loop; its errors become readable HTTP errors."""
    try:
        return await asyncio.wait_for(run_in_threadpool(fn, *args), timeout)
    except asyncio.TimeoutError:
        raise HTTPException(504, "this took too long; try a smaller size, fewer colours or a simpler image") from None
    except Image.DecompressionBombError:
        raise HTTPException(413, f"the image has too many pixels (limit {MAX_PIXELS // 1_000_000} megapixels)") from None
    except (ValueError, ImportError) as e:
        raise HTTPException(422, str(e)) from None
    except OSError as e:   # PIL: not an image it can read
        raise HTTPException(422, f"could not read the file as an image, SVG or PDF ({e})") from None


def _source(upload_id: str) -> Source:
    source = uploads.get(upload_id)
    if source is None:
        raise HTTPException(404, "upload not found or expired; please upload the file again")
    return source


def _built(model_id: str) -> Built:
    built = models.get(model_id)
    if built is None:
        raise HTTPException(404, "model not found or expired; please build it again")
    return built


def _layers(upload_id: str, source: Source, settings: Settings) -> list[Artwork]:
    trace_settings = {k: v for k, v in settings.to_dict().items() if k not in PLATE_OPTIONS}
    key = upload_id + json.dumps(trace_settings, sort_keys=True)
    layers = traces.get(key)
    if layers is None:
        layers = trace_layers(source.data, settings)
        size = sum(len(p.exterior.coords) + sum(len(r.coords) for r in p.interiors)
                   for a in layers for p in as_polygons(a.geometry))
        traces.put(key, layers, 64 * size + 1024)
    return layers


def _downscale(data: bytes) -> bytes:
    """Shrink a raster image to MAX_SIDE on its longest side, as PNG; small images are kept as they are.
    A print cannot show more detail than this, and full-size phone photos run the server out of memory."""
    im = open_image(data)
    if max(im.size) <= MAX_SIDE:
        return data
    if im.mode not in ("RGB", "RGBA", "L", "LA"):
        im = im.convert("RGBA")   # palette images would otherwise be resized without smoothing
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _analyze(source: Source) -> Upload:
    data = source.data
    pages = 1
    if source.kind == "raster":
        im = open_image(data)
        im.load()
        width, height = im.size
        thumb = im.copy()
        thumb.thumbnail((200, 200))
        rgb = load_rgb(thumb)
        uniq, counts = np.unique(rgb.reshape(-1, 3), axis=0, return_counts=True)
        groups, hexes = group_colors(uniq, counts, colors=8)
        shares = np.bincount(groups, weights=counts, minlength=len(hexes)) / counts.sum()
    else:
        if source.kind == "pdf":
            pages = _pdf_pages(data)
        art = load_vector(data)
        width, height = art.width, art.height
        visible = art.visible()
        areas = np.array([g.area for _, g in visible])
        groups, hexes = group_colors([parse_color(c) for c, _ in visible], areas, colors=min(8, len(visible)))
        shares = np.bincount(groups, weights=areas, minlength=len(hexes)) / areas.sum()
    order = np.argsort(-shares)
    names = unique_names([hexes[i] for i in order])
    colors = [Swatch(color=hexes[i], name=n, share=float(shares[i]))
              for i, n in zip(order, names) if shares[i] >= 0.01]   # skip anti-aliasing shades
    return Upload(id=hashlib.sha256(data).hexdigest()[:24], filename=source.filename, kind=source.kind,
                  width=float(width), height=float(height), pages=pages, colors=colors)


def _trace_body(layers: list[Artwork], settings: Settings) -> Trace:
    if settings.color_mode:
        names = unique_names([a.color or "#808080" for a in layers])
    else:
        names = [PAPER[0], INK[0]]
    w, h = layers[0].width, layers[0].height
    return Trace(width=w, height=h, layers=[
        Layer(name=n, color=to_hex(parse_color(a.color or "#808080")), area=a.area, path=svg_path(a, h))
        for n, a in zip(names, layers)])


def svg_path(art: Artwork, height: float) -> str:
    """Shapely geometry in mm (y up) as SVG path data (y down); fill it with fill-rule evenodd."""
    out = []
    for poly in as_polygons(art.geometry):
        for ring in (poly.exterior, *poly.interiors):
            pts = np.asarray(ring.coords)[:-1]
            if len(pts) < 3:
                continue
            out.append("M" + " ".join(f"{x:.2f},{height - y:.2f}" for x, y in pts) + "Z")
    return "".join(out)


def _model_bytes(model: Model) -> int:
    # Meshes plus the export files made from them later.
    return sum(p.mesh.vertices.nbytes + p.mesh.faces.nbytes for p in model) * 4


def _download(data: bytes, filename: str, media_type: str) -> Response:
    # Plain ASCII name for old clients, the real (possibly Hebrew) name in filename*.
    fallback = re.sub(r'[^A-Za-z0-9._-]', "_", filename.encode("ascii", "replace").decode())
    return Response(data, media_type=media_type, headers={
        "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"})


def _has_pdf() -> bool:
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        return False
    return True


def _pdf_pages(data: bytes) -> int:
    try:
        import pymupdf
    except ImportError:
        raise ImportError("PDF input needs PyMuPDF on the server: pip install img2print[pdf]") from None
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return len(doc)
