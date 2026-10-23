"""Request and response bodies of the web API. Settings itself is the library's dataclass."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..settings import Settings


class Swatch(BaseModel):
    color: str = Field(description="'#rrggbb'")
    name: str
    share: float = Field(description="fraction of the image, 0..1")


class Upload(BaseModel):
    id: str
    filename: str
    kind: Literal["raster", "svg", "pdf"]
    width: float = Field(description="natural width: pixels for raster images, document units for SVG / PDF")
    height: float
    pages: int
    colors: list[Swatch] = Field(description="main colours found, largest first")


class TraceRequest(BaseModel):
    upload_id: str
    settings: Settings = Field(default_factory=Settings)


class BuildRequest(TraceRequest):
    material: str = "PLA"


class Layer(BaseModel):
    name: str
    color: str
    area: float = Field(description="mm^2")
    path: str = Field(description="SVG path data in mm, y down, even-odd fill")


class Trace(BaseModel):
    width: float = Field(description="mm")
    height: float = Field(description="mm")
    layers: list[Layer] = Field(description="background first")


class PartStats(BaseModel):
    name: str
    color: str | None
    triangles: int
    watertight: bool
    volume: float = Field(description="mm^3")
    grams: float = Field(description="as a solid print")
    metres: float = Field(description="of 1.75 mm filament")
    stl_url: str


class BuiltModel(BaseModel):
    id: str
    size: tuple[float, float, float] = Field(description="x, y, z in mm")
    material: str
    parts: list[PartStats]
    trace: Trace
    glb_url: str
    threemf_url: str
    zip_url: str


class Preset(BaseModel):
    id: str
    name: str
    nozzle: float
    layer_height: float
    base: float
    layer: float


class Info(BaseModel):
    version: str
    pdf: bool = Field(description="whether PDF input is available")
    materials: list[str]
    presets: list[Preset]
    max_upload_mb: int
