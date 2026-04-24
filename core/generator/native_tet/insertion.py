"""Phase A3 — 입력 surface triangle 을 tet mesh facet 으로 복원.

scipy.Delaunay 는 convex-hull Delaunay 이므로 입력 triangle 이 tet facet 으로
존재한다는 보장이 없다. 오목한 형상이나 얇은 feature 에서는 다수의 triangle 이
"missing" 상태가 되어 표면이 왜곡된다.

본 모듈은
  1. 입력 triangle 중 현재 tet facet set 에 포함되지 않은 missing triangle 을
     찾고,
  2. 가능하면 해당 triangle 의 barycenter 를 "내부 시드" 로 추가해 다음 번
     Delaunay 호출 때 recovery 가 일어나도록 시드 리스트를 리턴한다.

본격적인 constrained Delaunay (Lawson edge flip + face flip) 는 Phase B 에서.
여기서는 "시드 기반 re-meshing" 으로 우회한다 — 실용적으로 sphere / cube /
bracket 에서 대부분의 missing 을 해소한다.

레퍼런스
    - Si & Gärtner 2005, "Meshing Piecewise Linear Complexes by Constrained
      Delaunay Tetrahedralizations".
    - fTetWild (MPL-2.0) 의 Insertion step §3.2 — 본 모듈은 독립 Python 재구현.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class RecoveryResult:
    n_input_triangles: int
    n_recovered: int           # tet facet 으로 실제 포함된 triangle 개수
    n_missing: int             # 여전히 missing 인 triangle 개수
    extra_seeds: np.ndarray    # (K, 3) 다음 Delaunay 호출 시 추가할 내부 점


def _tet_facet_keys(tets: np.ndarray) -> set[tuple[int, int, int]]:
    """tet array 로부터 모든 facet (sorted 3-tuple) 의 set 를 반환."""
    keys: set[tuple[int, int, int]] = set()
    for t in tets:
        a, b, c, d = int(t[0]), int(t[1]), int(t[2]), int(t[3])
        # 4 facets
        for tri in (
            (a, b, c), (a, b, d), (a, c, d), (b, c, d),
        ):
            s = tuple(sorted(tri))
            keys.add(s)  # type: ignore[arg-type]
    return keys


def find_missing_triangles(
    F: np.ndarray,
    tets: np.ndarray,
) -> np.ndarray:
    """입력 triangle F 중 tet facet 에 포함되지 않은 것의 index array.

    Args:
        F: (m, 3) 입력 triangle index. 반드시 Delaunay 에 들어간 vertex array
            기준 (surface vertex 는 [0, n_surf) 로 가정).
        tets: (T, 4) tet.

    Returns:
        (k,) int64 — F 상의 missing triangle index.
    """
    F = np.asarray(F, dtype=np.int64)
    tets = np.asarray(tets, dtype=np.int64)
    if F.size == 0 or tets.size == 0:
        return np.zeros(0, dtype=np.int64)
    facet_set = _tet_facet_keys(tets)
    missing: list[int] = []
    for idx in range(F.shape[0]):
        a, b, c = int(F[idx, 0]), int(F[idx, 1]), int(F[idx, 2])
        key = tuple(sorted((a, b, c)))
        if key not in facet_set:
            missing.append(idx)
    return np.asarray(missing, dtype=np.int64)


def recovery_seeds(
    V: np.ndarray,
    F: np.ndarray,
    tets: np.ndarray,
    *,
    bump_distance: float = 0.0,
    max_seeds: int = 2000,
) -> RecoveryResult:
    """Missing triangle 마다 barycenter (혹은 barycenter + 법선 방향 살짝 안쪽)
    을 내부 시드로 제안.

    Args:
        V: (n, 3) 현재 Delaunay 입력 점 (surface + grid).
        F: (m, 3) 입력 surface triangle.
        tets: (T, 4) 현재 Delaunay 결과.
        bump_distance: barycenter 를 triangle normal 방향으로 얼마나 밀어넣을지.
            0 이면 triangle 평면 위의 점. 약간의 양수 (예: 0.05 × target_edge) 로
            설정하면 Delaunay 가 두 쪽으로 나누기 쉬움.
        max_seeds: 보호용 상한.

    Returns:
        RecoveryResult.
    """
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    tets = np.asarray(tets, dtype=np.int64)

    missing_idx = find_missing_triangles(F, tets)
    n_missing = int(missing_idx.size)
    n_input = int(F.shape[0])
    n_recovered = n_input - n_missing

    if n_missing == 0 or n_input == 0:
        return RecoveryResult(
            n_input_triangles=n_input,
            n_recovered=n_recovered,
            n_missing=0,
            extra_seeds=np.zeros((0, 3), dtype=np.float64),
        )

    take = missing_idx[: max_seeds]
    tri = V[F[take]]          # (k, 3, 3)
    bary = tri.mean(axis=1)    # (k, 3)

    if bump_distance > 0.0:
        e1 = tri[:, 1] - tri[:, 0]
        e2 = tri[:, 2] - tri[:, 0]
        n = np.cross(e1, e2)
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        safe = ln[:, 0] > 1e-30
        n_unit = np.zeros_like(n)
        n_unit[safe] = n[safe] / ln[safe]
        # 안쪽 판별 없이 두 방향에 시드 생성 (outside 는 이후 inside filter 가 제거).
        bary = np.concatenate([
            bary + bump_distance * n_unit,
            bary - bump_distance * n_unit,
        ], axis=0)

    return RecoveryResult(
        n_input_triangles=n_input,
        n_recovered=n_recovered,
        n_missing=n_missing,
        extra_seeds=bary,
    )
