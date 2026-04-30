"""O2 / beta2661 — OBJ + PLY surface writer.

OBJ: simple Wavefront text format (v / f).
PLY: ASCII Stanford polygon format.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


@dataclass
class SurfaceWriteResult:
    success: bool
    output_path: str = ""
    n_vertices: int = 0
    n_faces: int = 0
    elapsed: float = 0.0
    message: str = ""


def write_obj(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    output_path: str | Path,
) -> SurfaceWriteResult:
    """Surface mesh → OBJ (Wavefront)."""
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_v = int(V.shape[0])
    n_f = int(F.shape[0])

    if n_v == 0 or n_f == 0:
        return SurfaceWriteResult(
            success=False, output_path=str(out),
            message="empty mesh",
            elapsed=time.perf_counter() - t0,
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="ascii") as f:
        f.write(f"# OBJ written by AutoTessell (O2/beta2661)\n")
        for v in V:
            f.write(f"v {v[0]:.6e} {v[1]:.6e} {v[2]:.6e}\n")
        for face in F:
            # 1-based.
            idx = " ".join(str(int(i) + 1) for i in face)
            f.write(f"f {idx}\n")

    return SurfaceWriteResult(
        success=True, output_path=str(out),
        n_vertices=n_v, n_faces=n_f,
        elapsed=time.perf_counter() - t0,
        message=f"OBJ written ({n_v} vertices, {n_f} faces).",
    )


def write_ply(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    output_path: str | Path,
    *,
    binary: bool = False,
) -> SurfaceWriteResult:
    """Surface mesh → PLY (ASCII default, binary 옵션)."""
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_v = int(V.shape[0])
    n_f = int(F.shape[0])

    if n_v == 0 or n_f == 0:
        return SurfaceWriteResult(
            success=False, output_path=str(out),
            message="empty mesh",
            elapsed=time.perf_counter() - t0,
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    fmt = "binary_little_endian 1.0" if binary else "ascii 1.0"

    if binary:
        # binary path: header text, body binary.
        with out.open("wb") as f:
            header = (
                "ply\n"
                f"format {fmt}\n"
                f"element vertex {n_v}\n"
                "property float x\n"
                "property float y\n"
                "property float z\n"
                f"element face {n_f}\n"
                "property list uchar int vertex_index\n"
                "end_header\n"
            )
            f.write(header.encode("ascii"))
            f.write(V.astype("<f4").tobytes(order="C"))
            # face: uchar(n_v_per_face) + int32 indices.
            for face in F:
                f.write(bytes([len(face)]))
                f.write(face.astype("<i4").tobytes(order="C"))
    else:
        with out.open("w", encoding="ascii") as f:
            f.write(
                "ply\n"
                f"format {fmt}\n"
                f"comment AutoTessell PLY (O2/beta2661)\n"
                f"element vertex {n_v}\n"
                "property float x\n"
                "property float y\n"
                "property float z\n"
                f"element face {n_f}\n"
                "property list uchar int vertex_index\n"
                "end_header\n"
            )
            for v in V:
                f.write(f"{v[0]:.6e} {v[1]:.6e} {v[2]:.6e}\n")
            for face in F:
                idx = " ".join(str(int(i)) for i in face)
                f.write(f"{len(face)} {idx}\n")

    return SurfaceWriteResult(
        success=True, output_path=str(out),
        n_vertices=n_v, n_faces=n_f,
        elapsed=time.perf_counter() - t0,
        message=f"PLY written ({'binary' if binary else 'ASCII'}, {n_v} v, {n_f} f).",
    )
