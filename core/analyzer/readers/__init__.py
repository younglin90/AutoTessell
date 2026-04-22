"""AutoTessell 자체 표면 메쉬 reader 모음 (trimesh 의존 제거 로드맵).

v0.4 "Native-First" 철학에 따라 외부 라이브러리 (trimesh, meshio, pyvista) 의존을
점진적으로 제거하고, 각 파일 포맷 명세를 우리 코드로 직접 파싱한다.

공통 반환 타입: CoreSurfaceMesh (numpy 기반 경량 dataclass).

지원 포맷 (현재):
    - STL (binary + ASCII)
    - OBJ (v / f / vn)
    - PLY (ASCII + binary little/big endian)
    - OFF

외부 reader 와의 parity 는 tests/test_native_readers.py 에서 교차 검증한다.
"""
from __future__ import annotations

from core.analyzer.readers.core_mesh import CoreSurfaceMesh
from core.analyzer.readers.obj import read_obj
from core.analyzer.readers.off import read_off
from core.analyzer.readers.ply import read_ply
from core.analyzer.readers.stl import read_stl


__all__ = [
    "CoreSurfaceMesh",
    "read_stl",
    "read_obj",
    "read_ply",
    "read_off",
]
