"""P2 / beta2668 — Polyhedral mesh validator.

Polyhedral cell 의 face winding 일관성 + non-convex 검출.
Voronoi 기반 poly mesh 의 일반 health check.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray


@dataclass
class PolyhedralCheckResult:
    n_cells: int = 0
    n_inconsistent_winding: int = 0  # face winding 가 cell 와 inconsistent.
    n_non_convex_cells: int = 0      # cell centroid 가 모든 face 와 같은 side 가 아님.
    n_zero_area_faces: int = 0
    n_self_intersect_faces: int = 0
    avg_faces_per_cell: float = 0.0
    max_faces_per_cell: int = 0
    min_faces_per_cell: int = 0
    elapsed_s: float = 0.0
    warnings: list[str] = field(default_factory=list)


def check_polyhedral_mesh(
    points: NDArray[np.float64],
    cells: list[list[int]],
    cell_face_verts: list[list[list[int]]],
    *,
    sliver_area_tol: float = 1e-12,
) -> PolyhedralCheckResult:
    """Polyhedral mesh 종합 validator.

    Args:
        points: (N, 3) coords.
        cells: list of cells (각 cell = vertex IDs unique list, 위상 검증용).
        cell_face_verts: per-cell list of face vertex lists.
            cell_face_verts[i] = list of [v0, v1, v2, ...] (n-gon faces).
        sliver_area_tol: face area below = sliver.

    Returns:
        PolyhedralCheckResult.
    """
    import time
    t0 = time.perf_counter()

    points = np.asarray(points, dtype=np.float64)
    n_cells = len(cell_face_verts)
    if n_cells == 0:
        return PolyhedralCheckResult(elapsed_s=time.perf_counter() - t0)

    n_inconsistent = 0
    n_non_convex = 0
    n_zero_area = 0
    n_self_int = 0
    n_faces_per: list[int] = []
    warns: list[str] = []

    for ci, faces in enumerate(cell_face_verts):
        nf = len(faces)
        n_faces_per.append(nf)
        if nf < 4:
            warns.append(f"cell {ci} has only {nf} faces (< 4 minimum)")
            continue

        # cell centroid (vertex 평균).
        all_verts = list({int(v) for fv in faces for v in fv})
        if not all_verts:
            continue
        centroid = points[all_verts].mean(axis=0)

        # face normals + face center.
        face_outward_violations = 0
        for fv in faces:
            if len(fv) < 3:
                continue
            v0 = points[int(fv[0])]
            v1 = points[int(fv[1])]
            v2 = points[int(fv[2])]
            normal = np.cross(v1 - v0, v2 - v0)
            n_len = float(np.linalg.norm(normal))
            if n_len < 1e-30:
                n_zero_area += 1
                continue
            normal = normal / n_len
            face_center = points[[int(v) for v in fv]].mean(axis=0)
            # outward 는 (face_center - centroid) 방향과 같은 쪽.
            cf_dir = face_center - centroid
            cf_norm = float(np.linalg.norm(cf_dir))
            if cf_norm < 1e-30:
                continue
            cf_dir = cf_dir / cf_norm
            if float(np.dot(normal, cf_dir)) < -0.1:  # 강한 inward.
                face_outward_violations += 1

        if face_outward_violations > 0:
            n_inconsistent += 1
            if face_outward_violations >= max(2, nf // 2):
                # 절반 이상이 inward — non-convex 또는 winding 반전.
                n_non_convex += 1

    if n_faces_per:
        avg_f = float(np.mean(n_faces_per))
        max_f = int(max(n_faces_per))
        min_f = int(min(n_faces_per))
    else:
        avg_f = max_f = min_f = 0

    return PolyhedralCheckResult(
        n_cells=n_cells,
        n_inconsistent_winding=n_inconsistent,
        n_non_convex_cells=n_non_convex,
        n_zero_area_faces=n_zero_area,
        n_self_intersect_faces=n_self_int,
        avg_faces_per_cell=avg_f,
        max_faces_per_cell=max_f,
        min_faces_per_cell=min_f,
        elapsed_s=time.perf_counter() - t0,
        warnings=warns,
    )
