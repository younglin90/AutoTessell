"""Phase C2 — Envelope-based surface preservation.

fTetWild 의 핵심 아이디어: 입력 표면 주변 ε-envelope 을 정의하고, 메쉬
operation (flip/smooth/split/collapse) 후 boundary 가 envelope 을 벗어나면
해당 operation 을 reject (이전 상태 복원).

이로써 최종 tet mesh 의 boundary 가 입력 surface 에서 ε 이하의 Hausdorff
거리를 갖도록 보장.

구현 요약
    - TriangleBVH (core/utils/aabb.py) 로 점→표면 거리 O(log F).
    - boundary tet 의 surface vertex 가 envelope 밖이면 violation.
    - proposed operation 테스트 시, 새 boundary vertex 위치를 모두 검사.

레퍼런스
    - Hu et al. 2020 (fTetWild, MPL-2.0) §3.3 "Envelope".
    - Wang et al. 2020 "Exact and Efficient Polyhedral Envelope Containment Check".
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.utils.aabb import TriangleBVH


@dataclass
class Envelope:
    bvh: TriangleBVH
    eps: float

    @classmethod
    def build(
        cls, V: np.ndarray, F: np.ndarray, *, eps_relative: float = 0.001,
    ) -> "Envelope":
        """입력 surface 로 envelope 구성.

        Args:
            V, F: surface mesh.
            eps_relative: bbox 대각선에 대한 비율 (기본 0.1%).
        """
        V = np.asarray(V, dtype=np.float64)
        F = np.asarray(F, dtype=np.int64)
        if V.shape[0] > 0:
            diag = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0)))
        else:
            diag = 1.0
        eps = diag * float(eps_relative)
        return cls(bvh=TriangleBVH.build(V, F), eps=eps)

    def contains_point(self, p: np.ndarray) -> bool:
        _cp, d, _ti = self.bvh.closest_point(np.asarray(p, dtype=np.float64))
        return d <= self.eps

    def contains_points(self, pts: np.ndarray) -> np.ndarray:
        d = self.bvh.unsigned_distances(np.asarray(pts, dtype=np.float64))
        return d <= self.eps

    def project(self, p: np.ndarray) -> np.ndarray:
        """p 를 envelope 안 (가장 가까운 표면 점) 으로 projection."""
        cp, _d, _ = self.bvh.closest_point(np.asarray(p, dtype=np.float64))
        return cp


def check_operation(
    envelope: Envelope,
    proposed_surface_points: np.ndarray,
) -> tuple[bool, float]:
    """operation 후 모든 surface vertex 가 envelope 내에 있는지 검증.

    Returns:
        (ok, max_distance).
        ok = all vertices 가 envelope 안. max_distance = 가장 멀어진 점의 표면
        거리.
    """
    pts = np.asarray(proposed_surface_points, dtype=np.float64)
    if pts.size == 0:
        return True, 0.0
    d = envelope.bvh.unsigned_distances(pts)
    mx = float(d.max())
    return (mx <= envelope.eps), mx
