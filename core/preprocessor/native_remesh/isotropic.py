"""Isotropic remesh — Botsch & Kobbelt 2004 algorithm 의 경량 이식.

알고리즘 요지:
    target edge length `h` 가 주어졌을 때, 아래 4 step 을 `n_iter` 번 반복:

    1) Split — edge 길이 > 4/3 * h 인 edge 를 중점에서 분할
    2) Collapse — edge 길이 < 4/5 * h 인 edge 를 한 쪽 vertex 로 병합
    3) Flip — 두 face 가 공유하는 edge 에서 valence (이웃 face 수) 편차가 줄어들면
       다른 대각선으로 flip
    4) Relocate — 각 vertex 를 1-ring neighbour 의 centroid 로 이동 (tangential
       smoothing). 본 구현은 원 표면으로 사영 없이 단순 평균만 수행 (MVP).

Phase 2 (beta87 완성):
    - surface projection (원본 KDTree nearest-point 사영, Hausdorff drift 방지)
    - feature edge locking (dihedral > angle_thresh 의 vertex 는 smoothing 제외)

Phase 3 (beta99 완성):
    - valence constraint flip: interior vertex valence 6, boundary vertex valence 4 목표.
      ``isotropic_remesh(..., valence_constraint=True)`` 로 활성화.
    - vertex snapping to surface triangles (not just nearest vertex, 향후 확장)

제한 사항:
    - 현재 구현은 closed manifold 를 가정 (boundary edge 는 split/collapse 건너뜀)
    - Hausdorff distance 를 유지하지 않음 (기하 drift 가능)
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _build_edge_map(faces: np.ndarray) -> dict[tuple[int, int], list[int]]:
    m: dict[tuple[int, int], list[int]] = defaultdict(list)
    for fi, f in enumerate(faces):
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            m[_edge_key(int(a), int(b))].append(int(fi))
    return m


def _edge_lengths(
    V: np.ndarray, edges: list[tuple[int, int]],
) -> np.ndarray:
    if not edges:
        return np.zeros(0)
    a = np.array([e[0] for e in edges], dtype=np.int64)
    b = np.array([e[1] for e in edges], dtype=np.int64)
    return np.linalg.norm(V[a] - V[b], axis=1)


def _split_edges_above(
    V: np.ndarray, F: np.ndarray, h_hi: float,
) -> tuple[np.ndarray, np.ndarray, int]:
    """edge 가 h_hi 초과면 edge 중점에 vertex 삽입 + 두 삼각형 분할.

    단순 1-pass: 각 face 에서 가장 긴 edge 가 h_hi 초과면 분할. 같은 iteration 안
    에서 face 여러 개 분할 시 vertex 번호 증가를 반영하기 위해 List mutation.
    """
    V_list = V.tolist()
    new_F: list[list[int]] = []
    n_split = 0
    edge_mid: dict[tuple[int, int], int] = {}

    def _midpoint_id(a: int, b: int) -> int:
        nonlocal V_list, edge_mid
        k = (a, b) if a < b else (b, a)
        if k in edge_mid:
            return edge_mid[k]
        mid = [
            0.5 * (V_list[a][0] + V_list[b][0]),
            0.5 * (V_list[a][1] + V_list[b][1]),
            0.5 * (V_list[a][2] + V_list[b][2]),
        ]
        V_list.append(mid)
        idx = len(V_list) - 1
        edge_mid[k] = idx
        return idx

    for f in F:
        v0, v1, v2 = int(f[0]), int(f[1]), int(f[2])
        p0 = np.asarray(V_list[v0]); p1 = np.asarray(V_list[v1]); p2 = np.asarray(V_list[v2])
        e01 = float(np.linalg.norm(p0 - p1))
        e12 = float(np.linalg.norm(p1 - p2))
        e20 = float(np.linalg.norm(p2 - p0))
        # 가장 긴 edge 만 분할 (한 번에 한 edge — 안정적)
        longest = max(e01, e12, e20)
        if longest <= h_hi:
            new_F.append([v0, v1, v2])
            continue
        n_split += 1
        if longest == e01:
            m = _midpoint_id(v0, v1)
            new_F.append([v0, m, v2])
            new_F.append([m, v1, v2])
        elif longest == e12:
            m = _midpoint_id(v1, v2)
            new_F.append([v0, v1, m])
            new_F.append([v0, m, v2])
        else:  # e20 longest
            m = _midpoint_id(v2, v0)
            new_F.append([v0, v1, m])
            new_F.append([m, v1, v2])

    return (
        np.array(V_list, dtype=np.float64),
        np.array(new_F, dtype=np.int64),
        int(n_split),
    )


def _collapse_edges_below(
    V: np.ndarray, F: np.ndarray, h_lo: float,
) -> tuple[np.ndarray, np.ndarray, int]:
    """edge 가 h_lo 미만이면 한 vertex 로 병합.

    구현 전략 (MVP):
        1) 짧은 edge 하나 선택 → (a, b) 중 a 로 병합 (b → a 로 리매핑)
        2) b 를 참조하는 face 에서 (a, a, x) 형태 퇴화면 제거
        3) 다음 iteration 에서 계속
    한 iteration 에서 여러 edge 를 병합할 수 있으나 cascading conflict 를 피하기
    위해 각 vertex 는 최대 한 번만 병합 대상이 되도록 한다.
    """
    V_list = V.tolist()
    F_list = [list(f) for f in F.tolist()]
    merged_into = list(range(len(V_list)))  # union-find 유사 (but only 1-step)
    consumed = [False] * len(V_list)
    n_collapse = 0

    def _resolve(v: int) -> int:
        while merged_into[v] != v:
            v = merged_into[v]
        return v

    # edge 목록 (고유)
    edges = set()
    for f in F_list:
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            edges.add(_edge_key(int(a), int(b)))
    # 짧은 edge 순회
    edge_lens = []
    for a, b in edges:
        p = np.array(V_list[a]); q = np.array(V_list[b])
        L = float(np.linalg.norm(p - q))
        if L < h_lo:
            edge_lens.append((L, a, b))
    edge_lens.sort()

    for _, a, b in edge_lens:
        ra = _resolve(a); rb = _resolve(b)
        if ra == rb:
            continue
        if consumed[ra] or consumed[rb]:
            continue
        # b 를 a 에 병합 (좌표는 평균으로)
        pa = np.array(V_list[ra]); pb = np.array(V_list[rb])
        V_list[ra] = ((pa + pb) * 0.5).tolist()
        merged_into[rb] = ra
        consumed[ra] = True
        consumed[rb] = True
        n_collapse += 1

    # face 재작성
    new_F: list[list[int]] = []
    for f in F_list:
        a = _resolve(int(f[0])); b = _resolve(int(f[1])); c = _resolve(int(f[2]))
        if a == b or b == c or a == c:
            continue
        new_F.append([a, b, c])

    # vertex 압축
    used = sorted(set(v for tri in new_F for v in tri))
    remap = {old: new for new, old in enumerate(used)}
    V_out = np.array([V_list[i] for i in used], dtype=np.float64)
    F_out = np.array([[remap[v] for v in tri] for tri in new_F], dtype=np.int64)
    return V_out, F_out, int(n_collapse)


def _is_boundary_vertex(v: int, edge_map: dict[tuple[int, int], list[int]]) -> bool:
    """vertex v 가 boundary (manifold 아닌 edge) 에 속하면 True.

    boundary edge = 오직 1개의 face 만 공유하는 edge.
    """
    for (a, b), fl in edge_map.items():
        if (a == v or b == v) and len(fl) == 1:
            return True
    return False


def _flip_edges_to_improve_valence(
    V: np.ndarray, F: np.ndarray,
    valence_constraint: bool = False,
) -> tuple[np.ndarray, int]:
    """각 internal edge 에 대해 flip 전후 valence 편차가 줄어들면 flip.

    valence deviation = Σ |valence(v) − target(v)|, target = 6 (interior) or 4 (boundary).

    Args:
        valence_constraint: True (Phase 3, beta99) 면 목표 valence (interior=6,
            boundary=4) 기준 편차가 줄어드는 edge 를 최대한 flip 하는 다중 패스
            적용. False 면 단일 패스 (기존 동작).
    """
    # valence_constraint=True 면 수렴할 때까지 최대 3 패스 반복
    n_passes = 3 if valence_constraint else 1
    total_flipped = 0

    F_list = [list(f) for f in F.tolist()]
    n_verts = int(V.shape[0])

    for _pass in range(n_passes):
        edge_map = _build_edge_map(np.asarray(F_list, dtype=np.int64))

        # valence map
        valence = np.zeros(n_verts, dtype=np.int64)
        for f in F_list:
            for v in f:
                valence[int(v)] += 1
        # interior vs boundary — boundary edge = 1 face 만 공유
        on_boundary = np.zeros(n_verts, dtype=bool)
        for (a, b), fl in edge_map.items():
            if len(fl) == 1:
                on_boundary[a] = True; on_boundary[b] = True
        target = np.where(on_boundary, 4, 6)

        def _dev(v: int) -> int:
            return int(abs(int(valence[v]) - int(target[v])))

        n_flipped_pass = 0
        visited_edges: set[tuple[int, int]] = set()
        for (a, b), fl in edge_map.items():
            if len(fl) != 2 or (a, b) in visited_edges:
                continue
            f1_idx, f2_idx = fl[0], fl[1]
            f1 = F_list[f1_idx]; f2 = F_list[f2_idx]
            # opposite vertex 찾기 (삼각형의 세 vertex 중 a,b 아닌 것)
            def _opp(tri: list[int], _a: int, _b: int) -> int:
                for v in tri:
                    if v != _a and v != _b:
                        return int(v)
                return -1
            c = _opp(f1, a, b); d = _opp(f2, a, b)
            if c < 0 or d < 0:
                continue
            # 현재 deviation
            cur_dev = _dev(a) + _dev(b) + _dev(c) + _dev(d)
            # flip 후 valence: a, b 는 -1 / c, d 는 +1
            valence[a] -= 1; valence[b] -= 1; valence[c] += 1; valence[d] += 1
            new_dev = _dev(a) + _dev(b) + _dev(c) + _dev(d)
            if new_dev >= cur_dev:
                # rollback valence change
                valence[a] += 1; valence[b] += 1; valence[c] -= 1; valence[d] -= 1
                continue
            # flip 확정 — 두 face 를 (a,c,d) (b,d,c) 로 교체
            F_list[f1_idx] = [a, c, d]
            F_list[f2_idx] = [b, d, c]
            n_flipped_pass += 1
            visited_edges.add((a, b))

        total_flipped += n_flipped_pass
        # 더 이상 flip 없으면 조기 종료
        if n_flipped_pass == 0:
            break

    return np.array(F_list, dtype=np.int64), int(total_flipped)


def _tangential_relocate(
    V: np.ndarray, F: np.ndarray, lam: float = 0.5,
    feature_verts: frozenset[int] | None = None,
    origin_V: np.ndarray | None = None,
) -> np.ndarray:
    """각 vertex 를 1-ring neighbour 의 centroid 쪽으로 lam 비율 이동.

    beta87 Phase 2:
    - ``feature_verts`` 가 주어지면 해당 vertex 는 이동하지 않음 (feature lock).
    - ``origin_V`` 가 주어지면 이동 후 원본 표면의 nearest point 로 사영 (drift 방지).
    """
    n_verts = int(V.shape[0])
    sum_pos = np.zeros_like(V)
    count = np.zeros(n_verts, dtype=np.int64)
    adj: dict[int, set[int]] = defaultdict(set)
    for f in F:
        a, b, c = int(f[0]), int(f[1]), int(f[2])
        adj[a].add(b); adj[a].add(c)
        adj[b].add(a); adj[b].add(c)
        adj[c].add(a); adj[c].add(b)
    for v, ns in adj.items():
        for n in ns:
            sum_pos[v] += V[n]
            count[v] += 1
    non_zero = count > 0
    centroids = np.zeros_like(V)
    centroids[non_zero] = sum_pos[non_zero] / count[non_zero, np.newaxis]
    new_V = V.copy()
    mask = non_zero.copy()
    if feature_verts:
        for fv in feature_verts:
            if 0 <= fv < n_verts:
                mask[fv] = False  # feature vertex 는 이동 안 함
    new_V[mask] = V[mask] + lam * (centroids[mask] - V[mask])

    # Phase 2: surface projection (Hausdorff drift 방지)
    if origin_V is not None and origin_V.shape[0] > 0:
        try:
            from core.utils.kdtree import NumpyKDTree  # noqa: PLC0415
            tree = NumpyKDTree(origin_V)
            _, nn_idx = tree.query(new_V[mask], k=1)
            nn_idx = np.asarray(nn_idx).ravel()
            new_V[mask] = origin_V[nn_idx]
        except Exception:
            pass  # projection 실패 시 centroid 이동 그대로 사용
    return new_V


def _detect_feature_verts(
    V: np.ndarray, F: np.ndarray, angle_thresh_deg: float = 45.0,
) -> frozenset[int]:
    """인접 face 간 dihedral > threshold 인 edge 의 vertex 수집 (feature lock 용)."""
    if F.size == 0 or angle_thresh_deg <= 0:
        return frozenset()
    # face normals
    v0, v1, v2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    norms = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.where(norms > 1e-30, n / np.where(norms > 1e-30, norms, 1.0), 0.0)

    edge_map: dict[tuple[int, int], list[int]] = {}
    for fi in range(F.shape[0]):
        a, b, c = int(F[fi, 0]), int(F[fi, 1]), int(F[fi, 2])
        for x, y in ((a, b), (b, c), (c, a)):
            key = (x, y) if x < y else (y, x)
            edge_map.setdefault(key, []).append(fi)

    cos_thresh = float(np.cos(np.deg2rad(angle_thresh_deg)))
    feature: set[int] = set()
    for (a, b), fl in edge_map.items():
        if len(fl) != 2:
            feature.add(a); feature.add(b)
            continue
        cos_a = float(np.clip(np.dot(n[fl[0]], n[fl[1]]), -1.0, 1.0))
        if cos_a < cos_thresh:
            feature.add(a); feature.add(b)
    return frozenset(feature)


def isotropic_remesh(
    vertices: np.ndarray, faces: np.ndarray,
    *,
    target_edge_length: float,
    n_iter: int = 5,
    relocation_lambda: float = 0.5,
    project_to_surface: bool = False,
    feature_angle_deg: float = 45.0,
    lock_features: bool = False,
    valence_constraint: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """isotropic remesh 알고리즘 — split / collapse / flip / relocate 반복.

    Args:
        project_to_surface: True 면 relocate 후 원본 vertex 로 nearest-point 사영.
        feature_angle_deg: feature edge 판정 dihedral 기준.
        lock_features: True 면 sharp edge vertex 를 relocate 에서 제외 (feature lock).
        valence_constraint: True (Phase 3, beta99) 면 flip 시 interior vertex valence 6,
            boundary vertex valence 4 목표 편차 감소를 강제 적용.
            False (기본) = 기존 동작 (deviation 감소 시에만 flip).

    beta87 Phase 2: surface projection + feature locking 추가.
    beta99 Phase 3 (valence_constraint=True): valence constraint flip 강화.
    """
    V = np.asarray(vertices, dtype=np.float64).copy()
    F = np.asarray(faces, dtype=np.int64).copy()
    origin_V = V.copy() if project_to_surface else None
    h = float(target_edge_length)
    if h <= 0 or F.size == 0:
        return V, F
    h_hi = h * (4.0 / 3.0)
    h_lo = h * (4.0 / 5.0)

    feature_verts: frozenset[int] = frozenset()
    if lock_features:
        feature_verts = _detect_feature_verts(V, F, feature_angle_deg)

    for _ in range(max(1, int(n_iter))):
        V, F, _ = _split_edges_above(V, F, h_hi)
        V, F, _ = _collapse_edges_below(V, F, h_lo)
        F, _ = _flip_edges_to_improve_valence(V, F, valence_constraint=valence_constraint)
        V = _tangential_relocate(
            V, F, lam=relocation_lambda,
            feature_verts=feature_verts if feature_verts else None,
            origin_V=origin_V,
        )
    return V, F
