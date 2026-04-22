"""OBJ reader — Wavefront OBJ, numpy 기반 자체 구현.

포맷:
    v  x y z [w]       → vertex
    vn nx ny nz        → vertex normal (현재 미사용, 무시)
    vt u v             → vertex texture (현재 미사용, 무시)
    f  v1 v2 v3 [v4]   → face. 각 vi 는:
        v               (position index)
        v/vt            (position + texture)
        v//vn           (position + normal)
        v/vt/vn         (position + texture + normal)
    # comment         → 주석

지원: 1-indexed vertex index (OBJ 표준), 4 각형 face 는 fan triangulation 으로
분할 (v1,v2,v3), (v1,v3,v4).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers.core_mesh import CoreSurfaceMesh


def _parse_face_token(token: str) -> int:
    """OBJ face token (v / v/vt / v//vn / v/vt/vn) 에서 position index 반환 (1-indexed)."""
    idx_str = token.split("/", 1)[0]
    return int(idx_str)


def read_obj(path: str | Path) -> CoreSurfaceMesh:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"OBJ 파일 없음: {p}")

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []  # 0-indexed 로 저장
    with p.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("v "):
                parts = line.split()
                if len(parts) >= 4:
                    vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif line.startswith("f "):
                parts = line.split()
                idxs = [_parse_face_token(t) for t in parts[1:]]
                # 음수 인덱스 (OBJ 는 끝에서부터 상대 인덱스 허용) → 현재 vertex 수 기준
                resolved = [
                    (i - 1) if i > 0 else (len(vertices) + i)
                    for i in idxs
                ]
                if len(resolved) < 3:
                    continue
                # fan triangulation
                v0 = resolved[0]
                for k in range(1, len(resolved) - 1):
                    faces.append((v0, resolved[k], resolved[k + 1]))
            # vn, vt, g, usemtl, s 등은 현재 무시

    V = np.array(vertices, dtype=np.float64) if vertices else np.zeros((0, 3))
    F = np.array(faces, dtype=np.int64) if faces else np.zeros((0, 3), dtype=np.int64)
    return CoreSurfaceMesh(
        vertices=V, faces=F,
        metadata={"format": "obj", "path": str(p)},
    )
