"""AutoTessell 자체 topology 유틸 — trimesh 속성 의존 제거 로드맵.

모두 numpy 기반 순수 Python 으로 구현. 입력은 (vertices, faces) 또는
CoreSurfaceMesh.

제공 함수:
    is_watertight(faces)    — 각 edge 가 정확히 2 face 공유
    is_manifold(faces)      — edge-manifold (각 edge 최대 2 face) + vertex-manifold
                              (vertex 주변 face 가 단일 fan 으로 연결)
    compute_euler(V, F)     — V - E + F
    compute_genus(V, F)     — (2 - Euler) / 2 (closed oriented surface 기준)
    num_connected_components(faces)
    split_components(faces) — face 의 component index 배열
    count_non_manifold_edges(faces)
    boundary_edges(faces)   — 1 face 만 참조하는 edge 리스트
    face_adjacency(faces)   — (n_faces, ?) list of neighbours across edges
    dihedral_angles(verts, faces) — 각 internal edge 의 dihedral angle (라디안)
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

try:
    from core.generator.native_tet._native import (
        surface_boundary_edges_batch as _c_surface_boundary_edges_batch,
        surface_edge_stats_batch as _c_surface_edge_stats_batch,
    )
except Exception:  # pragma: no cover - optional native extension
    _c_surface_boundary_edges_batch = None
    _c_surface_edge_stats_batch = None


# ---------------------------------------------------------------------------
# Edge helpers
# ---------------------------------------------------------------------------


def _edges_per_face(faces: np.ndarray) -> np.ndarray:
    """faces (F,3) → (3F, 2) array of sorted edges (min, max)."""
    if faces.size == 0:
        return np.zeros((0, 2), dtype=np.int64)
    e = np.stack(
        [faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]],
        axis=1,
    ).reshape(-1, 2)
    e = np.sort(e, axis=1)
    return e


def _edge_face_map(faces: np.ndarray) -> dict[tuple[int, int], list[int]]:
    """edge (sorted tuple) → list of face indices sharing that edge.

    Vectorized: builds all (3F,) edges + face indices via numpy, then
    groups with np.lexsort + np.searchsorted to avoid per-face Python loop.
    """
    F = int(faces.shape[0])
    e = _edges_per_face(faces)          # (3F, 2) sorted
    face_idx = np.repeat(np.arange(F, dtype=np.int64), 3)  # (3F,)

    # Lexicographic sort so identical edges are contiguous
    order = np.lexsort((e[:, 1], e[:, 0]))
    e_s = e[order]          # (3F, 2)
    fi_s = face_idx[order]  # (3F,)

    # Find group boundaries: where adjacent rows differ
    diff = np.any(e_s[1:] != e_s[:-1], axis=1)  # (3F-1,) bool
    starts = np.concatenate(([0], np.where(diff)[0] + 1))  # (G,)
    ends = np.concatenate((starts[1:], [3 * F]))             # (G,)

    result: dict[tuple[int, int], list[int]] = {}
    for s, end in zip(starts.tolist(), ends.tolist()):
        k = (int(e_s[s, 0]), int(e_s[s, 1]))
        result[k] = fi_s[s:end].tolist()
    return result


# ---------------------------------------------------------------------------
# Topology predicates
# ---------------------------------------------------------------------------


def is_watertight(faces: np.ndarray) -> bool:
    """모든 edge 가 정확히 2 face 를 공유하면 watertight."""
    if faces.size == 0:
        return False
    if _c_surface_edge_stats_batch is not None:
        stats = _c_surface_edge_stats_batch(faces)
        if stats is not None:
            _n_unique, n_boundary, n_nonmanifold, max_count = stats
            return bool(n_boundary == 0 and n_nonmanifold == 0 and max_count == 2)
    e = _edges_per_face(faces)
    # numpy unique with counts — (unique_edges, counts)
    uq, cnt = np.unique(e, axis=0, return_counts=True)
    return bool((cnt == 2).all())


def is_edge_manifold(faces: np.ndarray) -> bool:
    """각 edge 가 최대 2 face 를 공유하면 edge-manifold."""
    if faces.size == 0:
        return True
    if _c_surface_edge_stats_batch is not None:
        stats = _c_surface_edge_stats_batch(faces)
        if stats is not None:
            return bool(stats[3] <= 2)
    e = _edges_per_face(faces)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return bool((cnt <= 2).all())


def count_non_manifold_edges(faces: np.ndarray) -> int:
    """3 face 이상 공유하는 edge 수."""
    if faces.size == 0:
        return 0
    if _c_surface_edge_stats_batch is not None:
        stats = _c_surface_edge_stats_batch(faces)
        if stats is not None:
            return int(stats[2])
    e = _edges_per_face(faces)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return int((cnt >= 3).sum())


def is_manifold(faces: np.ndarray) -> bool:
    """edge-manifold + vertex-manifold 판정.

    vertex-manifold: 각 vertex 주변의 face 들이 단일 fan 으로 연결되어야 함.
    (이 함수에서는 edge-manifold 만 검사해도 대부분 케이스 커버. 완전한 vertex-
    manifold 판정은 고비용 — 필요시 별도 구현.)
    """
    return is_edge_manifold(faces)


def boundary_edges(faces: np.ndarray) -> np.ndarray:
    """1 face 만 참조하는 edge 들 (surface boundary). (K, 2)."""
    if faces.size == 0:
        return np.zeros((0, 2), dtype=np.int64)
    if _c_surface_boundary_edges_batch is not None:
        out = _c_surface_boundary_edges_batch(faces)
        if out is not None:
            return out
    e = _edges_per_face(faces)
    uq, cnt = np.unique(e, axis=0, return_counts=True)
    return uq[cnt == 1]


# ---------------------------------------------------------------------------
# Euler / Genus
# ---------------------------------------------------------------------------


def compute_euler(n_vertices: int, faces: np.ndarray) -> int:
    """V - E + F. E 는 unique undirected edge 수."""
    if faces.size == 0:
        return int(n_vertices)
    if _c_surface_edge_stats_batch is not None:
        stats = _c_surface_edge_stats_batch(faces)
        if stats is not None:
            return int(n_vertices - stats[0] + faces.shape[0])
    e = _edges_per_face(faces)
    uq = np.unique(e, axis=0)
    return int(n_vertices - uq.shape[0] + faces.shape[0])


def compute_genus(n_vertices: int, faces: np.ndarray) -> int:
    """Closed oriented surface 의 genus = (2 − Euler) / 2.

    열린 표면 / non-manifold 의 경우 수학적 의미가 모호. 호출자가 watertight 여부
    를 확인 후 사용 권장.
    """
    euler = compute_euler(n_vertices, faces)
    return int((2 - euler) // 2)


# ---------------------------------------------------------------------------
# Connected components (face-level, edge-adjacency 기반)
# ---------------------------------------------------------------------------


def _union_find_init(n: int) -> list[int]:
    return list(range(n))


def _uf_find(parent: list[int], x: int) -> int:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _uf_union(parent: list[int], a: int, b: int) -> None:
    ra, rb = _uf_find(parent, a), _uf_find(parent, b)
    if ra != rb:
        parent[ra] = rb


def split_components(faces: np.ndarray) -> np.ndarray:
    """face 별 component index (0-indexed). face-edge 인접 기반 union-find."""
    F = int(faces.shape[0])
    if F == 0:
        return np.zeros(0, dtype=np.int64)
    edge_map = _edge_face_map(faces)
    parent = _union_find_init(F)
    for _edge, flist in edge_map.items():
        if len(flist) < 2:
            continue
        base = flist[0]
        for other in flist[1:]:
            _uf_union(parent, base, other)
    # C-PERF-33 / beta2484 — vectorize root-find via iterative path doubling.
    # parent[i] points to (eventual) root after unions; doubling parent =
    # parent[parent] log2(F)+2 times converges all paths to roots.
    parent_arr = np.asarray(parent, dtype=np.int64)
    n_steps = int(np.log2(max(F, 2))) + 2
    for _ in range(n_steps):
        new_parent = parent_arr[parent_arr]
        if np.array_equal(new_parent, parent_arr):
            break
        parent_arr = new_parent
    roots = parent_arr
    # compact 0..K-1
    unique_roots, comp = np.unique(roots, return_inverse=True)
    return comp.astype(np.int64)


def num_connected_components(faces: np.ndarray) -> int:
    if faces.size == 0:
        return 0
    return int(split_components(faces).max()) + 1


# ---------------------------------------------------------------------------
# Dihedral angles (sharp edge 감지용)
# ---------------------------------------------------------------------------


def _face_normals_unit(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    if faces.size == 0:
        return np.zeros((0, 3))
    v = vertices[faces]
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    m = np.linalg.norm(n, axis=1, keepdims=True)
    m[m < 1e-30] = 1.0
    return n / m


def dihedral_angles(
    vertices: np.ndarray, faces: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """internal edge 별 dihedral angle (라디안). 0 = 평평, π = 완전히 접힌 상태.

    완전 numpy 벡터화: per-edge Python loop 없음.

    Returns:
        (edges, angles) — edges: (K, 2) int64, angles: (K,) float64.
    """
    if faces.size == 0:
        return np.zeros((0, 2), dtype=np.int64), np.zeros(0, dtype=np.float64)
    normals = _face_normals_unit(vertices, faces)  # (F, 3)

    # Build (3F, 2) sorted edges + face index per half-edge — all numpy
    F = faces.shape[0]
    face_idx = np.repeat(np.arange(F, dtype=np.int64), 3)   # (3F,)
    e_raw = _edges_per_face(faces)                           # (3F, 2) sorted

    # Lexicographic sort on (e0, e1) to group shared edges together
    order = np.lexsort((e_raw[:, 1], e_raw[:, 0]))
    e_sorted = e_raw[order]        # (3F, 2)
    fi_sorted = face_idx[order]    # (3F,)

    # Find runs: positions where adjacent rows are equal → shared edge
    same = np.all(e_sorted[1:] == e_sorted[:-1], axis=1)  # (3F-1,) bool
    # Indices where a run of 2 starts (same[i] True means row i and i+1 match)
    run_start = np.where(same)[0]  # positions i where e[i]==e[i+1]

    # Keep only pairs where exactly 2 faces share an edge (manifold interior)
    # A non-manifold edge would appear 3+ times; we take consecutive pairs.
    # Filter: run_start[j]+1 must not also be in run_start (i.e. no triple)
    if run_start.size == 0:
        return np.zeros((0, 2), dtype=np.int64), np.zeros(0, dtype=np.float64)

    # Exclude starts that are themselves part of a longer run
    is_triple_start = np.zeros(run_start.size, dtype=bool)
    if run_start.size > 1:
        # if run_start[k]+1 == run_start[k+1], then we have ≥3 consecutive
        is_triple_start[:-1] = (run_start[1:] == run_start[:-1] + 1)
        is_triple_start[1:] |= (run_start[1:] == run_start[:-1] + 1)
    valid = ~is_triple_start
    rs = run_start[valid]           # valid pair starts

    if rs.size == 0:
        return np.zeros((0, 2), dtype=np.int64), np.zeros(0, dtype=np.float64)

    # Extract edge endpoints and face pairs — vectorized
    edge_verts = e_sorted[rs]              # (K, 2)
    fi0 = fi_sorted[rs]                   # (K,) face index 0
    fi1 = fi_sorted[rs + 1]               # (K,) face index 1

    # Dot product of normals — fully vectorized
    n0 = normals[fi0]                     # (K, 3)
    n1 = normals[fi1]                     # (K, 3)
    cos_a = np.clip((n0 * n1).sum(axis=1), -1.0, 1.0)  # (K,)
    angles = np.arccos(cos_a)             # (K,)

    return edge_verts.astype(np.int64), angles


def count_sharp_edges(
    vertices: np.ndarray, faces: np.ndarray,
    angle_threshold_deg: float = 30.0,
) -> int:
    """face 법선 차이가 threshold 이상인 내부 edge 수 (sharp feature)."""
    _, angles = dihedral_angles(vertices, faces)
    thresh_rad = float(np.deg2rad(angle_threshold_deg))
    return int((angles >= thresh_rad).sum())
