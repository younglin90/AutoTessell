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


def run_native_repair(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    dedup_tol: float = 1e-9,
    degenerate_area_tol: float = 1e-18,
    fill_hole_max_boundary: int = 64,
    fix_normals: bool = True,
) -> NativeRepairResult:
    """L1 표면 수리 파이프라인 — 모든 단계 자체 구현.

    순서:
        1) dedup_vertices (KDTree 계열 병합)
        2) remove_degenerate_faces (면적 작음 + 중복)
        3) remove_non_manifold_faces (edge 가 3+ face 공유 → 1 face 제거)
        4) fill_small_holes (boundary loop ≤ max_boundary → fan)
        5) fix_face_winding (optional — BFS 로 winding 통일)

    Returns:
        NativeRepairResult. 원본은 변경하지 않음.
    """
    from core.analyzer.topology import is_manifold, is_watertight
    steps: list[dict[str, Any]] = []

    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)

    # 1) dedup
    V2, F2, ndup = dedup_vertices(V, F, tol=dedup_tol)
    steps.append({"step": "dedup_vertices", "merged": int(ndup)})

    # 2) degenerate
    F3, ndeg = remove_degenerate_faces(V2, F2, area_tol=degenerate_area_tol)
    steps.append({"step": "remove_degenerate_faces", "removed": int(ndeg)})

    # 3) non-manifold
    F4, nnm = remove_non_manifold_faces(F3)
    steps.append({"step": "remove_non_manifold_faces", "removed": int(nnm)})

    # 4) hole fill
    F5, nadd = fill_small_holes(V2, F4, max_boundary=fill_hole_max_boundary)
    steps.append({"step": "fill_small_holes", "added": int(nadd)})

    # 5) winding
    if fix_normals:
        F6, nflip = fix_face_winding(V2, F5)
        steps.append({"step": "fix_face_winding", "flipped": int(nflip)})
    else:
        F6 = F5

    return NativeRepairResult(
        vertices=V2, faces=F6, steps=steps,
        watertight=bool(is_watertight(F6)),
        manifold=bool(is_manifold(F6)),
    )
