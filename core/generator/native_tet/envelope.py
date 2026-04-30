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
    def build_auto_eps(
        cls, V: np.ndarray, F: np.ndarray,
        *, base_ratio: float = 0.001,
        min_feature_factor: float = 0.05,
    ) -> "Envelope":
        """beta1250 (R135) — eps 를 입력 feature 분포 기반 자동 산정.

        eps = max(bbox_diag × base_ratio, shortest_edge × min_feature_factor).
        """
        V = np.asarray(V, dtype=np.float64)
        F = np.asarray(F, dtype=np.int64)
        if V.shape[0] == 0:
            return cls(bvh=TriangleBVH.build(V, F), eps=1e-6)
        diag = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0)))
        base = diag * float(base_ratio)
        if F.shape[0] > 0:
            e1 = np.linalg.norm(V[F[:, 1]] - V[F[:, 0]], axis=1)
            e2 = np.linalg.norm(V[F[:, 2]] - V[F[:, 1]], axis=1)
            e3 = np.linalg.norm(V[F[:, 0]] - V[F[:, 2]], axis=1)
            shortest = float(np.minimum.reduce([e1, e2, e3]).min())
        else:
            shortest = diag
        feat = shortest * float(min_feature_factor)
        eps = max(base, feat)
        return cls(bvh=TriangleBVH.build(V, F), eps=eps)

    def relax_eps(self, factor: float = 1.5) -> "Envelope":
        """beta1260 (R136) — envelope eps 를 factor 배로 완화 (새 인스턴스)."""
        return Envelope(bvh=self.bvh, eps=self.eps * float(factor))

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
        # E3 / beta2598 — env-gated GPU fast-path.
        # AUTO_TESSELL_GPU_ENVELOPE=1 → torch.compile + Eberly fused kernel.
        # 50-100× speedup target (CUDA + fp16). 실패 / torch 미가용 시
        # CPU BVH path 자동 fallback.
        try:
            import os as _os_e3
            if _os_e3.environ.get("AUTO_TESSELL_GPU_ENVELOPE", "0") == "1":
                return self._contains_points_gpu(pts)
        except Exception:
            pass
        d = self.bvh.unsigned_distances(np.asarray(pts, dtype=np.float64))
        return d <= self.eps

    def _contains_points_gpu(self, pts: np.ndarray) -> np.ndarray:
        """GPU 가속 envelope check (Eberly + torch.compile)."""
        try:
            from core.generator.native_ai.gpu_envelope import (
                gpu_envelope_check_accurate,
            )
            # BVH 의 V/F 를 직접 사용해 surf array 추출.
            surf_V = np.asarray(self.bvh.V, dtype=np.float64)
            surf_F = np.asarray(self.bvh.F, dtype=np.int64)
            inside, r = gpu_envelope_check_accurate(
                np.asarray(pts, dtype=np.float64),
                surf_V, surf_F, float(self.eps),
                use_fp16=False,  # fp32 default — sliver 정확.
            )
            if r.success:
                return inside
        except Exception:
            pass
        # GPU 실패 → CPU fallback.
        d = self.bvh.unsigned_distances(np.asarray(pts, dtype=np.float64))
        return d <= self.eps

    def project(self, p: np.ndarray) -> np.ndarray:
        """p 를 envelope 안 (가장 가까운 표면 점) 으로 projection."""
        cp, _d, _ = self.bvh.closest_point(np.asarray(p, dtype=np.float64))
        return cp

    def heal_violations(self, pts: np.ndarray) -> tuple[np.ndarray, int]:
        """beta1270 (R137) — envelope 바깥 vertex 를 가장 가까운 valid 위치로.

        Returns: (pts_new, n_healed).
        """
        pts = np.asarray(pts, dtype=np.float64).copy()
        d = self.bvh.unsigned_distances(pts)
        bad = d > self.eps
        if not bad.any():
            return pts, 0
        cps, _, _ = self.bvh.closest_points_all_shared(pts[bad])
        pts[bad] = cps
        return pts, int(bad.sum())


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
