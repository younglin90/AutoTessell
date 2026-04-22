"""AutoTessell 자체 tet mesh 엔진 (MVP).

v0.4 native-first: TetWild/fTetWild/Netgen 의존 없이 순수 Python 으로 closed
watertight 표면 메쉬를 부피 tet mesh 로 변환한다.

알고리즘 (MVP):
    1. 입력 vertex + bbox 내부 uniform grid 시드 포인트로 scipy.spatial.Delaunay
       구동 → 초기 tet.
    2. 각 tet centroid 가 표면 내부에 있는지 winding-number (ray casting) 로 판정,
       외부 tet 제거.
    3. 남은 tet 을 PolyMeshWriter 로 constant/polyMesh 에 기록.

제한 사항 (향후 개선 대상):
    - envelope 보존이 strict 하지 않음 (surface fidelity 는 대략)
    - boundary preservation (원 STL vertex 가 결과 mesh 에 있도록) 은 Delaunay 에
      입력 vertex 를 포함하지만 topology 가 변할 수 있음
    - 경계 patch 이름은 "defaultWall" 하나로 통합 (원본 patch 정보 없음)
    - epsilon / stop_energy 등의 TetWild 파라미터는 없음
"""
from __future__ import annotations

from core.generator.native_tet.mesher import (
    NativeTetResult,
    generate_native_tet,
)


__all__ = ["NativeTetResult", "generate_native_tet"]
