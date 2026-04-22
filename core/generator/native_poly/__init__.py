"""AutoTessell 자체 polyhedral mesh 엔진 (MVP).

v0.4 native-first: OpenFOAM polyDualMesh / pyvoro-mm 의존 없이 native_tet 결과를
dual polyhedral 로 변환하거나, scipy Voronoi 로 직접 polyhedral 생성.

MVP 전략 (두 경로):
    1) :func:`native_tet_to_poly_dual`: native_tet 결과 tet polyMesh 를 dual 변환.
       각 tet 의 circumcenter 를 polyhedral vertex, 공유 face 를 edge, 공유 edge
       를 polygonal face 로 삼는다. (계산량: O(n_tets))
    2) :func:`generate_native_poly_voronoi`: bbox 내부 균일 seed point 로
       scipy.spatial.Voronoi 구동, bbox 로 clip 해 polyhedral cell 생성.

본 MVP 는 (2) 경로만 구현한다. (1) 은 향후 확장.
"""
from __future__ import annotations

from core.generator.native_poly.voronoi import (
    NativePolyResult,
    generate_native_poly_voronoi,
)

__all__ = ["NativePolyResult", "generate_native_poly_voronoi"]
