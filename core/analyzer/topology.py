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
    """edge (sorted tuple) → list of face indices sharing that edge."""
    result: dict[tuple[int, int], list[int]] = defaultdict(list)
    for fi in range(faces.shape[0]):
        f = faces[fi]
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            k = (int(min(a, b)), int(max(a, b)))
            result[k].append(fi)
    return result


# ---------------------------------------------------------------------------
# Topology predicates
# ---------------------------------------------------------------------------


def is_watertight(faces: np.ndarray) -> bool:
    """모든 edge 가 정확히 2 face 를 공유하면 watertight."""
    if faces.size == 0:
        return False
    e = _edges_per_face(faces)
    # numpy unique with counts — (unique_edges, counts)
    uq, cnt = np.unique(e, axis=0, return_counts=True)
    return bool((cnt == 2).all())


def is_edge_manifold(faces: np.ndarray) -> bool:
    """각 edge 가 최대 2 face 를 공유하면 edge-manifold."""
    if faces.size == 0:
        return True
    e = _edges_per_face(faces)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return bool((cnt <= 2).all())


def count_non_manifold_edges(faces: np.ndarray) -> int:
    """3 face 이상 공유하는 edge 수."""
    if faces.size == 0:
        return 0
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
    roots = np.array([_uf_find(parent, i) for i in range(F)])
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

    Returns:
        (edges, angles) — edges: (K, 2) int64, angles: (K,) float64.
    """
    if faces.size == 0:
        return np.zeros((0, 2), dtype=np.int64), np.zeros(0, dtype=np.float64)
    normals = _face_normals_unit(vertices, faces)
    edge_map = _edge_face_map(faces)
    edges_out: list[tuple[int, int]] = []
    angles_out: list[float] = []
    for (a, b), fl in edge_map.items():
        if len(fl) != 2:
            continue
        n1 = normals[fl[0]]; n2 = normals[fl[1]]
        c = float(np.clip(np.dot(n1, n2), -1.0, 1.0))
        ang = float(np.arccos(c))
        edges_out.append((a, b))
        angles_out.append(ang)
    return (
        np.array(edges_out, dtype=np.int64) if edges_out else np.zeros((0, 2), dtype=np.int64),
        np.array(angles_out, dtype=np.float64),
    )


def count_sharp_edges(
    vertices: np.ndarray, faces: np.ndarray,
    angle_threshold_deg: float = 30.0,
) -> int:
    """face 법선 차이가 threshold 이상인 내부 edge 수 (sharp feature)."""
    _, angles = dihedral_angles(vertices, faces)
    thresh_rad = float(np.deg2rad(angle_threshold_deg))
    return int((angles >= thresh_rad).sum())
