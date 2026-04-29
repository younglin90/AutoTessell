"""C6.1 / beta2371 — Hex BL prism stacking (Pointwise T-Rex hex BL 동등).

목적:
    hex-only mesh 의 wall face (quad) 에서 wall-normal 방향으로 hex cell
    을 stack 하여 boundary layer 를 추가. Pointwise T-Rex 의 hex BL 과
    동등. 기존 native_bl.py (wedge prism 6-vertex) 와 다른 점:
        - wall face = quad (4-vertex)
        - 추출된 cell = hex (8-vertex), 두께가 geometric (first × g^k).

알고리즘:
    1. 각 wall quad face (q0, q1, q2, q3) 에 대해 N+1 layer 의 vertex 생성:
       layer 0 = wall surface (q0..q3)
       layer k = q_i + thickness_k × normal[q_i],  thickness_k = first × Σ g^j (j<k)
    2. layer k → k+1 사이에 hex cell 생성:
       hex = (l0_q0, l0_q1, l0_q2, l0_q3, l1_q0, l1_q1, l1_q2, l1_q3)

이 모듈은 pure-function 한 입력→출력 매핑만 제공. C6.2 후속에서
tier_layers_post.run 에 mesh_type=hex_dominant 분기 wired.

CLAUDE.md 정책:
    - 외부 lib 신규 의존 0.
    - 단일 파일 < 350 줄.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class HexBLResult:
    """Hex BL extrude 결과 통계."""

    n_wall_quads: int
    n_wall_verts: int
    n_layers: int
    n_hex_cells: int       # n_wall_quads * n_layers.
    n_new_points: int      # n_wall_verts * n_layers.
    total_thickness: float
    elapsed_s: float


def _layer_thicknesses(
    first_thickness: float, growth_ratio: float, n_layers: int,
) -> NDArray[np.float64]:
    """k-th layer 의 두께 = first × g^k (k = 0..n-1)."""
    g = float(growth_ratio)
    f = float(first_thickness)
    return np.array([f * (g ** k) for k in range(int(n_layers))], dtype=np.float64)


def _cumulative_offsets(thicknesses: NDArray[np.float64]) -> NDArray[np.float64]:
    """Layer k 의 wall surface 부터 누적 거리 (k=0 → 0, k=N → total)."""
    return np.concatenate(([0.0], np.cumsum(thicknesses)))


def extrude_hex_bl(
    points: NDArray[np.float64],
    wall_quads: NDArray[np.int64],
    vertex_normals: NDArray[np.float64],
    *,
    num_layers: int,
    first_thickness: float,
    growth_ratio: float = 1.2,
) -> tuple[NDArray[np.float64], NDArray[np.int64], HexBLResult]:
    """Wall quad face → hex cell stack 을 wall-normal 방향으로 extrude.

    Args:
        points: (P, 3) 좌표.
        wall_quads: (Q, 4) wall face connectivity. CCW outward (or 일관성).
        vertex_normals: (P, 3) 각 mesh vertex 의 wall-outward normal
            (wall vertex 에만 의미 있음; 나머지는 0 ok).
        num_layers: 적층할 layer 수 (≥ 1).
        first_thickness: 첫 layer 두께.
        growth_ratio: 층간 성장비.

    Returns:
        (new_points, hex_cells, HexBLResult).
        new_points: (P + n_wall_verts × num_layers, 3) — append-only.
        hex_cells: (Q × num_layers, 8) — 8-vertex hex.
    """
    import time as _t
    t0 = _t.perf_counter()

    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError(f"points 는 (P,3) 형태여야 함 (got {pts.shape})")

    quads = np.asarray(wall_quads, dtype=np.int64)
    if quads.ndim != 2 or quads.shape[1] != 4:
        raise ValueError(f"wall_quads 는 (Q,4) 형태여야 함 (got {quads.shape})")

    vnorm = np.asarray(vertex_normals, dtype=np.float64)
    if vnorm.shape != pts.shape:
        raise ValueError(
            f"vertex_normals 크기 {vnorm.shape} ≠ points {pts.shape}"
        )

    n_quads = int(quads.shape[0])
    nl = int(num_layers)
    if n_quads == 0 or nl < 1:
        return pts.copy(), np.zeros((0, 8), dtype=np.int64), HexBLResult(
            n_wall_quads=n_quads, n_wall_verts=0, n_layers=nl, n_hex_cells=0,
            n_new_points=0, total_thickness=0.0,
            elapsed_s=_t.perf_counter() - t0,
        )

    # 1) wall vertex 집합 — quad 에서 추출, sorted unique.
    wall_v = np.unique(quads.ravel())
    n_wall = int(wall_v.shape[0])

    # 2) thickness offsets — (nl + 1,), offset[k] = wall surface 부터 k 번째 layer 까지 누적.
    thicks = _layer_thicknesses(float(first_thickness), float(growth_ratio), nl)
    offsets = _cumulative_offsets(thicks)
    total_t = float(offsets[-1])

    # 3) vertex layer table — layer_pids[k][global_vid] = new pid.
    #    layer 0 = original (pts), layer k>0 = new appended.
    next_pid = pts.shape[0]
    new_pts_list: list[NDArray[np.float64]] = [pts]
    # vid → row in wall_v (for normal lookup).
    wall_v_to_row = {int(v): r for r, v in enumerate(wall_v.tolist())}

    layer_pids: list[dict[int, int]] = [{} for _ in range(nl + 1)]
    # layer 0 = original.
    for v in wall_v.tolist():
        layer_pids[0][int(v)] = int(v)

    # layer k > 0: 모든 wall vertex 에 대해 새 pid 추가.
    for k in range(1, nl + 1):
        offs_k = float(offsets[k])
        new_layer_pts = np.zeros((n_wall, 3), dtype=np.float64)
        for r, v in enumerate(wall_v.tolist()):
            base_p = pts[v]
            n = vnorm[v]
            new_layer_pts[r] = base_p + offs_k * n
            layer_pids[k][int(v)] = next_pid + r
        new_pts_list.append(new_layer_pts)
        next_pid += n_wall

    new_points = np.vstack(new_pts_list)

    # 4) hex cell 생성 — quad q × layer k 마다 8-vertex hex.
    #    OpenFOAM hex ordering: bottom (0,1,2,3) CCW + top (4,5,6,7) 같은 순서.
    #    여기서 bottom = layer k, top = layer k+1.
    n_hex = n_quads * nl
    hex_cells = np.zeros((n_hex, 8), dtype=np.int64)
    cell_idx = 0
    for qi in range(n_quads):
        q0, q1, q2, q3 = quads[qi].tolist()
        for k in range(nl):
            lk = layer_pids[k]
            lkp1 = layer_pids[k + 1]
            hex_cells[cell_idx, 0] = lk[q0]
            hex_cells[cell_idx, 1] = lk[q1]
            hex_cells[cell_idx, 2] = lk[q2]
            hex_cells[cell_idx, 3] = lk[q3]
            hex_cells[cell_idx, 4] = lkp1[q0]
            hex_cells[cell_idx, 5] = lkp1[q1]
            hex_cells[cell_idx, 6] = lkp1[q2]
            hex_cells[cell_idx, 7] = lkp1[q3]
            cell_idx += 1

    return new_points, hex_cells, HexBLResult(
        n_wall_quads=n_quads,
        n_wall_verts=n_wall,
        n_layers=nl,
        n_hex_cells=n_hex,
        n_new_points=n_wall * nl,
        total_thickness=total_t,
        elapsed_s=_t.perf_counter() - t0,
    )
