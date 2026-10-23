"""Multi-part printable models and their export to STL / 3MF."""

from __future__ import annotations

from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path

import numpy as np
import trimesh

# Filament for the estimates: g/cm^3 per material, and filament diameter in mm.
DENSITY = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "TPU": 1.21}
FILAMENT_DIAMETER = 1.75


@dataclass
class Part:
    """One single-material body of a model."""

    name: str
    mesh: trimesh.Trimesh
    color: str | None = None  # "#rrggbb", used as the display colour in the 3MF

    def to_stl(self) -> bytes:
        return self.mesh.export(file_type="stl")


@dataclass
class Model:
    """A set of parts that print together, one filament per part."""

    parts: list[Part] = field(default_factory=list)

    def __getitem__(self, name: str) -> Part:
        for p in self.parts:
            if p.name == name:
                return p
        raise KeyError(name)

    def __iter__(self):
        return iter(self.parts)

    @property
    def bounds(self) -> np.ndarray:
        return np.array(trimesh.util.concatenate([p.mesh for p in self.parts]).bounds)

    def flip_face_down(self) -> "Model":
        """Rotate 180 deg about X so the top face lands on the build plate.

        The design still reads correctly when the print is viewed from below.
        Modifies the model in place and returns it.
        """
        (_, ymin, zmin), (_, ymax, zmax) = self.bounds
        flip = trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
        for p in self.parts:
            p.mesh.apply_transform(flip)
            p.mesh.apply_translation([0, ymin + ymax, zmin + zmax])
        return self

    def to_scene(self) -> trimesh.Scene:
        scene = trimesh.Scene()
        for p in self.parts:
            mesh = p.mesh
            if p.color:
                mesh = mesh.copy()
                mesh.visual.face_colors = _hex_to_rgba(p.color)
            scene.add_geometry(mesh, node_name=p.name, geom_name=p.name)
        return scene

    def to_glb(self) -> bytes:
        """All parts in one binary glTF with their colours, for a web 3D viewer."""
        return self.to_scene().export(file_type="glb")

    def to_3mf(self) -> bytes:
        """All parts in one 3MF: load as one multi-part object and assign a filament per part."""
        return self.to_scene().export(file_type="3mf")

    def export(self, prefix: str | PathLike, stl: bool = True, threemf: bool = True) -> list[Path]:
        """Write <prefix>_<part>.stl for each part and <prefix>.3mf. Returns the written paths."""
        prefix = Path(prefix)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        written = []
        if stl:
            for p in self.parts:
                path = prefix.with_name(f"{prefix.name}_{p.name}.stl")
                path.write_bytes(p.to_stl())
                written.append(path)
        if threemf:
            path = prefix.with_name(f"{prefix.name}.3mf")
            path.write_bytes(self.to_3mf())
            written.append(path)
        return written

    def stats(self, material: str = "PLA", diameter: float = FILAMENT_DIAMETER) -> list[dict]:
        """Per part: name, colour, triangles, watertight, volume (mm^3) and the filament it
        needs as a solid print (grams and metres). Infill makes real prints lighter."""
        density = DENSITY[material]
        section = np.pi * (diameter / 2) ** 2
        out = []
        for p in self.parts:
            m = p.mesh
            volume = float(m.volume)
            out.append(dict(name=p.name, color=p.color, triangles=len(m.faces),
                            watertight=bool(m.is_watertight), volume=volume,
                            grams=volume / 1000 * density, metres=volume / section / 1000))
        return out

    def summary(self) -> str:
        return "\n".join(f"{s['name']}: {s['triangles']} triangles, watertight={s['watertight']}, "
                         f"volume={s['volume']:.0f} mm^3" for s in self.stats())


def _hex_to_rgba(color: str) -> list[int]:
    c = color.lstrip("#")
    return [int(c[i:i + 2], 16) for i in (0, 2, 4)] + [255]
