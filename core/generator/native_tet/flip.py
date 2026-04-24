"""Phase B3 — Face flip (2-3 / 3-2) for quality improvement.

2-3 flip : 두 tet 이 공유하는 triangle 을 없애고, 그 자리에 새 edge (반대편
           두 vertex 를 잇는) 가 생기도록 재구성. 2 tet → 3 tet.
3-2 flip : 3 tet 이 공유하는 내부 edge 를 제거, 2 tet 로 재구성. 2-3 의 역.

flip 은 quality 가 개선될 때 + topology 가 valid 할 때만 수행. 본 구현은
"quality 개선" 만 보수적으로 검사 (Delaunay criterion 은 미구현, 다음 round).

레퍼런스
    - Edelsbrunner 2001, "Geometry and Topology for Mesh Generation" §3.
    - Botsch et al. 2010 §5.4.
    - fTetWild (MPL-2.0) §3.3 — 독립 Python 재구현.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FlipResult:
    n_flip_23: int
    n_flip_32: int
    n_tets_before: int
    n_tets_after: int
    min_quality_before: float
    min_quality_after: float


def _tet_quality(A, B, C, D) -> float:
    v = np.abs(np.dot(B - A, np.cross(C - A, D - A))) / 6.0
    e = [A - B, A - C, A - D, B - C, B - D, C - D]
    emax = max(float(np.linalg.norm(x)) for x in e)
    if emax < 1e-30:
        return 0.0
    return 8.48 * v / (emax ** 3)


def _tet_signed_vol6(A, B, C, D) -> float:
    return float(np.dot(B - A, np.cross(C - A, D - A)))


def flip_faces_23(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    min_quality_improvement: float = 1e-4,
    max_flips: int = 5000,
) -> tuple[np.ndarray, int]:
    """공유 face 를 가진 tet pair 마다 2-3 flip 시도.

    두 tet {A,B,C,X} 와 {A,B,C,Y} 가 face (A,B,C) 를 공유할 때, 새 구성
    {A,B,X,Y}, {B,C,X,Y}, {C,A,X,Y} 가 전부 valid (positive volume) 하고
    min_quality 가 개선되면 교체.
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64).copy()
    if tets.size == 0:
        return tets, 0

    def _face_map(T: np.ndarray) -> dict[tuple[int, int, int], list[int]]:
        m: dict[tuple[int, int, int], list[int]] = {}
        for i in range(T.shape[0]):
            a, b, c, d = (int(x) for x in T[i])
            for tri in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
                k = tuple(sorted(tri))
                m.setdefault(k, []).append(i)  # type: ignore[arg-type]
        return m

    n_flip = 0
    alive = np.ones(tets.shape[0], dtype=bool)
    tets_list = tets.tolist()

    # 한 번의 pass 로 처리 (여러 pass 는 외부에서 반복).
    fmap = _face_map(np.asarray(tets_list, dtype=np.int64))
    visited_faces: set[tuple[int, int, int]] = set()

    for face, owners in list(fmap.items()):
        if n_flip >= max_flips:
            break
        if len(owners) != 2:
            continue
        if face in visited_faces:
            continue
        ti, tj = owners
        if not (alive[ti] and alive[tj]):
            continue
        a, b, c = face
        x_cands = [v for v in tets_list[ti] if v not in face]
        y_cands = [v for v in tets_list[tj] if v not in face]
        if len(x_cands) != 1 or len(y_cands) != 1:
            continue
        x = x_cands[0]; y = y_cands[0]
        if x == y:
            continue

        # 기존 2 tet 의 min quality.
        q_old = min(
            _tet_quality(pts[a], pts[b], pts[c], pts[x]),
            _tet_quality(pts[a], pts[b], pts[c], pts[y]),
        )

        # 새 3 tet.
        new_tets = [
            (a, b, x, y),
            (b, c, x, y),
            (c, a, x, y),
        ]
        # 모두 양의 부피 + 중복 없어야 함.
        ok = True
        q_new_min = 1.0
        for nt in new_tets:
            if len(set(nt)) != 4:
                ok = False; break
            vol6 = _tet_signed_vol6(pts[nt[0]], pts[nt[1]], pts[nt[2]], pts[nt[3]])
            if abs(vol6) < 1e-20:
                ok = False; break
            q = _tet_quality(pts[nt[0]], pts[nt[1]], pts[nt[2]], pts[nt[3]])
            if q < q_new_min:
                q_new_min = q
        if not ok:
            continue
        if q_new_min <= q_old + float(min_quality_improvement):
            continue

        # flip apply.
        alive[ti] = False
        alive[tj] = False
        for nt in new_tets:
            tets_list.append(list(nt))
            alive = np.append(alive, True)
        n_flip += 1
        visited_faces.add(face)

    out = np.asarray(
        [tets_list[i] for i in range(len(tets_list)) if alive[i]],
        dtype=np.int64,
    )
    return out, n_flip


def face_flip_pass(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    n_iter: int = 3,
    max_flips_per_iter: int = 5000,
) -> tuple[np.ndarray, FlipResult]:
    """2-3 flip 을 여러 pass 반복. 업데이트된 tets array 와 FlipResult 반환.

    (3-2 는 edge 기반이라 다음 round 에서 처리.)
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets0 = np.asarray(tets, dtype=np.int64)
    if tets0.size == 0:
        return tets0, FlipResult(0, 0, 0, 0, 0.0, 0.0)

    def _min_quality(T: np.ndarray) -> float:
        qs = [
            _tet_quality(pts[T[i, 0]], pts[T[i, 1]], pts[T[i, 2]], pts[T[i, 3]])
            for i in range(T.shape[0])
        ]
        return min(qs) if qs else 0.0

    q_before = _min_quality(tets0)
    T = tets0
    n_flip_total = 0
    for _ in range(max(1, n_iter)):
        T_new, n = flip_faces_23(pts, T, max_flips=max_flips_per_iter)
        if n == 0:
            break
        T = T_new
        n_flip_total += n
    q_after = _min_quality(T)
    return T, FlipResult(
        n_flip_23=n_flip_total,
        n_flip_32=0,
        n_tets_before=int(tets0.shape[0]),
        n_tets_after=int(T.shape[0]),
        min_quality_before=q_before,
        min_quality_after=q_after,
    )
