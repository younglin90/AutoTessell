"""G2 / beta2603 — Mixed-element pyramid interface (tet ↔ hex transition).

Pointwise/Star-CCM+ 의 mixed-element mesh 핵심: hex 영역과 tet 영역이
인접할 때 quad face (hex 측) 와 tri face (tet 측) 가 직접 만날 수 없음.
Pyramid (5-vertex: 4 base + 1 apex) cell 이 transition layer 역할.

알고리즘:
    1. interface face 식별 — hex 영역과 tet 영역이 공유하는 quad face.
    2. quad face 별 apex 점 계산 (centroid + offset toward tet 측).
    3. pyramid cell 생성 (4 base verts + 1 apex), 4 tri face 추가.
    4. quad → 4 tri 분할로 tet 측 표면 보정.

CLAUDE.md 정책:
    - numpy only. 외부 의존 0.
    - 단일 파일 < 350 줄.
    - tet/hex polyMesh 호환 (1 owner per face).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray


@dataclass
class PyramidInterfaceResult:
    """Pyramid 인터페이스 빌드 결과."""

    success: bool
    n_pyramid_cells: int = 0
    n_new_apex_points: int = 0
    n_new_tri_faces: int = 0
    interface_quad_face_ids: list[int] = field(default_factory=list)
    elapsed_s: float = 0.0
    message: str = ""


def detect_interface_quads(
    hex_cells: NDArray[np.int64],
    tet_cells: NDArray[np.int64],
    hex_face_owner: NDArray[np.int64],
    hex_face_verts: list[list[int]],
) -> list[int]:
    """hex 영역의 boundary quad face 중 tet 영역과 인접한 face id 반환.

    인접 판정: hex face 의 4 vertex 가 tet cell 의 vertex 집합과 ≥ 3 공유.

    Args:
        hex_cells: (Nh, 8) — hex cell connectivity.
        tet_cells: (Nt, 4) — tet cell connectivity.
        hex_face_owner: (Nf,) — hex face 의 owner cell id.
        hex_face_verts: list of [v0, v1, v2, v3] (quad face vertex IDs).

    Returns:
        interface quad face id list.
    """
    if hex_cells.size == 0 or tet_cells.size == 0:
        return []
    tet_v_set = set(np.asarray(tet_cells, dtype=np.int64).reshape(-1).tolist())
    interface_ids: list[int] = []
    for fi, fv in enumerate(hex_face_verts):
        if len(fv) != 4:
            continue
        n_shared = sum(1 for v in fv if int(v) in tet_v_set)
        if n_shared >= 3:
            interface_ids.append(fi)
    return interface_ids


def build_pyramid_cells(
    points: NDArray[np.float64],
    interface_quads: list[list[int]],
    *,
    apex_offset_factor: float = 0.5,
) -> tuple[NDArray[np.float64], NDArray[np.int64], list[list[int]], PyramidInterfaceResult]:
    """interface quad → pyramid (5-vertex) cell + 4 new tri faces 생성.

    각 quad face (v0, v1, v2, v3) 에 대해:
        apex = centroid + normal × (avg_edge × apex_offset_factor)
        pyramid = (v0, v1, v2, v3, apex)
        4 new tri faces: (v0, v1, apex), (v1, v2, apex), (v2, v3, apex), (v3, v0, apex)

    Args:
        points: (P, 3) 좌표.
        interface_quads: list of [v0, v1, v2, v3] (quad vertex IDs).
        apex_offset_factor: apex 의 offset (mean_edge × factor). 0.5 = 정사면체-like.

    Returns:
        (new_points, pyramid_cells, new_tri_faces, PyramidInterfaceResult).
        new_points: 원본 + apex 추가.
        pyramid_cells: (Np, 5) — last index = apex.
        new_tri_faces: list of [a, b, c] (4 tris per pyramid).
    """
    import time as _t
    t0 = _t.perf_counter()

    pts = np.asarray(points, dtype=np.float64)
    n_pts_old = int(pts.shape[0])
    n_quads = len(interface_quads)

    if n_quads == 0:
        return pts.copy(), np.zeros((0, 5), dtype=np.int64), [], PyramidInterfaceResult(
            success=False, n_pyramid_cells=0,
            elapsed_s=_t.perf_counter() - t0,
            message="no interface quads",
        )

    apex_pts: list[NDArray[np.float64]] = []
    pyramid_cells: list[list[int]] = []
    new_tri_faces: list[list[int]] = []
    next_apex_id = n_pts_old

    for q in interface_quads:
        if len(q) != 4:
            continue
        v0, v1, v2, v3 = int(q[0]), int(q[1]), int(q[2]), int(q[3])
        p0, p1, p2, p3 = pts[v0], pts[v1], pts[v2], pts[v3]
        centroid = 0.25 * (p0 + p1 + p2 + p3)
        # normal: avg of two diagonals' cross.
        n_vec = np.cross(p2 - p0, p3 - p1)
        nl = float(np.linalg.norm(n_vec))
        if nl < 1e-30:
            continue
        n_unit = n_vec / nl
        # mean edge length.
        mean_e = 0.25 * (
            float(np.linalg.norm(p1 - p0))
            + float(np.linalg.norm(p2 - p1))
            + float(np.linalg.norm(p3 - p2))
            + float(np.linalg.norm(p0 - p3))
        )
        apex = centroid + n_unit * (mean_e * float(apex_offset_factor))
        apex_pts.append(apex[None, :])
        a_id = next_apex_id
        next_apex_id += 1
        pyramid_cells.append([v0, v1, v2, v3, a_id])
        # 4 tri faces (CCW from outside, apex away from viewer).
        new_tri_faces.append([v0, v1, a_id])
        new_tri_faces.append([v1, v2, a_id])
        new_tri_faces.append([v2, v3, a_id])
        new_tri_faces.append([v3, v0, a_id])

    if not pyramid_cells:
        return pts.copy(), np.zeros((0, 5), dtype=np.int64), [], PyramidInterfaceResult(
            success=False, n_pyramid_cells=0,
            elapsed_s=_t.perf_counter() - t0,
            message="all quads skipped (degenerate)",
        )

    new_points = np.vstack([pts] + apex_pts)
    pyramid_arr = np.asarray(pyramid_cells, dtype=np.int64)

    return new_points, pyramid_arr, new_tri_faces, PyramidInterfaceResult(
        success=True,
        n_pyramid_cells=int(pyramid_arr.shape[0]),
        n_new_apex_points=len(apex_pts),
        n_new_tri_faces=len(new_tri_faces),
        elapsed_s=_t.perf_counter() - t0,
        message=f"built {pyramid_arr.shape[0]} pyramid cells, {len(apex_pts)} apex points",
    )


def split_quad_to_tri(
    quad_verts: list[int],
    new_apex_id: int | None = None,
) -> list[list[int]]:
    """quad → 2 tri (diagonal split) 또는 4 tri (apex 사용).

    Args:
        quad_verts: [v0, v1, v2, v3].
        new_apex_id: None 이면 diagonal (v0-v2) split. else 4 tri (v0,v1,apex), ...

    Returns:
        list of [a, b, c] tri face vertex IDs.
    """
    if len(quad_verts) != 4:
        return []
    v0, v1, v2, v3 = quad_verts
    if new_apex_id is None:
        return [[v0, v1, v2], [v0, v2, v3]]
    return [
        [v0, v1, new_apex_id],
        [v1, v2, new_apex_id],
        [v2, v3, new_apex_id],
        [v3, v0, new_apex_id],
    ]


def pyramid_quality(pts: NDArray[np.float64], pyramid: NDArray[np.int64]) -> float:
    """Pyramid (5-vertex) 의 normalized quality.

    Mean-ratio metric 변형:
        Q = 5 × V / (mean_edge_length^3 / 6)
    완벽 정사각뿔 (apex 가 base 평면 위 정중앙, 높이 = base_diag/sqrt(2)) → Q ≈ 1.
    """
    if pyramid.shape[0] != 5:
        return 0.0
    p = pts[pyramid]  # (5, 3).
    base = p[:4]
    apex = p[4]
    # base centroid.
    cb = base.mean(axis=0)
    # height = |apex - cb|.
    h = float(np.linalg.norm(apex - cb))
    if h < 1e-30:
        return 0.0
    # base area via 2 tri 분할.
    a1 = 0.5 * float(np.linalg.norm(np.cross(base[1] - base[0], base[2] - base[0])))
    a2 = 0.5 * float(np.linalg.norm(np.cross(base[2] - base[0], base[3] - base[0])))
    base_area = a1 + a2
    # volume = (1/3) × base_area × h.
    vol = (base_area * h) / 3.0
    # mean edge = (4 base edges + 4 lateral edges) / 8.
    edges = [
        float(np.linalg.norm(base[(i + 1) % 4] - base[i])) for i in range(4)
    ]
    edges += [float(np.linalg.norm(apex - base[i])) for i in range(4)]
    mean_e = float(np.mean(edges))
    if mean_e < 1e-30:
        return 0.0
    # normalize: 정사각뿔 V_ref = (a^2 × h_ref)/3, h_ref = a × √2/2 → V_ref = a^3 × √2/6.
    a = mean_e
    v_ref = (a ** 3) * np.sqrt(2.0) / 6.0
    if v_ref < 1e-30:
        return 0.0
    return float(np.clip(vol / v_ref, 0.0, 1.0))
