"""AutoTessell 자체 hex-dominant mesh 엔진 (MVP).

v0.4 native-first: snappyHexMesh / cfMesh 의존 없이 순수 Python 으로 bbox 내부
uniform hex grid 를 생성하고 표면 내부에 있는 cell 만 유지한다.

알고리즘 (MVP):
    1. 표면 bbox + 여유 padding 으로 grid 정의.
    2. N×M×K cell vertex 생성 (N+1, M+1, K+1 points).
    3. 각 cell 의 8 vertex 를 OpenFOAM hexa 순서로 정렬.
    4. cell centroid 를 ray-casting inside-test 로 필터링.
    5. 사용된 vertex 만 유지 + 인덱스 압축.
    6. OpenFOAM polyMesh 로 기록 (내부 PolyMeshHexWriter).

제한 사항:
    - 표면에 snap 하지 않음 (cell 경계가 계단 모양).
    - BL 는 native_bl 경로와 별도로 호출 (Phase F 에서 연결 가능).
    - 단일 "defaultWall" patch.

향후 확장:
    - Octree 기반 adaptive refinement (edge intersect 감지).
    - STL 표면 snap (vertex projection).
    - Feature edge 보존.
"""
from __future__ import annotations

from core.generator.native_hex.mesher import (
    NativeHexResult,
    generate_native_hex,
)

__all__ = ["NativeHexResult", "generate_native_hex"]
