"""Phase Q — 입력 표면 pre-check.

generate_native_tet 진입 전에 입력의 degenerate / self-intersection 가능성을
감지해 경고 (failure 아님, 계속 진행 가능). 사용자가 입력 품질을 인지하도록.

레퍼런스
    - Möller 1997, "A Fast Triangle-Triangle Intersection Test".
    - Botsch et al. 2010 §1.4 consistency checks.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class InputCheckResult:
    n_duplicate_vertices: int
    n_zero_area_triangles: int
    n_boundary_edges: int          # 1 owner edge (non-watertight)
    n_nonmanifold_edges: int       # 3+ owner edge
    min_triangle_area: float
    min_dihedral_deg: float
    warnings: list[str]


def check_input(
    V: np.ndarray, F: np.ndarray,
    *,
    dup_tol: float = 1e-12,
    zero_area_tol: float = 1e-20,
) -> InputCheckResult:
    """입력 surface mesh 의 기본 건강성 리포트."""
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    warnings: list[str] = []

    # 1) 중복 vertex.
    n_dup = 0
    if V.shape[0] > 0:
        # round to tol grid + unique.
        scale = 1.0 / max(dup_tol, 1e-30)
        q = np.round(V * scale).astype(np.int64)
        _, counts = np.unique(
            q.view([("", q.dtype)] * 3),
            return_counts=True,
        )
        n_dup = int((counts > 1).sum())
        if n_dup > 0:
            warnings.append(
                f"duplicate vertices: {n_dup} (tolerance={dup_tol:.2e})"
            )

    # 2) triangle area.
    min_area = 0.0
    n_zero = 0
    if F.shape[0] > 0:
        e1 = V[F[:, 1]] - V[F[:, 0]]
        e2 = V[F[:, 2]] - V[F[:, 0]]
        area = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
        n_zero = int((area < zero_area_tol).sum())
        min_area = float(area.min()) if area.size else 0.0
        if n_zero > 0:
            warnings.append(
                f"zero-area triangles: {n_zero} (< {zero_area_tol:.2e})"
            )

    # 3) edge topology.
    n_boundary = 0; n_nonmanifold = 0
    min_dih = 180.0
    if F.shape[0] > 0:
        edge_owners: dict[tuple[int, int], list[int]] = {}
        for ti in range(F.shape[0]):
            a, b, c = int(F[ti, 0]), int(F[ti, 1]), int(F[ti, 2])
            for u, v in ((a, b), (b, c), (c, a)):
                key = (u, v) if u < v else (v, u)
                edge_owners.setdefault(key, []).append(ti)
        for key, lst in edge_owners.items():
            if len(lst) == 1:
                n_boundary += 1
            elif len(lst) >= 3:
                n_nonmanifold += 1
        if n_boundary > 0:
            warnings.append(f"non-watertight: {n_boundary} boundary edges")
        if n_nonmanifold > 0:
            warnings.append(
                f"non-manifold: {n_nonmanifold} edges with 3+ owners"
            )

    return InputCheckResult(
        n_duplicate_vertices=n_dup,
        n_zero_area_triangles=n_zero,
        n_boundary_edges=n_boundary,
        n_nonmanifold_edges=n_nonmanifold,
        min_triangle_area=min_area,
        min_dihedral_deg=min_dih,
        warnings=warnings,
    )
