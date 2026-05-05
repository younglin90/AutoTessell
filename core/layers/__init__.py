"""AutoTessell 자체 Boundary Layer (BL) 생성 엔진.

공개 API:
    generate_native_bl(case_dir, ...) — polyMesh 에 prism BL 추가
    compute_vertex_normals(points, faces, wall_face_idx) — area-weighted normals
"""
from core.layers.native_bl import (  # noqa: F401
    BLConfig,
    NativeBLResult,
    generate_native_bl,
)
