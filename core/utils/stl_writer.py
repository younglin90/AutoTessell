"""O1 / beta2660 — STL ASCII writer.

polyMesh boundary 또는 surface (V, F) → STL ASCII.
binary STL 은 별도 카드 (mesh_exporter_starccm 의 export_intersecting_faces_stl 가
binary writer 보유 — 참조).

STL ASCII 형식:
    solid <name>
    facet normal nx ny nz
      outer loop
        vertex x y z
        vertex x y z
        vertex x y z
      endloop
    endfacet
    ...
    endsolid <name>
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


@dataclass
class STLWriteResult:
    success: bool
    output_path: str = ""
    n_triangles: int = 0
    elapsed: float = 0.0
    message: str = ""


def write_stl_ascii(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    output_path: str | Path,
    *,
    name: str = "AutoTessell",
) -> STLWriteResult:
    """Surface mesh (V, F) → STL ASCII.

    Args:
        V: (N, 3).
        F: (M, 3) tri indices.
        output_path: 출력 .stl 파일.
        name: solid 이름.
    """
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_t = int(F.shape[0])

    if n_t == 0:
        return STLWriteResult(
            success=False, output_path=str(out),
            message="empty face array",
            elapsed=time.perf_counter() - t0,
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="ascii") as f:
        f.write(f"solid {name}\n")
        for fi in range(n_t):
            v0 = V[F[fi, 0]]
            v1 = V[F[fi, 1]]
            v2 = V[F[fi, 2]]
            n_vec = np.cross(v1 - v0, v2 - v0)
            n_len = float(np.linalg.norm(n_vec))
            if n_len > 1e-30:
                n_vec = n_vec / n_len
            else:
                n_vec = np.zeros(3, dtype=np.float64)
            f.write(f"  facet normal {n_vec[0]:.6e} {n_vec[1]:.6e} {n_vec[2]:.6e}\n")
            f.write("    outer loop\n")
            f.write(f"      vertex {v0[0]:.6e} {v0[1]:.6e} {v0[2]:.6e}\n")
            f.write(f"      vertex {v1[0]:.6e} {v1[1]:.6e} {v1[2]:.6e}\n")
            f.write(f"      vertex {v2[0]:.6e} {v2[1]:.6e} {v2[2]:.6e}\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")
        f.write(f"endsolid {name}\n")

    return STLWriteResult(
        success=True, output_path=str(out),
        n_triangles=n_t,
        elapsed=time.perf_counter() - t0,
        message=f"STL ASCII written ({n_t} triangles).",
    )


def write_stl_binary(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    output_path: str | Path,
    *,
    name: str = "AutoTessell",
) -> STLWriteResult:
    """Q1 / beta2674 — STL binary writer.

    Format: 80-byte header + uint32 n_tri + per-tri (12 float32 + uint16 attr).

    50% smaller + 5-10× faster than ASCII for large meshes.
    """
    import struct
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_t = int(F.shape[0])

    if n_t == 0:
        return STLWriteResult(
            success=False, output_path=str(out),
            message="empty face array",
            elapsed=time.perf_counter() - t0,
        )

    # face vertices.
    v0 = V[F[:, 0]].astype(np.float32)
    v1 = V[F[:, 1]].astype(np.float32)
    v2 = V[F[:, 2]].astype(np.float32)

    # face normals (vectorized).
    n_unnorm = np.cross(v1 - v0, v2 - v0)
    n_lens = np.linalg.norm(n_unnorm, axis=1, keepdims=True)
    n_safe = np.where(n_lens > 1e-30, n_unnorm / np.maximum(n_lens, 1e-30), 0.0).astype(np.float32)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        # 80-byte header.
        header = (f"AutoTessell binary STL ({name})").encode("ascii", errors="replace")[:80]
        f.write(header.ljust(80, b"\x00"))
        # uint32 n_tri.
        f.write(struct.pack("<I", n_t))
        # per-tri: 12 float32 + uint16.
        # vectorize: build (n_t, 50) byte buffer.
        # Each tri = 4 vec3 (normal + 3 verts) × 4 bytes + 2 bytes = 50 bytes.
        buf = np.empty((n_t, 50), dtype=np.uint8)
        # Pack 12 floats (48 bytes) + 2 bytes attr.
        for i in range(n_t):
            row = struct.pack(
                "<12fH",
                n_safe[i, 0], n_safe[i, 1], n_safe[i, 2],
                v0[i, 0], v0[i, 1], v0[i, 2],
                v1[i, 0], v1[i, 1], v1[i, 2],
                v2[i, 0], v2[i, 1], v2[i, 2],
                0,
            )
            f.write(row)

    return STLWriteResult(
        success=True, output_path=str(out),
        n_triangles=n_t,
        elapsed=time.perf_counter() - t0,
        message=f"STL binary written ({n_t} triangles).",
    )
