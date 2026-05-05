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

    # OBJ_READER_VEC: batch-collect v/f lines then vectorize vertex parse.
    v_lines: list[str] = []
    face_tokens: list[list[str]] = []  # parts[1:] for each f line
    # track vertex count at each f-line for negative-index resolution
    vert_count_at_face: list[int] = []

    with p.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            if raw[0:2] == "v ":
                v_lines.append(raw)
            elif raw[0:2] == "f ":
                vert_count_at_face.append(len(v_lines))
                face_tokens.append(raw.split()[1:])
            # vn, vt, g, usemtl, s 등은 무시

    # --- Vectorized vertex parse ---
    if v_lines:
        # Extract x y z columns (col 1,2,3) via numpy; ignore optional w.
        # Split all lines at once using numpy string operations.
        # Each line: "v x y z[\n]"  — split on whitespace, take cols 1-3.
        arr = np.array(
            [ln.split()[1:4] for ln in v_lines], dtype=np.float64
        )  # (N,3)
        V = arr
    else:
        V = np.zeros((0, 3), dtype=np.float64)

    n_verts = V.shape[0]

    # --- Face parse (per-line; tokens need split on '/') ---
    faces: list[tuple[int, int, int]] = []
    for fi, parts in enumerate(face_tokens):
        vc = vert_count_at_face[fi]
        idxs = [_parse_face_token(t) for t in parts]
        resolved = [(i - 1) if i > 0 else (vc + i) for i in idxs]
        if len(resolved) < 3:
            continue
        v0 = resolved[0]
        for k in range(1, len(resolved) - 1):
            faces.append((v0, resolved[k], resolved[k + 1]))

    F = np.array(faces, dtype=np.int64) if faces else np.zeros((0, 3), dtype=np.int64)
    return CoreSurfaceMesh(
        vertices=V, faces=F,
        metadata={"format": "obj", "path": str(p), "n_vertices": n_verts},
    )
