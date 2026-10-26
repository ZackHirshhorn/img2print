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


class TextShape(BaseModel):
    path: str = Field(description="SVG path data in mm, y down, even-odd fill; empty when the text is empty")
    error: str | None = Field(None, description="why the text could not be drawn, e.g. an unknown font")
    thin: float = Field(0.0, description="share of the text in strokes thinner than a 0.4 mm nozzle, 0..1")


class Trace(BaseModel):
    width: float = Field(description="mm")
    height: float = Field(description="mm")
    layers: list[Layer] = Field(description="background first")
    texts: list[TextShape] = Field(default_factory=list, description="one per settings.texts, in the same order")


class PartStats(BaseModel):
    name: str
    color: str | None
    triangles: int
    watertight: bool
    volume: float = Field(description="mm^3")
    grams: float = Field(description="as a solid print")
    metres: float = Field(description="of 1.75 mm filament")
    stl_url: str


class FilamentChange(BaseModel):
    height: float = Field(description="mm from the bed, where this part's filament starts")
    name: str
    color: str | None


class BuiltModel(BaseModel):
    id: str
    size: tuple[float, float, float] = Field(description="x, y, z in mm")
    material: str
    parts: list[PartStats]
    filament_changes: list[FilamentChange] = Field(description="colour by layer only, lowest first")
    trace: Trace
    glb_url: str
    threemf_url: str
    zip_url: str


class Font(BaseModel):
    family: str
    variants: list[str] = Field(description="'400', '700', '400i' (weight, i for italic)")
    source: Literal["bundled", "local", "google"]
    category: str
    subsets: list[str] = Field(description="scripts covered, e.g. hebrew, latin")
    popularity: int = Field(description="Google's rank, lower is more popular; 0 for other fonts")


class Info(BaseModel):
    version: str
    pdf: bool = Field(description="whether PDF input is available")
    materials: list[str]
    max_upload_mb: int
