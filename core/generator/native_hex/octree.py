"""native_hex 2-level octree adaptive refinement (beta91).

알고리즘:
    1. Fine grid (2× resolution) 생성.
    2. 각 fine cell 의 inside 여부 계산.
    3. Fine cell 을 2×2×2 coarse block 으로 그룹화.
       - 블록 내 8개 sub-cell 이 모두 inside → 단일 coarse hex 로 병합.
       - 그 외 → 8개 fine hex 개별 유지 (경계 영역).
    4. Coarse ↔ Fine 경계 전환 face:
       - Coarse cell 의 경계 면을 4개의 sub-quad 로 분할.
       - Fine cells 와의 conformal 연결 보장 (hanging node 없음).
    5. write_generic_polymesh 로 출력.

결과: 표면 근방은 fine (h/2), 내부는 coarse (h). 균일 grid 대비 better surface fit.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from core.utils.geometry import inside_winding_number as _iwn
from core.utils.logging import get_logger

log = get_logger(__name__)


def _fid(i: int, j: int, k: int, ny1: int, nz1: int) -> int:
    """Fine grid 의 (i,j,k) vertex → linear index."""
    return i * ny1 * nz1 + j * nz1 + k


def _hex8(i: int, j: int, k: int, ny1: int, nz1: int) -> list[int]:
    """(i,j,k) fine cell 의 8 vertex id (OpenFOAM hex order)."""
    f = _fid
    return [
        f(i,   j,   k,   ny1, nz1),
        f(i+1, j,   k,   ny1, nz1),
        f(i+1, j+1, k,   ny1, nz1),
        f(i,   j+1, k,   ny1, nz1),
        f(i,   j,   k+1, ny1, nz1),
        f(i+1, j,   k+1, ny1, nz1),
        f(i+1, j+1, k+1, ny1, nz1),
        f(i,   j+1, k+1, ny1, nz1),
    ]


# OpenFOAM hex face definitions (각 면의 vertex local index, CCW from outside)
_HEX_FACES: tuple[tuple[int, ...], ...] = (
    (0, 3, 2, 1),   # bottom -z
    (4, 5, 6, 7),   # top    +z
    (0, 1, 5, 4),   # front  -y
    (3, 7, 6, 2),   # back   +y
    (0, 4, 7, 3),   # left   -x
    (1, 2, 6, 5),   # right  +x
)

# For each of the 6 faces of a coarse 2×2 block: which 4 sub-quads cover it.
# Sub-quad defined by (di0,dj0,dk0) origin fine vertex corner deltas.
# Face axis ∈ {0=x,1=y,2=z}, face_side ∈ {0=min,1=max}.
# Returns list of 4 sub-quads each as 4 global-fine-vertex (di,dj,dk) tuples.
def _coarse_face_sub_quads(
    ci: int, cj: int, ck: int,
    face_idx: int,
    ny1: int, nz1: int,
) -> list[list[int]]:
    """Coarse cell (ci,cj,ck) 의 face_idx 면을 4개 fine sub-quad 로 분할.

    face_idx: 0=bottom, 1=top, 2=front, 3=back, 4=left, 5=right
    반환: sub-quad 마다 4 개의 fine grid vertex id 리스트.
    """
    # Fine base: coarse (ci,cj,ck) → fine (2ci, 2cj, 2ck)
    fi_base, fj_base, fk_base = ci * 2, cj * 2, ck * 2

    def gid(di: int, dj: int, dk: int) -> int:
        return _fid(fi_base + di, fj_base + dj, fk_base + dk, ny1, nz1)

    # 각 face 에 해당하는 4 sub-quad 정의 (fine vertex delta들)
    if face_idx == 0:  # bottom z=0
        # 2×2 grid on (i,j) plane at k=0
        return [
            [gid(0,0,0), gid(1,0,0), gid(1,1,0), gid(0,1,0)],
            [gid(1,0,0), gid(2,0,0), gid(2,1,0), gid(1,1,0)],
            [gid(0,1,0), gid(1,1,0), gid(1,2,0), gid(0,2,0)],
            [gid(1,1,0), gid(2,1,0), gid(2,2,0), gid(1,2,0)],
        ]
    elif face_idx == 1:  # top z=2
        return [
            [gid(0,0,2), gid(0,1,2), gid(1,1,2), gid(1,0,2)],
            [gid(1,0,2), gid(1,1,2), gid(2,1,2), gid(2,0,2)],
            [gid(0,1,2), gid(0,2,2), gid(1,2,2), gid(1,1,2)],
            [gid(1,1,2), gid(1,2,2), gid(2,2,2), gid(2,1,2)],
        ]
    elif face_idx == 2:  # front y=0
        return [
            [gid(0,0,0), gid(0,0,1), gid(1,0,1), gid(1,0,0)],
            [gid(1,0,0), gid(1,0,1), gid(2,0,1), gid(2,0,0)],
            [gid(0,0,1), gid(0,0,2), gid(1,0,2), gid(1,0,1)],
            [gid(1,0,1), gid(1,0,2), gid(2,0,2), gid(2,0,1)],
        ]
    elif face_idx == 3:  # back y=2
        return [
            [gid(0,2,0), gid(1,2,0), gid(1,2,1), gid(0,2,1)],
            [gid(1,2,0), gid(2,2,0), gid(2,2,1), gid(1,2,1)],
            [gid(0,2,1), gid(1,2,1), gid(1,2,2), gid(0,2,2)],
            [gid(1,2,1), gid(2,2,1), gid(2,2,2), gid(1,2,2)],
        ]
    elif face_idx == 4:  # left x=0
        return [
            [gid(0,0,0), gid(0,1,0), gid(0,1,1), gid(0,0,1)],
            [gid(0,1,0), gid(0,2,0), gid(0,2,1), gid(0,1,1)],
            [gid(0,0,1), gid(0,1,1), gid(0,1,2), gid(0,0,2)],
            [gid(0,1,1), gid(0,2,1), gid(0,2,2), gid(0,1,2)],
        ]
    else:  # right x=2
        return [
            [gid(2,0,0), gid(2,0,1), gid(2,1,1), gid(2,1,0)],
            [gid(2,1,0), gid(2,1,1), gid(2,2,1), gid(2,2,0)],
            [gid(2,0,1), gid(2,0,2), gid(2,1,2), gid(2,1,1)],
            [gid(2,1,1), gid(2,1,2), gid(2,2,2), gid(2,2,1)],
        ]


def build_octree_hex_cells(
    surface_V: np.ndarray,
    surface_F: np.ndarray,
    bmin: np.ndarray,
    bmax: np.ndarray,
    target_edge: float,
    max_cells_per_axis: int = 50,
) -> tuple[np.ndarray, list[list[list[int]]], dict]:
    """2-level octree hex grid 생성.

    Returns:
        (fine_pts, cell_face_verts, stats)
        fine_pts: (P, 3) fine grid 모든 vertex.
        cell_face_verts: 각 cell 의 face vertex list (write_generic_polymesh 입력 형식).
        stats: n_coarse, n_fine, n_total, grid_shape.
    """
    t0 = time.perf_counter()
    h = float(target_edge)
    h2 = h / 2.0

    # Fine grid dimensions (2× coarse)
    cap_fine = max_cells_per_axis * 2
    nfxyz = np.maximum(
        np.ceil((bmax - bmin) / h2).astype(int), 2,
    )
    nfxyz = np.minimum(nfxyz, cap_fine)
    nfx, nfy, nfz = int(nfxyz[0]), int(nfxyz[1]), int(nfxyz[2])
    nfx1, nfy1, nfz1 = nfx + 1, nfy + 1, nfz + 1

    log.info(
        "native_hex_octree_build",
        fine_grid=(nfx, nfy, nfz), h=h, h_fine=h2,
    )

    # Fine grid vertex coordinates
    xs = np.linspace(bmin[0], bmax[0], nfx1)
    ys = np.linspace(bmin[1], bmax[1], nfy1)
    zs = np.linspace(bmin[2], bmax[2], nfz1)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    fine_pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)

    # Inside test for fine cell centroids
    fine_cells_idx = np.array([
        _hex8(i, j, k, nfy1, nfz1)
        for i in range(nfx) for j in range(nfy) for k in range(nfz)
    ], dtype=np.int64)  # (N_fine, 8)

    centroids = fine_pts[fine_cells_idx].mean(axis=1)
    fine_inside = _iwn(centroids, surface_V, surface_F)  # (N_fine,)

    # Map (i,j,k) fine cell → linear index in fine_cells_idx
    def fine_cell_linear(i: int, j: int, k: int) -> int:
        return i * nfy * nfz + j * nfz + k

    fine_inside_3d = fine_inside.reshape(nfx, nfy, nfz)

    # Determine coarse blocks: 2×2×2 fine cells each
    # Coarse grid: ncx × ncy × ncz
    ncx, ncy, ncz = nfx // 2, nfy // 2, nfz // 2

    # coarse_ok[ci,cj,ck] = True iff all 8 sub-cells are inside
    coarse_ok = np.zeros((ncx, ncy, ncz), dtype=bool)
    for ci in range(ncx):
        for cj in range(ncy):
            for ck in range(ncz):
                fi2, fj2, fk2 = ci * 2, cj * 2, ck * 2
                block = fine_inside_3d[
                    fi2:fi2+2, fj2:fj2+2, fk2:fk2+2,
                ]
                coarse_ok[ci, cj, ck] = bool(block.all())

    # covered_by_coarse[fi,fj,fk] = True if this fine cell is part of an accepted coarse block
    covered = np.zeros((nfx, nfy, nfz), dtype=bool)
    for ci in range(ncx):
        for cj in range(ncy):
            for ck in range(ncz):
                if coarse_ok[ci, cj, ck]:
                    fi2, fj2, fk2 = ci * 2, cj * 2, ck * 2
                    covered[fi2:fi2+2, fj2:fj2+2, fk2:fk2+2] = True

    # Build cell face lists
    cell_face_verts: list[list[list[int]]] = []
    n_coarse = 0
    n_fine_cells = 0

    def coarse_hex_faces(ci: int, cj: int, ck: int) -> list[list[int]]:
        """Coarse hex 의 face list. 인접 fine cell 이 있으면 sub-quad 4개로 분할."""
        fi2, fj2, fk2 = ci * 2, cj * 2, ck * 2
        # 8 corner vertices (coarse = fine at even positions)
        c8 = _hex8(fi2, fj2, fk2, nfy1, nfz1)
        # 이 face 를 step=2 로 구성하면 됨
        # c8[0]=fi2,fj2,fk2  c8[1]=fi2+2,fj2,fk2 ...
        # Recompute using 2× offset
        def gid2(di: int, dj: int, dk: int) -> int:
            return _fid(fi2+di*2, fj2+dj*2, fk2+dk*2, nfy1, nfz1)
        coarse_v8 = [
            gid2(0,0,0), gid2(1,0,0), gid2(1,1,0), gid2(0,1,0),
            gid2(0,0,1), gid2(1,0,1), gid2(1,1,1), gid2(0,1,1),
        ]

        # Neighbour directions: check if adjacent coarse block exists
        # For each of 6 faces: is there a fine cell on the other side?
        faces_out: list[list[int]] = []

        # Face 0: bottom z=0 (fk2 side)
        need_split_0 = (ck > 0) and not coarse_ok[ci, cj, ck-1]
        # Face 1: top z=2 (fk2+2 side)
        need_split_1 = (ck < ncz-1) and not coarse_ok[ci, cj, ck+1]
        # Face 2: front y=0
        need_split_2 = (cj > 0) and not coarse_ok[ci, cj-1, ck]
        # Face 3: back y=2
        need_split_3 = (cj < ncy-1) and not coarse_ok[ci, cj+1, ck]
        # Face 4: left x=0
        need_split_4 = (ci > 0) and not coarse_ok[ci-1, cj, ck]
        # Face 5: right x=2
        need_split_5 = (ci < ncx-1) and not coarse_ok[ci+1, cj, ck]

        splits = [need_split_0, need_split_1, need_split_2,
                  need_split_3, need_split_4, need_split_5]

        for fid_local, (local_verts, split) in enumerate(
            zip(_HEX_FACES, splits)
        ):
            if split:
                # Split this face into 4 sub-quads
                sub_quads = _coarse_face_sub_quads(ci, cj, ck, fid_local, nfy1, nfz1)
                faces_out.extend(sub_quads)
            else:
                # Standard coarse quad face
                faces_out.append([coarse_v8[v] for v in local_verts])
        return faces_out

    # Coarse cells first
    for ci in range(ncx):
        for cj in range(ncy):
            for ck in range(ncz):
                if coarse_ok[ci, cj, ck]:
                    cell_face_verts.append(coarse_hex_faces(ci, cj, ck))
                    n_coarse += 1

    # Fine cells (not covered by coarse)
    for fi in range(nfx):
        for fj in range(nfy):
            for fk in range(nfz):
                if fine_inside_3d[fi, fj, fk] and not covered[fi, fj, fk]:
                    hex8 = _hex8(fi, fj, fk, nfy1, nfz1)
                    faces_of_cell = [[hex8[v] for v in lf] for lf in _HEX_FACES]
                    cell_face_verts.append(faces_of_cell)
                    n_fine_cells += 1

    n_total = n_coarse + n_fine_cells
    stats = {
        "n_coarse": n_coarse,
        "n_fine": n_fine_cells,
        "n_total": n_total,
        "grid_shape": (ncx, ncy, ncz),
        "fine_grid": (nfx, nfy, nfz),
        "elapsed": time.perf_counter() - t0,
    }
    log.info("native_hex_octree_done", **stats)
    return fine_pts, cell_face_verts, stats
