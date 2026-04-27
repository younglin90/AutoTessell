"""OFF reader (Object File Format).

포맷:
    OFF
    V F E
    x0 y0 z0
    ...
    n v0 v1 ... v(n-1)
    ...

지원: triangle + polygon (fan triangulation). color 토큰 (face 뒤 RGBA) 은 무시.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers.core_mesh import CoreSurfaceMesh


def read_off(path: str | Path) -> CoreSurfaceMesh:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"OFF 파일 없음: {p}")

    with p.open("r", encoding="utf-8", errors="replace") as f:
        # magic (OFF / NOFF / COFF / STOFF...). 첫 줄 시작이 *OFF
        first = f.readline().strip()
        if not first.upper().endswith("OFF"):
            raise ValueError(f"OFF magic 불일치: {first!r}")

        # 빈 줄 / 주석 건너뛰기
        def _next_data_line() -> str:
            while True:
                line = f.readline()
                if not line:
                    raise ValueError("OFF 헤더 예상치 못한 EOF")
                s = line.strip()
                if s and not s.startswith("#"):
                    return s

        counts = _next_data_line().split()
        if len(counts) < 2:
            raise ValueError(f"OFF counts 라인 오류: {counts}")
        V = int(counts[0]); Fn = int(counts[1])  # E 는 무시

        # --- vectorized vertex read ---
        raw_lines = [_next_data_line() for _ in range(V)]
        vertices = np.array(
            [line.split()[:3] for line in raw_lines], dtype=np.float64
        ) if V else np.zeros((0, 3), dtype=np.float64)

        # --- face read: fast-path for all-triangle meshes ---
        face_lines = [_next_data_line() for _ in range(Fn)]
        all_tri = all(line.split()[0] == "3" for line in face_lines) if face_lines else True
        if all_tri and face_lines:
            faces_out = np.array(
                [line.split()[1:4] for line in face_lines], dtype=np.int64
            )
        else:
            tris: list[list[int]] = []
            for line in face_lines:
                toks = line.split()
                n = int(toks[0])
                idx = np.array(toks[1 : 1 + n], dtype=np.int64)
                for k in range(1, n - 1):
                    tris.append([idx[0], idx[k], idx[k + 1]])
            faces_out = np.array(tris, dtype=np.int64) if tris else np.zeros((0, 3), dtype=np.int64)

    return CoreSurfaceMesh(
        vertices=vertices, faces=faces_out,
        metadata={"format": "off", "path": str(p)},
    )
