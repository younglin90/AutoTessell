"""K2 / beta2634 — surface mesh diagnostic 도구.

face normal consistency / dihedral distribution / sliver detection.
입력 surface mesh 의 quality 분석 (volume mesh 시작 전 사전 점검).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        surface_diag_stats_batch as _c_surface_diag_stats_batch,
    )
except Exception:  # pragma: no cover - optional native extension
    _c_surface_diag_stats_batch = None


@dataclass
class SurfaceDiagResult:
    """surface mesh diagnostic 결과."""

    n_vertices: int = 0
    n_faces: int = 0
    n_inconsistent_normals: int = 0
    n_sliver_faces: int = 0          # area < 1e-12.
    n_dihedral_sharp: int = 0        # > feature_angle (default 30°).
    dihedral_min_deg: float = 0.0
    dihedral_max_deg: float = 0.0
    dihedral_mean_deg: float = 0.0
    face_area_min: float = 0.0
    face_area_max: float = 0.0
    aspect_ratio_max: float = 0.0    # max edge / min edge per face.
    elapsed_s: float = 0.0
    warnings: list[str] = field(default_factory=list)


def diagnose_surface(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    feature_angle_deg: float = 30.0,
    sliver_area_tol: float = 1e-12,
) -> SurfaceDiagResult:
    """Surface mesh 종합 diagnostic.

    Args:
        V: (N, 3) vertex coordinates.
        F: (M, 3) triangle indices.
        feature_angle_deg: dihedral threshold for "sharp".
        sliver_area_tol: face area below = sliver.
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_v = int(V.shape[0])
    n_f = int(F.shape[0])

    if n_f == 0:
        return SurfaceDiagResult(
            n_vertices=n_v, n_faces=0,
            elapsed_s=time.perf_counter() - t0,
            warnings=["empty face array"],
        )

    if _c_surface_diag_stats_batch is not None:
        cos_thresh = float(np.cos(np.deg2rad(feature_angle_deg)))
        native = _c_surface_diag_stats_batch(V, F, cos_thresh, sliver_area_tol)
        if native is not None:
            counts, stats = native
            n_inconsistent, n_sliver, n_sharp, _n_dihedral_pairs = counts
            (
                dihedral_min,
                dihedral_max,
                dihedral_mean,
                face_area_min,
                face_area_max,
                aspect_max,
            ) = stats
            warnings: list[str] = []
            if n_sliver > 0:
                warnings.append(f"sliver faces: {n_sliver}/{n_f}")
            if n_inconsistent > 0:
                warnings.append(f"inconsistent normals: {n_inconsistent} edge pairs")
            if aspect_max > 100:
                warnings.append(f"high face aspect: max={aspect_max:.1f}")
            if n_sharp > n_f * 0.5:
                warnings.append(f"many sharp edges: {n_sharp}/{n_f} > 50% (CAD-like)")
            return SurfaceDiagResult(
                n_vertices=n_v,
                n_faces=n_f,
                n_inconsistent_normals=int(n_inconsistent),
                n_sliver_faces=int(n_sliver),
                n_dihedral_sharp=int(n_sharp),
                dihedral_min_deg=float(dihedral_min),
                dihedral_max_deg=float(dihedral_max),
                dihedral_mean_deg=float(dihedral_mean),
                face_area_min=float(face_area_min),
                face_area_max=float(face_area_max),
                aspect_ratio_max=float(aspect_max),
                elapsed_s=time.perf_counter() - t0,
                warnings=warnings,
            )

    # face normals + areas.
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    n_unnorm = np.cross(e1, e2)
    n_lens = np.linalg.norm(n_unnorm, axis=1)
    face_areas = 0.5 * n_lens
    n_sliver = int((face_areas < sliver_area_tol).sum())

    # face aspect ratio.
    edge_a = np.linalg.norm(e1, axis=1)
    edge_b = np.linalg.norm(e2, axis=1)
    edge_c = np.linalg.norm(V[F[:, 2]] - V[F[:, 1]], axis=1)
    edges = np.stack([edge_a, edge_b, edge_c], axis=1)
    e_min = edges.min(axis=1)
    e_max = edges.max(axis=1)
    aspect = e_max / np.maximum(e_min, 1e-30)
    aspect_max = float(aspect.max()) if aspect.size > 0 else 0.0

    # normalize normals for dihedral.
    safe_n = np.where(n_lens[:, None] > 1e-30, n_unnorm / np.maximum(n_lens[:, None], 1e-30), 0.0)

    # edge → face adjacency 계산 (dihedral).
    n_inconsistent = 0
    cos_thresh = float(np.cos(np.deg2rad(feature_angle_deg)))
    edges_per_face = np.stack([
        F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]],
    ], axis=1).reshape(-1, 2)
    edges_canon = np.sort(edges_per_face, axis=1)
    face_ids = np.arange(n_f, dtype=np.int64).repeat(3)
    ord_idx = np.lexsort((edges_canon[:, 1], edges_canon[:, 0]))
    sorted_edges = edges_canon[ord_idx]
    sorted_faces = face_ids[ord_idx]
    eq_prev = (
        np.diff(sorted_edges[:, 0]) != 0
    ) | (
        np.diff(sorted_edges[:, 1]) != 0
    )
    run_starts = np.concatenate(([0], np.where(eq_prev)[0] + 1))
    run_ends = np.concatenate((run_starts[1:], [len(sorted_edges)]))

    dihedral_cosines: list[float] = []
    for s, e in zip(run_starts.tolist(), run_ends.tolist()):
        fl = sorted_faces[s:e].tolist()
        if len(fl) == 2:
            cos_a = float(np.clip(np.dot(safe_n[fl[0]], safe_n[fl[1]]), -1.0, 1.0))
            dihedral_cosines.append(cos_a)
            if cos_a < -0.9:
                # 거의 anti-parallel (face winding 반대).
                n_inconsistent += 1

    if dihedral_cosines:
        dh = np.asarray(dihedral_cosines)
        dh_deg = np.rad2deg(np.arccos(dh))
        dihedral_min = float(dh_deg.min())
        dihedral_max = float(dh_deg.max())
        dihedral_mean = float(dh_deg.mean())
        n_sharp = int((dh < cos_thresh).sum())
    else:
        dihedral_min = dihedral_max = dihedral_mean = 0.0
        n_sharp = 0

    warnings: list[str] = []
    if n_sliver > 0:
        warnings.append(f"sliver faces: {n_sliver}/{n_f}")
    if n_inconsistent > 0:
        warnings.append(f"inconsistent normals: {n_inconsistent} edge pairs")
    if aspect_max > 100:
        warnings.append(f"high face aspect: max={aspect_max:.1f}")
    if n_sharp > n_f * 0.5:
        warnings.append(f"many sharp edges: {n_sharp}/{n_f} > 50% (CAD-like)")

    return SurfaceDiagResult(
        n_vertices=n_v, n_faces=n_f,
        n_inconsistent_normals=n_inconsistent,
        n_sliver_faces=n_sliver,
        n_dihedral_sharp=n_sharp,
        dihedral_min_deg=dihedral_min,
        dihedral_max_deg=dihedral_max,
        dihedral_mean_deg=dihedral_mean,
        face_area_min=float(face_areas.min()) if n_f > 0 else 0.0,
        face_area_max=float(face_areas.max()) if n_f > 0 else 0.0,
        aspect_ratio_max=aspect_max,
        elapsed_s=time.perf_counter() - t0,
        warnings=warnings,
    )
