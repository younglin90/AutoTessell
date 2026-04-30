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
