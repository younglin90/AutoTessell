"""I2 / beta2620 — NASA Plot3D .x (grid) + .q (solution) writer.

Plot3D 포맷 (NASA Ames Research Center, 1980s):
    Multi-block structured grid format. unstructured 메쉬는 직접 지원 안 됨 —
    1-block per "patch" 로 splitting 하거나 cells 를 rectangular block 으로 변환.

본 구현: 각 cell 을 단일 block 1×1×N 으로 (degenerate) 출력.
실 사용에서는 structured grid 입력만 권장. 우리 unstructured polyMesh 는
"point cloud + connectivity" 형태라 진짜 Plot3D 호환은 grid_x/grid_y/grid_z
재구조화 필요.

여기서는 "MULTI" 형태로 boundary point를 export — NASA FUN3D 가 unstructured 를
지원하므로 .x 와 함께 .ugrid 추천 (별도).

Format spec:
    .x (grid):
        nblocks  (int32)
        ni nj nk × nblocks (int32)
        x y z × ni*nj*nk × nblocks (float64)
    .q (solution): ni nj nk + 4 reference vars + density/momentum/energy.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Plot3DWriteResult:
    success: bool
    output_path: str = ""
    n_blocks: int = 0
    n_total_points: int = 0
    elapsed: float = 0.0
    message: str = ""


def write_plot3d_grid(
    polymesh_dir: str | Path,
    output_path: str | Path,
    *,
    binary: bool = True,
) -> Plot3DWriteResult:
    """OpenFOAM polyMesh → Plot3D .x grid file.

    Strategy: unstructured polyMesh → 1-block "1×1×N" pseudo-grid (모든 점 N).
    실 NASA tools 는 이 포맷을 reject 가능 — formal spec 대로 기록.
    """
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    pm_path = Path(polymesh_dir)

    try:
        from core.utils.poly_mesh_reader import read_poly_mesh
        pm = read_poly_mesh(pm_path)
    except Exception as exc:
        return Plot3DWriteResult(
            success=False, output_path=str(out),
            message=f"poly_mesh_reader unavailable: {exc!s:.60}",
            elapsed=time.perf_counter() - t0,
        )

    points = np.asarray(pm.get("points", []), dtype=np.float64)
    n_pts = int(points.shape[0])

    if n_pts == 0:
        return Plot3DWriteResult(
            success=False, output_path=str(out),
            message="empty mesh",
            elapsed=time.perf_counter() - t0,
        )

    out.parent.mkdir(parents=True, exist_ok=True)

    # Single block 1 × 1 × N_pts (pseudo-structured).
    nblocks = 1
    ni, nj, nk = 1, 1, n_pts
    n_block_pts = ni * nj * nk

    if binary:
        # Fortran unformatted — record markers (4-byte length).
        with out.open("wb") as f:
            # nblocks.
            f.write(struct.pack("<i", 4))         # record length.
            f.write(struct.pack("<i", nblocks))
            f.write(struct.pack("<i", 4))         # record length.
            # ni nj nk per block.
            f.write(struct.pack("<i", 12 * nblocks))
            f.write(struct.pack("<iii", ni, nj, nk))
            f.write(struct.pack("<i", 12 * nblocks))
            # coords block: ni*nj*nk × 3 × 8 bytes.
            block_bytes = n_block_pts * 3 * 8
            f.write(struct.pack("<i", block_bytes))
            # X block, Y block, Z block (axis-major).
            for axis in range(3):
                f.write(points[:, axis].astype("<f8").tobytes())
            f.write(struct.pack("<i", block_bytes))
    else:
        # ASCII format.
        with out.open("w", encoding="ascii") as f:
            f.write(f"{nblocks}\n")
            f.write(f"{ni} {nj} {nk}\n")
            for axis in range(3):
                for v in points[:, axis]:
                    f.write(f"{v:.10e}\n")

    return Plot3DWriteResult(
        success=True, output_path=str(out),
        n_blocks=nblocks, n_total_points=n_pts,
        elapsed=time.perf_counter() - t0,
        message=(
            f"Plot3D .x grid written ({nblocks} block, {n_pts} pts, "
            f"{'binary' if binary else 'ASCII'}). "
            f"NOTE: pseudo-structured (1×1×N) — NASA FUN3D 는 .ugrid 권장."
        ),
    )
