"""AutoTessell 자체 L1 표면 수리 (pymeshfix 의존 제거 로드맵).

각 오류 유형별 수리 유틸리티를 모아 놓았고, 고수준 진입점 :func:`run_native_repair`
를 제공한다. v0.4 "Native-First" 철학: pymeshfix / trimesh repair 가 없어도
대부분의 실용 케이스를 해결하는 것이 목표.

현재 구현:
    - dedup_vertices:      좌표 grid 양자화 기반 중복 vertex 병합 + face 리인덱싱
    - remove_degenerate:   면적 < ε 삼각형 제거 + 퇴화된 duplicate face 제거
    - fix_normals:         BFS 기반 face winding 일관성 (최대 component 기준)
    - remove_non_manifold: edge 공유 개수가 3+ 인 면 중 하나 제거 (heuristic)
    - fill_holes:          boundary loop 추출 + fan triangulation

외부 라이브러리 fallback 은 core/preprocessor/repair.py 에 유지.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.preprocessor.native_repair.dedup import dedup_vertices
from core.preprocessor.native_repair.degenerate import remove_degenerate_faces
from core.preprocessor.native_repair.hole_fill import fill_small_holes
from core.preprocessor.native_repair.manifold import remove_non_manifold_faces
from core.preprocessor.native_repair.normals import fix_face_winding


__all__ = [
    "NativeRepairResult",
    "run_native_repair",
    "dedup_vertices",
    "remove_degenerate_faces",
    "fix_face_winding",
    "remove_non_manifold_faces",
    "fill_small_holes",
]


@dataclass
class NativeRepairResult:
    """L1 repair 결과."""

    vertices: np.ndarray
    faces: np.ndarray
    steps: list[dict[str, Any]] = field(default_factory=list)
    watertight: bool | None = None
    manifold: bool | None = None
    # beta2325 — Möller 1997 self-intersect detect 결과 (옵트 캡처).
    n_self_intersect_before: int | None = None
    n_self_intersect_after: int | None = None


def run_native_repair(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    dedup_tol: float = 1e-9,
    degenerate_area_tol: float = 1e-18,
    fill_hole_max_boundary: int = 64,
    fix_normals: bool = True,
    aggressive: int = 1,
) -> NativeRepairResult:
    """L1 표면 수리 파이프라인 — 모든 단계 자체 구현.

    순서:
        1) dedup_vertices (KDTree 계열 병합)
        2) remove_degenerate_faces (면적 작음 + 중복)
        3) remove_non_manifold_faces (edge 가 3+ face 공유 → 1 face 제거)
        4) fill_small_holes (boundary loop ≤ max_boundary → fan)
        5) fix_face_winding (optional — BFS 로 winding 통일)

    Args:
        aggressive: 반복 회수 (default 1). 2+ 시 dedup tol 점진 완화 +
                    파이프라인 다시 적용. 매우 broken 한 self-intersect mesh 용.

    Returns:
        NativeRepairResult. 원본은 변경하지 않음.
    """
    from core.analyzer.topology import is_manifold, is_watertight
    steps: list[dict[str, Any]] = []

    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)

    n_passes = max(1, int(aggressive))
    bbox_diag = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0))) if V.size > 0 else 1.0

    V_cur, F_cur = V, F
    for pass_idx in range(n_passes):
        # aggressive 시 dedup tol 을 bbox 기준 점진 완화 (1e-9 → 1e-6 × diag).
        cur_dedup = dedup_tol if pass_idx == 0 else max(dedup_tol, bbox_diag * (10 ** (pass_idx - 6)))

        V2, F2, ndup = dedup_vertices(V_cur, F_cur, tol=cur_dedup)
        steps.append({"step": f"dedup_vertices_p{pass_idx}", "merged": int(ndup), "tol": cur_dedup})

        F3, ndeg = remove_degenerate_faces(V2, F2, area_tol=degenerate_area_tol)
        steps.append({"step": f"remove_degenerate_faces_p{pass_idx}", "removed": int(ndeg)})

        F4, nnm = remove_non_manifold_faces(F3)
        steps.append({"step": f"remove_non_manifold_faces_p{pass_idx}", "removed": int(nnm)})

        F5, nadd = fill_small_holes(V2, F4, max_boundary=fill_hole_max_boundary)
        steps.append({"step": f"fill_small_holes_p{pass_idx}", "added": int(nadd)})

        if fix_normals:
            F6, nflip = fix_face_winding(V2, F5)
            steps.append({"step": f"fix_face_winding_p{pass_idx}", "flipped": int(nflip)})
        else:
            F6 = F5

        V_cur, F_cur = V2, F6
        # early-stop: pass 결과 이미 watertight + manifold 면 더 안 함.
        if pass_idx + 1 < n_passes:
            try:
                if is_watertight(F_cur) and is_manifold(F_cur):
                    steps.append({"step": f"early_stop_p{pass_idx}", "reason": "wt+mf"})
                    break
            except Exception:
                pass

    # beta2325 — Möller 1997 self-intersect 진단 (before / after).
    # 작은 mesh 만 (≤5000 face) — 큰 mesh 는 KDTree 추가 import 비용 회피.
    n_si_before: int | None = None
    n_si_after: int | None = None
    try:
        if F.shape[0] <= 5000:
            from core.preprocessor.native_repair.self_intersect import (
                detect_self_intersections as _det_si,
            )
            _b = _det_si(V, F, max_pairs_for_o_n_squared=5000)
            _a = _det_si(V_cur, F_cur, max_pairs_for_o_n_squared=5000)
            n_si_before = int(_b.n_intersections)
            n_si_after = int(_a.n_intersections)
    except Exception:
        n_si_before = None
        n_si_after = None

    return NativeRepairResult(
        vertices=V_cur, faces=F_cur, steps=steps,
        watertight=bool(is_watertight(F_cur)),
        manifold=bool(is_manifold(F_cur)),
        n_self_intersect_before=n_si_before,
        n_self_intersect_after=n_si_after,
    )
