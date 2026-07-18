"""CARD BOOLMERGE2 — tet centroid union-filter 격리 헬퍼.

fTetWild §3.6(``papers/md/02_hu_2020_ftetwild.md:487-491``)은 각 tracked input
surface 의 winding number 를 tet centroid 에서 **독립적으로** 계산한 뒤 boolean
결합으로 keep 여부를 정한다 — "e.g. intersecting -> keep tets inside both".
즉 union=OR, intersection=AND, difference=AND-NOT 은 동일한 per-surface bool
배열 + reduce 패턴이다. 본 카드는 그 중 **union 만** ``(pts, tets)`` 도메인으로
리프트한 순수 필터를 제공한다. intersection/difference 는 패턴이 동일하지만
현재 호출자가 없어 (스타일 규칙상 dead code 회피) 후속 카드로 미룬다.

CARD BOOLMERGE1(``core/utils/geometry.inside_union_winding_number``)이 만든
점별 union 판정을 재사용할 뿐, 이 모듈은 새로운 inside-test 를 구현하지 않는다.
원본 입력 삼각형은 판정에만 쓰이고 절대 수정되지 않으므로 표면보존 불변식
(invariant 1)이 구조적으로 보장된다.

**호출자 없음 — 순수 격리 헬퍼.** mesher.py / orchestrator / server 어디에도
배선되지 않는다. 다중-surface 배선은 CARD BOOLMERGE3 이후 범위.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class UnionMergeResult:
    n_tets_before: int
    n_tets_after: int
    n_dropped: int
    volume_after: float


def _tets_volume(pts: np.ndarray, tets: np.ndarray) -> float:
    """Sum(|signed vol6|) / 6 — native_tet 코드베이스 관례(validate.signed_volume6)."""
    from core.generator.native_tet.validate import signed_volume6

    if tets.size == 0:
        return 0.0
    vol6 = signed_volume6(pts, tets)
    return float(np.abs(vol6).sum() / 6.0)


def filter_tets_to_union(
    pts: np.ndarray,
    tets: np.ndarray,
    surfaces: list[tuple[np.ndarray, np.ndarray]],
    *,
    threshold: float = 0.5,
) -> tuple[np.ndarray, np.ndarray, UnionMergeResult]:
    """centroid 가 어느 입력 surface 의 union 내부에도 없는 tet 을 제거.

    각 tet 의 centroid 에 ``inside_union_winding_number``(BOOLMERGE1)를 적용해
    keep 판정한다 — surface-level CSG 없이 volume-level 필터만 수행한다.

    Args:
        pts: (Np, 3) tet mesh vertex 좌표. **수정되지 않는다** — 반환값에
            그대로 포함되어 표면보존 불변식을 구조적으로 보장한다.
        tets: (Nt, 4) tet vertex index.
        surfaces: ``(V_i, F_i)`` 쌍 리스트. union 대상 입력 surface 들.
        threshold: 0.5 default — 개별 surface GWN 판정 임계값.

    Returns:
        ``(pts, kept_tets, UnionMergeResult)``. ``tets``/``surfaces`` 가 비어
        있으면 원본을 그대로 반환한다(``boundary_clip.py`` 관례와 일치).
    """
    from core.utils.geometry import inside_union_winding_number

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)

    n_before = int(tets.shape[0])

    if tets.size == 0 or not surfaces:
        volume_after = _tets_volume(pts, tets)
        return pts, tets, UnionMergeResult(
            n_tets_before=n_before,
            n_tets_after=n_before,
            n_dropped=0,
            volume_after=volume_after,
        )

    centroids = pts[tets].mean(axis=1)
    keep = inside_union_winding_number(centroids, surfaces, threshold=threshold)
    kept = tets[keep]
    volume_after = _tets_volume(pts, kept)

    return pts, kept, UnionMergeResult(
        n_tets_before=n_before,
        n_tets_after=int(kept.shape[0]),
        n_dropped=int((~keep).sum()),
        volume_after=volume_after,
    )
