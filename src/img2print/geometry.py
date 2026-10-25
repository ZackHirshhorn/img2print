"""2D shape helpers and 2D -> 3D mesh operations."""

from __future__ import annotations

import warnings

import numpy as np
import shapely
import trimesh
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry


def as_polygons(geom: BaseGeometry) -> list[Polygon]:
    """Flatten a Polygon / MultiPolygon / GeometryCollection into its non-empty polygons."""
    if isinstance(geom, Polygon):
        polys = [geom]
    else:
        polys = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]
    return [p for p in polys if not p.is_empty]


def rounded_rect(width: float, height: float, radius: float = 0.0, quad_segs: int = 16) -> Polygon:
    """Rectangle from (0, 0) to (width, height); radius is clamped to fit."""
    r = min(radius, width / 2, height / 2)
    if r <= 0:
        return box(0, 0, width, height)
    return box(r, r, width - r, height - r).buffer(r, quad_segs=quad_segs)


def extrude(geom: BaseGeometry, height: float, z0: float = 0.0) -> trimesh.Trimesh | None:
    """Extrude a (Multi)Polygon into a mesh spanning z0 .. z0 + height. None if empty."""
    # Boolean operations can leave points a hair apart, which break the triangulation into open meshes.
    polys = [shapely.remove_repeated_points(p, 1e-6) for p in as_polygons(geom)]
    meshes = [_extrude_one(p, height) for p in polys if p.area > 0]
    if not meshes:
        return None
    m = trimesh.util.concatenate(meshes)
    m.apply_translation([0, 0, z0])
    return m


def _extrude_one(poly: Polygon, height: float) -> trimesh.Trimesh:
    mesh = trimesh.creation.extrude_polygon(poly, height)
    if mesh.is_volume:
        return mesh
    # The ear-cutting triangulation fails on some shapes (e.g. letters cut by the plate edge) and
    # leaves an edge shared by four faces; manifold's own triangulation always gives a closed solid.
    from manifold3d import CrossSection, FillRule
    rings = [np.asarray(r.coords)[:-1] for r in (poly.exterior, *poly.interiors)]
    m = CrossSection(rings, FillRule.EvenOdd).extrude(height).to_mesh()
    return trimesh.Trimesh(m.vert_properties[:, :3], m.tri_verts)


def union(*meshes: trimesh.Trimesh) -> trimesh.Trimesh:
    """Boolean union if an engine is available, otherwise a plain merge of shells."""
    meshes = [m for m in meshes if m is not None]
    if len(meshes) == 1:
        return meshes[0]
    try:
        return trimesh.boolean.union(meshes, engine="manifold")
    except Exception as e:
        warnings.warn(f"boolean union unavailable ({e}); merging shells instead")
        return trimesh.util.concatenate(meshes)


def difference(mesh: trimesh.Trimesh, *cutters: trimesh.Trimesh) -> trimesh.Trimesh:
    """mesh with the cutters cut away (needs the manifold boolean engine)."""
    cutters = [m for m in cutters if m is not None]
    if not cutters:
        return mesh
    return trimesh.boolean.difference([mesh, *cutters], engine="manifold")
