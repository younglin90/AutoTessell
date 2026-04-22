"""AutoTessell 자체 L2 remesh (pyACVD / pymeshlab / geogram 의존 제거 로드맵).

목표: edge length 를 target 에 맞추고 삼각형 품질 (정삼각형에 가까움) 을 향상.

제공:
    isotropic_remesh (Botsch & Kobbelt 2004):
        반복
         1) edge split  (길이 > 4/3 * target)
         2) edge collapse (길이 < 4/5 * target)
         3) edge flip    (vertex valence 6 기준 편차 개선)
         4) tangential relocation (vertex 를 이웃 centroid 로 이동, 표면 사영)

    lloyd_cvt:
        단순화된 CVT (Centroidal Voronoi Tessellation) — 각 vertex 를 인접
        face centroid 의 area-weighted 평균 위치로 이동. 표면 사영은 입력 surface
        기준 KDTree 근사.

두 함수 모두 (vertices, faces) → (vertices, faces) 를 반환한다.
"""
from __future__ import annotations

from core.preprocessor.native_remesh.cvt import lloyd_cvt
from core.preprocessor.native_remesh.isotropic import isotropic_remesh


__all__ = ["isotropic_remesh", "lloyd_cvt"]
