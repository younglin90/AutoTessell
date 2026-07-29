"""Deterministic, surface-only native triangle remeshing."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from core.preprocessor.native_remesh.isotropic import _detect_feature_verts, isotropic_remesh


@runtime_checkable
class SurfaceQualityPredictor(Protocol):
    """Optional sizing advisor. Model loading/inference stays with caller."""

    def predict(self, vertices: np.ndarray, faces: np.ndarray) -> Mapping[str, float]:
        """Return optional numeric hints such as ``target_edge_scale``."""


class SurfaceRemeshConfig(BaseModel):
    """Deterministic controls for :func:`native_face_remesh`."""

    target_edge_length: float | None = Field(default=None, gt=0.0)
    iterations: int = Field(default=3, ge=1, le=12)
    feature_angle_deg: float = Field(default=45.0, gt=0.0, lt=180.0)
    adaptive_sizing: bool = True
    feature_size_weight: float = Field(default=0.35, ge=0.0, le=0.9)
    max_geometry_drift: float | None = Field(default=None, gt=0.0)
    projection_candidates: int = Field(default=12, ge=1, le=64)
    protected_edges: tuple[tuple[int, int], ...] = ()
    min_triangle_quality: float = Field(default=0.0, ge=0.0, le=1.0)


class SurfaceRemeshDiagnostics(BaseModel):
    """Machine-readable surface acceptance-gate evidence."""

    input_vertices: int
    input_faces: int
    output_vertices: int
    output_faces: int
    target_edge_length: float | None = None
    feature_vertices: int = 0
    predictor_used: bool = False
    predictor_error: str | None = None
    watertight: bool = False
    manifold: bool = False
    degenerate_faces: int = 0
    flipped_faces: int = 0
    max_geometry_drift: float = float("inf")
    gates: dict[str, bool] = Field(default_factory=dict)
    protected_edges_preserved: bool = True
    protected_edges: int = 0
    min_triangle_quality: float = 0.0
    rejection_reason: str | None = None


class SurfaceRemeshResult(BaseModel):
    """Rejected results preserve original triangle surface arrays."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vertices: np.ndarray
    faces: np.ndarray
    accepted: bool
    diagnostics: SurfaceRemeshDiagnostics


def _edge_lengths(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    return (
        np.concatenate(
            (
                np.linalg.norm(vertices[faces[:, 1]] - vertices[faces[:, 0]], axis=1),
                np.linalg.norm(vertices[faces[:, 2]] - vertices[faces[:, 1]], axis=1),
                np.linalg.norm(vertices[faces[:, 0]] - vertices[faces[:, 2]], axis=1),
            )
        )
        if faces.size
        else np.empty(0, dtype=np.float64)
    )


def _edge_counts(faces: np.ndarray) -> Counter[tuple[int, int]]:
    counts: Counter[tuple[int, int]] = Counter()
    for tri in faces:
        for first, second in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            a, b = int(first), int(second)
            counts[(a, b) if a < b else (b, a)] += 1
    return counts


def _face_areas(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    if not faces.size:
        return np.empty(0, dtype=np.float64)
    tri = vertices[faces]
    return 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)


def _closest_point_triangle(point: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Ericson closest-point region tests."""
    a, b, c = tri
    ab, ac, ap = b - a, c - a, point - a
    d1, d2 = float(ab @ ap), float(ac @ ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a
    bp = point - b
    d3, d4 = float(ab @ bp), float(ac @ bp)
    if d3 >= 0.0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        return a + (d1 / (d1 - d3)) * ab
    cp = point - c
    d5, d6 = float(ab @ cp), float(ac @ cp)
    if d6 >= 0.0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        return a + (d2 / (d2 - d6)) * ac
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and d4 >= d3 and d5 >= d6:
        bc = c - b
        return b + ((d4 - d3) / ((d4 - d3) + (d5 - d6))) * bc
    denom = 1.0 / (va + vb + vc)
    return a + ab * (vb * denom) + ac * (vc * denom)


def _project_to_triangles(
    vertices: np.ndarray,
    reference_vertices: np.ndarray,
    reference_faces: np.ndarray,
    candidates: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project to nearby reference faces; return points, normals, drift."""
    triangles = reference_vertices[reference_faces]
    centers = triangles.mean(axis=1)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    norm = np.linalg.norm(normals, axis=1)
    normals = np.divide(
        normals, norm[:, None], out=np.zeros_like(normals), where=norm[:, None] > 1e-30
    )
    count = min(candidates, len(triangles))
    projected, hit_normals = np.empty_like(vertices), np.zeros_like(vertices)
    drift = np.empty(len(vertices), dtype=np.float64)
    for index, point in enumerate(vertices):
        center_dist2 = np.einsum("ij,ij->i", centers - point, centers - point)
        nearby = np.argpartition(center_dist2, count - 1)[:count]
        best_point: np.ndarray | None = None
        best_face, best_dist2 = -1, float("inf")
        for face_index in nearby:
            candidate = _closest_point_triangle(point, triangles[int(face_index)])
            candidate_dist2 = float(np.dot(candidate - point, candidate - point))
            if candidate_dist2 < best_dist2:
                best_point, best_face, best_dist2 = candidate, int(face_index), candidate_dist2
        assert best_point is not None
        projected[index], hit_normals[index], drift[index] = (
            best_point,
            normals[best_face],
            best_dist2**0.5,
        )
    return projected, hit_normals, drift


def _input_error(vertices: np.ndarray, faces: np.ndarray) -> str | None:
    if vertices.ndim != 2 or vertices.shape[1] != 3:
        return "vertices must have shape (N, 3)"
    if faces.ndim != 2 or faces.shape[1] != 3:
        return "faces must have shape (M, 3)"
    if len(vertices) == 0 or len(faces) < 4:
        return "surface needs vertices and at least four triangles"
    if not np.isfinite(vertices).all() or (faces < 0).any() or (faces >= len(vertices)).any():
        return "surface contains non-finite vertices or invalid face indices"
    return None


def _rejected(
    vertices: np.ndarray, faces: np.ndarray, diagnostic: SurfaceRemeshDiagnostics, reason: str
) -> SurfaceRemeshResult:
    diagnostic.rejection_reason = reason
    return SurfaceRemeshResult(
        vertices=vertices, faces=faces, accepted=False, diagnostics=diagnostic
    )


def native_face_remesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    config: SurfaceRemeshConfig | None = None,
    predictor: SurfaceQualityPredictor | None = None,
) -> SurfaceRemeshResult:
    """Closed-triangle surface remesh. Never calls volume engines or external meshing."""
    settings = config or SurfaceRemeshConfig()
    original_vertices = np.asarray(vertices, dtype=np.float64).copy()
    original_faces = np.asarray(faces, dtype=np.int64).copy()
    diagnostic = SurfaceRemeshDiagnostics(
        input_vertices=len(original_vertices),
        input_faces=len(original_faces),
        output_vertices=len(original_vertices),
        output_faces=len(original_faces),
    )
    if error := _input_error(original_vertices, original_faces):
        return _rejected(original_vertices, original_faces, diagnostic, error)
    input_counts = _edge_counts(original_faces)
    bbox_diag = float(np.linalg.norm(original_vertices.max(axis=0) - original_vertices.min(axis=0)))
    area_floor = max(bbox_diag * bbox_diag * 1e-14, 1e-30)
    if not all(count == 2 for count in input_counts.values()) or not np.all(
        _face_areas(original_vertices, original_faces) > area_floor
    ):
        return _rejected(
            original_vertices,
            original_faces,
            diagnostic,
            "input must be watertight manifold with no degenerate triangles",
        )
    base_target = settings.target_edge_length or float(
        np.median(_edge_lengths(original_vertices, original_faces))
    )
    drift_limit = settings.max_geometry_drift or max(0.05 * bbox_diag, 1e-12)
    quality_limit = float(settings.min_triangle_quality)

    feature_vertices = _detect_feature_verts(
        original_vertices, original_faces, settings.feature_angle_deg
    )
    diagnostic.feature_vertices = len(feature_vertices)
    if settings.adaptive_sizing:
        base_target *= max(
            0.1, 1.0 - settings.feature_size_weight * len(feature_vertices) / len(original_vertices)
        )
    if predictor is not None:
        try:
            scale = float(
                predictor.predict(original_vertices.copy(), original_faces.copy()).get(
                    "target_edge_scale", 1.0
                )
            )
            if np.isfinite(scale) and 0.1 <= scale <= 4.0:
                base_target *= scale
                diagnostic.predictor_used = True
            else:
                diagnostic.predictor_error = "ignored invalid target_edge_scale"
        except Exception as exc:
            diagnostic.predictor_error = f"predictor failed: {type(exc).__name__}"
    diagnostic.target_edge_length = float(base_target)
    protected_edges = frozenset((min(int(a), int(b)), max(int(a), int(b))) for a, b in settings.protected_edges)
    if any(a == b or a < 0 or b >= len(original_vertices) or edge not in input_counts for a, b in protected_edges for edge in ((a, b),)):
        return _rejected(original_vertices, original_faces, diagnostic, "protected_edges must reference distinct input surface edges")
    diagnostic.protected_edges = len(protected_edges)
    try:
        remeshed_vertices, remeshed_faces = isotropic_remesh(
            original_vertices, original_faces, target_edge_length=float(base_target),
            n_iter=settings.iterations, project_to_surface=False,
            feature_angle_deg=settings.feature_angle_deg, lock_features=True,
            valence_constraint=True, protected_edges=protected_edges,
        )
        remeshed_vertices, _, _ = _project_to_triangles(
            remeshed_vertices, original_vertices, original_faces, settings.projection_candidates
        )
    except Exception as exc:
        return _rejected(
            original_vertices,
            original_faces,
            diagnostic,
            f"native operation failed: {type(exc).__name__}",
        )
    diagnostic.output_vertices, diagnostic.output_faces = len(remeshed_vertices), len(
        remeshed_faces
    )
    output_counts = _edge_counts(remeshed_faces)
    output_areas = _face_areas(remeshed_vertices, remeshed_faces)
    watertight = bool(output_counts) and all(count == 2 for count in output_counts.values())
    manifold = all(count <= 2 for count in output_counts.values())
    degenerate = int(np.count_nonzero(output_areas <= area_floor))
    normals = (
        np.cross(
            remeshed_vertices[remeshed_faces[:, 1]] - remeshed_vertices[remeshed_faces[:, 0]],
            remeshed_vertices[remeshed_faces[:, 2]] - remeshed_vertices[remeshed_faces[:, 0]],
        )
        if len(remeshed_faces)
        else np.empty((0, 3))
    )
    centers = (
        remeshed_vertices[remeshed_faces].mean(axis=1) if len(remeshed_faces) else np.empty((0, 3))
    )
    _, reference_normals, face_drift = (
        _project_to_triangles(
            centers, original_vertices, original_faces, settings.projection_candidates
        )
        if len(centers)
        else (centers, centers, np.empty(0))
    )
    _, _, vertex_drift = _project_to_triangles(
        remeshed_vertices, original_vertices, original_faces, settings.projection_candidates
    )
    normal_sizes = np.linalg.norm(normals, axis=1)
    flipped = int(
        np.count_nonzero(np.einsum("ij,ij->i", normals, reference_normals) <= normal_sizes * 1e-12)
    )
    edge_squared = np.sum((remeshed_vertices[remeshed_faces[:, 1]] - remeshed_vertices[remeshed_faces[:, 0]]) ** 2, axis=1) + np.sum((remeshed_vertices[remeshed_faces[:, 2]] - remeshed_vertices[remeshed_faces[:, 1]]) ** 2, axis=1) + np.sum((remeshed_vertices[remeshed_faces[:, 0]] - remeshed_vertices[remeshed_faces[:, 2]]) ** 2, axis=1)
    qualities = np.divide(4.0 * np.sqrt(3.0) * output_areas, edge_squared, out=np.zeros_like(output_areas), where=edge_squared > 1e-30)
    min_quality = float(qualities.min()) if len(qualities) else 0.0
    protected_preserved = all(output_counts.get(edge, 0) == 2 for edge in protected_edges)
    diagnostic.watertight = watertight
    diagnostic.manifold = manifold
    diagnostic.protected_edges_preserved = protected_preserved
    diagnostic.min_triangle_quality = min_quality
    max_drift = float(max(vertex_drift.max(initial=0.0), face_drift.max(initial=0.0)))
    diagnostic.degenerate_faces, diagnostic.flipped_faces, diagnostic.max_geometry_drift = (
        degenerate,
        flipped,
        max_drift,
    )
    diagnostic.gates = {
        "watertight": watertight,
        "manifold": manifold,
        "no_degenerate_faces": degenerate == 0,
        "no_face_flips": flipped == 0,
        "geometry_drift": max_drift <= drift_limit,
        "protected_edges": protected_preserved,
        "triangle_quality": min_quality >= quality_limit,
    }
    if not all(diagnostic.gates.values()):
        failed = ", ".join(name for name, passed in diagnostic.gates.items() if not passed)
        return _rejected(original_vertices, original_faces, diagnostic, f"failed gates: {failed}")
    return SurfaceRemeshResult(
        vertices=remeshed_vertices, faces=remeshed_faces, accepted=True, diagnostics=diagnostic
    )
