"""Producer adapters for default-off canonical surface quality evidence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


@dataclass(frozen=True, slots=True)
class CanonicalSurfaceQualityInput:
    vertices: np.ndarray
    triangles: np.ndarray
    quads: np.ndarray
    triangle_reference_normals: tuple[tuple[float, float, float], ...] | None
    quad_reference_normals: tuple[tuple[float, float, float], ...] | None
    source_sha256: str
    output_sha256: str
    source_face_lineage: tuple[Any, ...]
    patch_ids: tuple[Any, ...]
    physical_groups: tuple[str, ...]
    feature_ids: tuple[Any, ...]
    source_authority: Mapping[str, Any]
    requested_layers: int = 0
    actual_layers: int = 0
    wall_edge_stack: Mapping[str, Any] | None = None


def _canonical_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return _canonical_value(value.tolist())
    if isinstance(value, tuple):
        return tuple(_canonical_value(item) for item in value)
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Mapping):
        return {
            _canonical_value(key): _canonical_value(item)
            for key, item in value.items()
        }
    return value


def _array(value: Any, dtype: Any, width: int) -> np.ndarray:
    array = np.ascontiguousarray(np.asarray(value, dtype=dtype))
    if array.ndim != 2 or array.shape[1] != width:
        raise ValueError("surface_array_shape")
    return array


def _authority(mapping: Mapping[str, Any] | None, *, ready: bool) -> dict[str, Any]:
    result = dict(mapping or {})
    result["authority_ready"] = bool(ready and result.get("authority_ready", True))
    return result


def from_native_tri_release(
    result: Any,
    *,
    source_authority: Mapping[str, Any] | None = None,
    source_sha256: str | None = None,
    output_sha256: str | None = None,
) -> CanonicalSurfaceQualityInput:
    if not getattr(result, "accepted", False):
        raise ValueError("native_tri_release_not_accepted")
    faces = _array(result.faces, np.int64, 3)
    provenance = tuple(
        _canonical_value(item) for item in getattr(result, "source_face_provenance", ())
    )
    patches = tuple(
        _canonical_value(item) for item in getattr(result, "output_patch_ids", ())
    )
    groups = tuple(
        _canonical_value(item) for item in getattr(result, "output_physical_groups", ())
    )
    if not (
        getattr(result, "output_topology_valid", False)
        and getattr(result, "source_provenance_authoritative", False)
        and len(provenance) == len(faces)
        and len(patches) == len(faces)
        and len(groups) == len(faces)
    ):
        raise ValueError("native_tri_surface_authority_incomplete")
    return CanonicalSurfaceQualityInput(
        vertices=_array(result.vertices, np.float64, 3),
        triangles=faces,
        quads=np.empty((0, 4), dtype=np.int64),
        triangle_reference_normals=None,
        quad_reference_normals=None,
        source_sha256=str(source_sha256 or getattr(result, "source_file_sha256", None) or result.source_vertices_sha256),
        output_sha256=str(output_sha256 or result.output_faces_sha256),
        source_face_lineage=provenance,
        patch_ids=patches,
        physical_groups=groups,
        feature_ids=tuple(range(len(faces))),
        source_authority=_authority(source_authority, ready=True),
    )


def from_strict_quad_fixed_pair(
    product: Any,
    *,
    source_authority: Mapping[str, Any] | None = None,
    source_sha256: str | None = None,
    output_sha256: str | None = None,
) -> CanonicalSurfaceQualityInput:
    quads = _array(product.quads, np.int64, 4)
    triangles = _array(product.triangles, np.int64, 3)
    if len(quads) == 0:
        raise ValueError("strict_quad_empty")
    patches = tuple(getattr(product, "quad_patch_ids", ()))
    groups = tuple(getattr(product, "quad_physical_groups", ()))
    if len(patches) != len(quads) or len(groups) != len(quads):
        raise ValueError("strict_quad_provenance_incomplete")
    return CanonicalSurfaceQualityInput(
        vertices=_array(product.vertices, np.float64, 3),
        triangles=triangles,
        quads=quads,
        triangle_reference_normals=None,
        quad_reference_normals=None,
        source_sha256=str(source_sha256 or product.source_vertices_hash),
        output_sha256=str(output_sha256 or product.quads_hash),
        source_face_lineage=tuple(
            _canonical_value(item) for item in getattr(product, "quad_source_pairs", ())
        ),
        patch_ids=tuple(_canonical_value(item) for item in patches),
        physical_groups=tuple(_canonical_value(item) for item in groups),
        feature_ids=tuple(range(len(quads))),
        source_authority=_authority(source_authority, ready=True),
    )


def from_tri_quad_fixed_pair(
    product: Any,
    *,
    source_authority: Mapping[str, Any] | None = None,
    source_sha256: str | None = None,
    output_sha256: str | None = None,
) -> CanonicalSurfaceQualityInput:
    triangles = _array(product.triangles, np.int64, 3)
    quads = _array(product.quads, np.int64, 4)
    tri_patches = tuple(
        _canonical_value(item) for item in getattr(product, "triangle_patch_ids", ())
    )
    quad_patches = tuple(
        _canonical_value(item) for item in getattr(product, "quad_patch_ids", ())
    )
    tri_groups = tuple(
        _canonical_value(item) for item in getattr(product, "triangle_physical_groups", ())
    )
    quad_groups = tuple(
        _canonical_value(item) for item in getattr(product, "quad_physical_groups", ())
    )
    if len(tri_patches) != len(triangles) or len(quad_patches) != len(quads):
        raise ValueError("tri_quad_provenance_incomplete")
    lineage = tuple(
        _canonical_value(item)
        for item in getattr(product, "triangle_source_indices", ())
    ) + tuple(
        _canonical_value(item)
        for item in getattr(product, "quad_source_pairs", ())
    )
    return CanonicalSurfaceQualityInput(
        vertices=_array(product.vertices, np.float64, 3),
        triangles=triangles,
        quads=quads,
        triangle_reference_normals=None,
        quad_reference_normals=None,
        source_sha256=str(source_sha256 or product.source_vertices_hash),
        output_sha256=str(output_sha256 or product.source_triangles_hash),
        source_face_lineage=lineage,
        patch_ids=tri_patches + quad_patches,
        physical_groups=tri_groups + quad_groups,
        feature_ids=tuple(range(len(lineage))),
        source_authority=_authority(source_authority, ready=True),
    )


__all__ = [
    "CanonicalSurfaceQualityInput",
    "from_native_tri_release",
    "from_strict_quad_fixed_pair",
    "from_tri_quad_fixed_pair",
]
