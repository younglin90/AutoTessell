"""STL reader — binary + ASCII, numpy 기반 자체 구현.

포맷 스펙:
  Binary: 80-byte header + uint32 triangle_count + N × (normal(3f32) + v1(3f32) +
          v2(3f32) + v3(3f32) + uint16 attribute_bytes) = 50 bytes/triangle.
  ASCII:  "solid NAME\\n  facet normal nx ny nz\\n  outer loop\\n    vertex ...\\n
          endloop\\n  endfacet\\n..."

Binary 감지: header 의 "solid" 문자열 여부만으론 부족 (일부 binary 가 "solid" 로
시작). 대신 "파일 크기 == 84 + 50 × triangle_count" 여부를 체크하여 binary 로
확정, 아니면 ASCII 로 fallback.

Vertex 병합:
    STL 은 face 당 vertex 가 독립 저장되므로 중복 좌표가 많다. 옵션으로 (기본 on)
    KDTree 기반 좌표 근접 병합을 수행하여 shared vertex 형태로 반환.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from core.analyzer.readers.core_mesh import CoreSurfaceMesh


def _is_binary_stl(path: Path) -> bool:
    """파일 크기로 binary STL 여부 판정 (가장 신뢰성 있는 방법)."""
    size = path.stat().st_size
    if size < 84:
        return False
    with path.open("rb") as f:
        header = f.read(84)
    n_tri = struct.unpack_from("<I", header, 80)[0]
    expected = 84 + 50 * n_tri
    return size == expected


def _dedupe_vertices(
    raw_verts: np.ndarray, tol: float = 1e-9,
) -> tuple[np.ndarray, np.ndarray]:
    """좌표가 거의 같은 vertex 를 병합해 (unique_verts, remap) 반환.

    raw_verts: (3F, 3) — face 당 3 vertex 를 펼친 형태.
    remap: (3F,) — raw_verts[i] → unique_verts[remap[i]].

    tol 을 정수 grid 로 양자화해 dict 기반 unique 를 사용한다. KDTree 대비 간단
    하고 빠르다 (tol 이 양자화 단위).
    """
    if raw_verts.size == 0:
        return raw_verts.reshape(0, 3), np.zeros(0, dtype=np.int64)
    # 정수 grid 로 양자화 (symmetric rounding)
    scale = 1.0 / max(tol, 1e-30)
    keys = np.round(raw_verts * scale).astype(np.int64)
    # sort + unique
    # view as structured key for hashing
    view = np.ascontiguousarray(keys).view([("x", np.int64), ("y", np.int64), ("z", np.int64)])
    _, unique_idx, inverse = np.unique(view, return_index=True, return_inverse=True)
    unique_verts = raw_verts[unique_idx]
    return unique_verts, inverse


def _read_binary_stl(path: Path, dedupe: bool, tol: float) -> CoreSurfaceMesh:
    with path.open("rb") as f:
        header_bytes = f.read(80)
        n_tri = struct.unpack("<I", f.read(4))[0]
        # 각 triangle = 12 floats + uint16 attribute = 50 bytes
        dtype = np.dtype([
            ("normal", "<f4", 3),
            ("v0", "<f4", 3),
            ("v1", "<f4", 3),
            ("v2", "<f4", 3),
            ("attr", "<u2"),
        ])
        data = np.frombuffer(f.read(n_tri * 50), dtype=dtype, count=n_tri)

    if n_tri == 0:
        return CoreSurfaceMesh(
            vertices=np.zeros((0, 3)), faces=np.zeros((0, 3), dtype=np.int64),
            metadata={"format": "stl_binary", "header": header_bytes, "path": str(path)},
        )

    raw = np.stack([data["v0"], data["v1"], data["v2"]], axis=1).reshape(-1, 3).astype(np.float64)
    if dedupe:
        verts, inverse = _dedupe_vertices(raw, tol=tol)
        faces = inverse.reshape(-1, 3).astype(np.int64)
    else:
        verts = raw
        faces = np.arange(3 * n_tri, dtype=np.int64).reshape(-1, 3)

    return CoreSurfaceMesh(
        vertices=verts, faces=faces,
        metadata={
            "format": "stl_binary",
            "header": header_bytes.rstrip(b"\x00"),
            "path": str(path),
            "n_triangles": int(n_tri),
        },
    )


def _read_ascii_stl(path: Path, dedupe: bool, tol: float) -> CoreSurfaceMesh:
    verts: list[tuple[float, float, float]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("vertex "):
                parts = s.split()
                if len(parts) >= 4:
                    verts.append((float(parts[1]), float(parts[2]), float(parts[3])))

    if len(verts) % 3 != 0:
        raise ValueError(
            f"ASCII STL vertex 수 {len(verts)} 가 3 의 배수가 아님"
        )
    raw = np.array(verts, dtype=np.float64)
    n_tri = raw.shape[0] // 3
    if dedupe:
        uverts, inverse = _dedupe_vertices(raw, tol=tol)
        faces = inverse.reshape(-1, 3).astype(np.int64)
    else:
        uverts = raw
        faces = np.arange(3 * n_tri, dtype=np.int64).reshape(-1, 3)

    return CoreSurfaceMesh(
        vertices=uverts, faces=faces,
        metadata={"format": "stl_ascii", "path": str(path), "n_triangles": n_tri},
    )


def read_stl(
    path: str | Path,
    *,
    dedupe: bool = True,
    tol: float = 1e-9,
) -> CoreSurfaceMesh:
    """STL 파일 (binary 또는 ASCII) 을 로드해 CoreSurfaceMesh 반환.

    Args:
        path: STL 파일 경로.
        dedupe: True 면 좌표가 거의 같은 vertex 를 병합 (trimesh 의 merge_vertices
            와 유사). False 면 face 당 3 vertex 를 독립 저장 (3F vertex).
        tol: dedupe 허용 오차 (좌표 grid 양자화 단위).

    Returns:
        CoreSurfaceMesh.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"STL 파일 없음: {p}")
    if _is_binary_stl(p):
        return _read_binary_stl(p, dedupe, tol)
    return _read_ascii_stl(p, dedupe, tol)
