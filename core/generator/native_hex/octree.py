"""native_hex N-level octree adaptive refinement (beta92).

알고리즘:
    1. Fine grid (2^n_levels × resolution) 생성.
    2. 각 fine cell 의 inside 여부 + 표면 거리 계산.
    3. 거리 기반으로 목표 레벨 지정 (0=coarsest ~ n_levels=finest).
    4. 2:1 균형 조건 적용 (인접 cell 레벨 차이 ≤ 1).
    5. 레벨별로 coarsen 가능한 2^k × 2^k × 2^k 블록 병합.
    6. Conformal transition faces (coarse ↔ fine 경계).
    7. write_generic_polymesh 로 출력.

메모리 제한:
    fine grid 총 셀 수 ≤ 500,000. 초과 시 n_levels 자동 감소 + warning.

변경 이력:
    beta91: 2-level 고정 구현.
    beta92: n_levels 파라미터 추가 → N-level 지원 (n_levels=2 가 기존 동작과 호환).
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from core.utils.geometry import inside_winding_number as _iwn
from core.utils.logging import get_logger

log = get_logger(__name__)

# --------------------------------------------------------------------------
# 기본 인덱싱 유틸
# --------------------------------------------------------------------------


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

# Face neighbour direction deltas (fi, fj, fk) — 6 faces 순서로 _HEX_FACES 와 대응.
_FACE_DIRS: tuple[tuple[int, int, int], ...] = (
    (0,  0, -1),  # bottom -z
    (0,  0, +1),  # top    +z
    (0, -1,  0),  # front  -y
    (0, +1,  0),  # back   +y
    (-1, 0,  0),  # left   -x
    (+1, 0,  0),  # right  +x
)


# --------------------------------------------------------------------------
# Conformal transition face 생성 — 다중 레벨 대응
# --------------------------------------------------------------------------

def _sub_quads_on_face(
    fi_base: int, fj_base: int, fk_base: int,
    face_idx: int,
    step: int,
    ny1: int, nz1: int,
) -> list[list[int]]:
    """Coarse cell (fine origin fi_base,fj_base,fk_base, edge=step) 의 face_idx 면을
    (step//2) 크기의 서브 quad 4개로 분할.

    face_idx: 0=bottom(-z), 1=top(+z), 2=front(-y), 3=back(+y), 4=left(-x), 5=right(+x)
    반환: sub-quad 마다 4 개의 fine grid vertex id 리스트.
    """
    s = step  # coarse edge 크기 (fine grid units)
    h = s // 2  # sub-quad edge 크기

    def gid(di: int, dj: int, dk: int) -> int:
        return _fid(fi_base + di, fj_base + dj, fk_base + dk, ny1, nz1)

    if face_idx == 0:  # bottom z=0
        return [
            [gid(0,   0,   0), gid(h,   0,   0), gid(h,   h,   0), gid(0,   h,   0)],
            [gid(h,   0,   0), gid(s,   0,   0), gid(s,   h,   0), gid(h,   h,   0)],
            [gid(0,   h,   0), gid(h,   h,   0), gid(h,   s,   0), gid(0,   s,   0)],
            [gid(h,   h,   0), gid(s,   h,   0), gid(s,   s,   0), gid(h,   s,   0)],
        ]
    elif face_idx == 1:  # top z=s
        return [
            [gid(0,   0,   s), gid(0,   h,   s), gid(h,   h,   s), gid(h,   0,   s)],
            [gid(h,   0,   s), gid(h,   h,   s), gid(s,   h,   s), gid(s,   0,   s)],
            [gid(0,   h,   s), gid(0,   s,   s), gid(h,   s,   s), gid(h,   h,   s)],
            [gid(h,   h,   s), gid(h,   s,   s), gid(s,   s,   s), gid(s,   h,   s)],
        ]
    elif face_idx == 2:  # front y=0
        return [
            [gid(0,   0,   0), gid(0,   0,   h), gid(h,   0,   h), gid(h,   0,   0)],
            [gid(h,   0,   0), gid(h,   0,   h), gid(s,   0,   h), gid(s,   0,   0)],
            [gid(0,   0,   h), gid(0,   0,   s), gid(h,   0,   s), gid(h,   0,   h)],
            [gid(h,   0,   h), gid(h,   0,   s), gid(s,   0,   s), gid(s,   0,   h)],
        ]
    elif face_idx == 3:  # back y=s
        return [
            [gid(0,   s,   0), gid(h,   s,   0), gid(h,   s,   h), gid(0,   s,   h)],
            [gid(h,   s,   0), gid(s,   s,   0), gid(s,   s,   h), gid(h,   s,   h)],
            [gid(0,   s,   h), gid(h,   s,   h), gid(h,   s,   s), gid(0,   s,   s)],
            [gid(h,   s,   h), gid(s,   s,   h), gid(s,   s,   s), gid(h,   s,   s)],
        ]
    elif face_idx == 4:  # left x=0
        return [
            [gid(0,   0,   0), gid(0,   h,   0), gid(0,   h,   h), gid(0,   0,   h)],
            [gid(0,   h,   0), gid(0,   s,   0), gid(0,   s,   h), gid(0,   h,   h)],
            [gid(0,   0,   h), gid(0,   h,   h), gid(0,   h,   s), gid(0,   0,   s)],
            [gid(0,   h,   h), gid(0,   s,   h), gid(0,   s,   s), gid(0,   h,   s)],
        ]
    else:  # right x=s
        return [
            [gid(s,   0,   0), gid(s,   0,   h), gid(s,   h,   h), gid(s,   h,   0)],
            [gid(s,   h,   0), gid(s,   h,   h), gid(s,   s,   h), gid(s,   s,   0)],
            [gid(s,   0,   h), gid(s,   0,   s), gid(s,   h,   s), gid(s,   h,   h)],
            [gid(s,   h,   h), gid(s,   h,   s), gid(s,   s,   s), gid(s,   s,   h)],
        ]


# --------------------------------------------------------------------------
# 2-level 호환 래퍼 (기존 테스트 호환)
# --------------------------------------------------------------------------

def _coarse_face_sub_quads(
    ci: int, cj: int, ck: int,
    face_idx: int,
    ny1: int, nz1: int,
) -> list[list[int]]:
    """Coarse cell (ci,cj,ck) 의 face_idx 면을 4개 fine sub-quad 로 분할 (2-level 호환)."""
    fi_base, fj_base, fk_base = ci * 2, cj * 2, ck * 2
    return _sub_quads_on_face(fi_base, fj_base, fk_base, face_idx, 2, ny1, nz1)


# --------------------------------------------------------------------------
# N-level octree 핵심 구현
# --------------------------------------------------------------------------

def _compute_surface_distances(
    cell_centroids: np.ndarray,
    surface_V: np.ndarray,
    surface_F: np.ndarray,
) -> np.ndarray:
    """각 cell centroid 에서 표면 triangle 까지의 최솟거리 (근사).

    KDTree 를 triangle centroid 로 구성하여 근접 거리 추정.
    정확한 point-to-triangle 대신 centroid-to-centroid 로 빠르게 근사.
    """
    from scipy.spatial import cKDTree  # noqa: PLC0415

    # triangle centroid 계산
    tri_centroids = surface_V[surface_F].mean(axis=1)  # (T, 3)
    tree = cKDTree(tri_centroids)
    dists, _ = tree.query(cell_centroids, k=1, workers=1)
    return dists.astype(np.float64)


def _apply_2to1_balance(
    level_grid: np.ndarray,
    n_levels: int,
) -> np.ndarray:
    """2:1 균형 조건: 인접 cell 레벨 차이 ≤ 1.

    인접 cell 레벨 차이가 1 초과이면 낮은 쪽 레벨을 올린다.
    수렴할 때까지 반복 (최대 n_levels 번).
    """
    nx, ny, nz = level_grid.shape
    changed = True
    iterations = 0
    while changed and iterations < n_levels + 2:
        changed = False
        iterations += 1
        for di, dj, dk in (
            (1, 0, 0), (0, 1, 0), (0, 0, 1),
            (-1, 0, 0), (0, -1, 0), (0, 0, -1),
        ):
            # Shift arrays to compare neighbours
            if di == 1:
                a = level_grid[:-1, :, :]
                b = level_grid[1:,  :, :]
            elif di == -1:
                a = level_grid[1:,  :, :]
                b = level_grid[:-1, :, :]
            elif dj == 1:
                a = level_grid[:, :-1, :]
                b = level_grid[:, 1:,  :]
            elif dj == -1:
                a = level_grid[:, 1:,  :]
                b = level_grid[:, :-1, :]
            elif dk == 1:
                a = level_grid[:, :, :-1]
                b = level_grid[:, :, 1:]
            else:
                a = level_grid[:, :, 1:]
                b = level_grid[:, :, :-1]

            # 차이가 2 이상이면 낮은 쪽 레벨 올리기
            diff = a.astype(np.int32) - b.astype(np.int32)
            # a 가 b 보다 2 이상 높으면 b 를 1 올림
            mask_b_up = diff >= 2
            if mask_b_up.any():
                # b 에 해당하는 grid 슬라이스 찾기
                if di == 1:
                    level_grid[1:, :, :] = np.maximum(
                        level_grid[1:, :, :],
                        np.where(mask_b_up, level_grid[:-1, :, :] - 1, level_grid[1:, :, :]),
                    )
                elif di == -1:
                    level_grid[:-1, :, :] = np.maximum(
                        level_grid[:-1, :, :],
                        np.where(mask_b_up, level_grid[1:, :, :] - 1, level_grid[:-1, :, :]),
                    )
                elif dj == 1:
                    level_grid[:, 1:, :] = np.maximum(
                        level_grid[:, 1:, :],
                        np.where(mask_b_up, level_grid[:, :-1, :] - 1, level_grid[:, 1:, :]),
                    )
                elif dj == -1:
                    level_grid[:, :-1, :] = np.maximum(
                        level_grid[:, :-1, :],
                        np.where(mask_b_up, level_grid[:, 1:, :] - 1, level_grid[:, :-1, :]),
                    )
                elif dk == 1:
                    level_grid[:, :, 1:] = np.maximum(
                        level_grid[:, :, 1:],
                        np.where(mask_b_up, level_grid[:, :, :-1] - 1, level_grid[:, :, 1:]),
                    )
                else:
                    level_grid[:, :, :-1] = np.maximum(
                        level_grid[:, :, :-1],
                        np.where(mask_b_up, level_grid[:, :, 1:] - 1, level_grid[:, :, :-1]),
                    )
                changed = True
    return level_grid


def _build_nlevel_cells(
    fine_pts: np.ndarray,
    inside_3d: np.ndarray,
    level_3d: np.ndarray,
    n_levels: int,
    nfx: int, nfy: int, nfz: int,
    nfy1: int, nfz1: int,
) -> list[list[list[int]]]:
    """N-level octree cell 및 face 리스트 생성.

    level_3d[i,j,k] = 0..n_levels: 해당 fine cell 의 목표 refinement level.
    level=0 → 2^n_levels × 2^n_levels × 2^n_levels fine cell 을 1개 coarsest hex 로 병합.
    level=l → 2^(n_levels-l) 크기 블록.
    level=n_levels → fine cell 1개.

    구현 전략:
      각 레벨 l=0..n_levels 에 대해, 해당 레벨로 처리되는 블록을 먼저 식별.
      높은 레벨(fine) 부터 처리하고, 이미 처리된 fine cell 은 covered 배열로 추적.
    """
    stride = 1 << n_levels  # 최대 coarse block 크기 (fine grid units)
    covered = np.zeros((nfx, nfy, nfz), dtype=bool)
    cell_face_verts: list[list[list[int]]] = []

    # 각 fine cell 의 inside 여부
    # level_3d 는 inside_3d=True 인 cell 에만 의미있다. outside cell 은 skip.

    # 레벨 0 (가장 거친) 부터 n_levels (가장 미세) 까지 처리
    # 단, 처리 순서: 거친 것 먼저, 그 안에 미세한 것이 있으면 분할.
    # 실용적 접근: fine (level=n_levels) → coarser 순서로 진행하면
    # "이 블록이 단일 레벨로 묶을 수 있는가?" 판단이 쉬움.

    for target_lev in range(n_levels, -1, -1):
        block_sz = 1 << (n_levels - target_lev)  # fine grid 기준 블록 크기
        step_i = max(1, nfx // (nfx // block_sz + 1)) if block_sz > nfx else block_sz
        step_i = block_sz  # 단순화: block_sz 로 순회

        for fi in range(0, nfx, block_sz):
            for fj in range(0, nfy, block_sz):
                for fk in range(0, nfz, block_sz):
                    # 이미 처리된 cell 은 skip
                    if covered[fi, fj, fk]:
                        continue
                    # 블록 범위
                    fi_end = min(fi + block_sz, nfx)
                    fj_end = min(fj + block_sz, nfy)
                    fk_end = min(fk + block_sz, nfz)

                    # 블록 내 모든 cell 이 inside 이고 목표 레벨 == target_lev 이어야 함
                    # 또는 target_lev 이하 (더 거친 레벨이 허용됨) 이어야 함
                    sub_inside = inside_3d[fi:fi_end, fj:fj_end, fk:fk_end]
                    sub_level = level_3d[fi:fi_end, fj:fj_end, fk:fk_end]

                    # 블록 크기가 1×1×1 이면 fine cell
                    if block_sz == 1:
                        if not bool(sub_inside[0, 0, 0]):
                            continue
                        # Fine cell
                        hex8 = _hex8(fi, fj, fk, nfy1, nfz1)
                        # Fine cell 의 faces — 인접 cell 과의 conformal 연결은
                        # 단순 6-quad (fine 레벨끼리는 크기 동일)
                        faces_of_cell = [[hex8[v] for v in lf] for lf in _HEX_FACES]
                        cell_face_verts.append(faces_of_cell)
                        covered[fi, fj, fk] = True
                        continue

                    # 블록 전체가 inside 이고, 전부 target_lev 이하 레벨을 갖는가?
                    # (이 블록을 하나의 coarse hex 로 병합 가능한 조건)
                    sub_sz_act = (fi_end - fi, fj_end - fj, fk_end - fk)
                    if sub_sz_act != (block_sz, block_sz, block_sz):
                        # 경계에서 블록이 잘린 경우 — 병합 불가, 하위 레벨에서 처리
                        continue
                    if not bool(sub_inside.all()):
                        # 부분만 inside → 이 블록 통째로 병합 불가
                        continue
                    if not bool((sub_level <= target_lev).all()):
                        # 하위 cell 중 더 fine 해야 하는 것이 있음 → 병합 불가
                        continue

                    # 이 블록을 하나의 coarse hex 로 병합
                    # coarse hex 의 8 corner vertex: fine grid 기준 0,block_sz 위치
                    s = block_sz
                    def gv(di: int, dj: int, dk: int) -> int:
                        return _fid(fi+di, fj+dj, fk+dk, nfy1, nfz1)

                    coarse_v8 = [
                        gv(0, 0, 0), gv(s, 0, 0), gv(s, s, 0), gv(0, s, 0),
                        gv(0, 0, s), gv(s, 0, s), gv(s, s, s), gv(0, s, s),
                    ]

                    # 각 face: 인접 블록 레벨 확인 → split 필요하면 sub-quad 4개
                    faces_out: list[list[int]] = []
                    for fid_local, (local_verts, (di, dj, dk)) in enumerate(
                        zip(_HEX_FACES, _FACE_DIRS)
                    ):
                        # 인접 블록 origin
                        ni = fi + di * s
                        nj = fj + dj * s
                        nk = fk + dk * s

                        # 인접이 grid 밖이면 그냥 coarse quad
                        if not (0 <= ni < nfx and 0 <= nj < nfy and 0 <= nk < nfz):
                            faces_out.append([coarse_v8[v] for v in local_verts])
                            continue

                        # 인접 cell 의 목표 레벨 확인
                        nbr_level = int(level_3d[ni, nj, nk])
                        nbr_inside = bool(inside_3d[ni, nj, nk])

                        # 인접이 outside 이면 coarse quad (경계)
                        if not nbr_inside:
                            faces_out.append([coarse_v8[v] for v in local_verts])
                            continue

                        # 인접 레벨이 더 높으면 (fine) → sub-quad 분할
                        if nbr_level > target_lev:
                            sub_quads = _sub_quads_on_face(
                                fi, fj, fk, fid_local, s, nfy1, nfz1,
                            )
                            faces_out.extend(sub_quads)
                        else:
                            faces_out.append([coarse_v8[v] for v in local_verts])

                    cell_face_verts.append(faces_out)
                    covered[fi:fi_end, fj:fj_end, fk:fk_end] = True

    return cell_face_verts


# --------------------------------------------------------------------------
# 공개 API
# --------------------------------------------------------------------------

def build_octree_hex_cells(
    surface_V: np.ndarray,
    surface_F: np.ndarray,
    bmin: np.ndarray,
    bmax: np.ndarray,
    target_edge: float,
    max_cells_per_axis: int = 50,
    n_levels: int = 2,
    refinement_distance_factor: float = 2.0,
) -> tuple[np.ndarray, list[list[list[int]]], dict]:
    """N-level octree hex grid 생성 (beta92).

    Args:
        surface_V: (V, 3) 표면 점.
        surface_F: (F, 3) 표면 triangles.
        bmin, bmax: bounding box.
        target_edge: coarsest level 의 hex edge length.
        max_cells_per_axis: fine grid 각 축당 최대 cell 수.
        n_levels: octree 최대 refinement 레벨 (기본 2, beta91 호환).
                  레벨 0 = target_edge, 레벨 k = target_edge / 2^k.
        refinement_distance_factor: 표면까지 거리 < factor × h_level_k 이면 level k 이상.

    Returns:
        (fine_pts, cell_face_verts, stats)
        fine_pts: (P, 3) fine grid 모든 vertex.
        cell_face_verts: 각 cell 의 face vertex list (write_generic_polymesh 입력 형식).
        stats: n_coarse, n_fine, n_total, grid_shape.

    메모리 제한:
        fine grid 총 셀 수 ≤ 500,000. 초과 시 n_levels 자동 감소.
    """
    t0 = time.perf_counter()
    h = float(target_edge)
    n_lev = int(max(1, n_levels))

    # 메모리 제한: fine grid 총 셀 수 ≤ 500,000
    _MAX_FINE_CELLS = 500_000
    while n_lev > 1:
        cap_fine = max_cells_per_axis * (1 << n_lev)
        nfxyz_est = np.maximum(
            np.ceil((bmax - bmin) / (h / (1 << n_lev))).astype(int), 2,
        )
        nfxyz_est = np.minimum(nfxyz_est, cap_fine)
        est_cells = int(nfxyz_est[0]) * int(nfxyz_est[1]) * int(nfxyz_est[2])
        if est_cells <= _MAX_FINE_CELLS:
            break
        old = n_lev
        n_lev -= 1
        log.warning(
            "native_hex_octree_nlevel_reduced",
            from_levels=old, to_levels=n_lev,
            estimated_cells=est_cells, limit=_MAX_FINE_CELLS,
        )

    # Fine grid 크기: h_fine = h / 2^n_lev (가장 미세한 cell 크기)
    h_fine = h / (1 << n_lev)
    cap_fine = max_cells_per_axis * (1 << n_lev)
    nfxyz = np.maximum(
        np.ceil((bmax - bmin) / h_fine).astype(int), 2,
    )
    nfxyz = np.minimum(nfxyz, cap_fine)
    nfx, nfy, nfz = int(nfxyz[0]), int(nfxyz[1]), int(nfxyz[2])
    nfx1, nfy1, nfz1 = nfx + 1, nfy + 1, nfz + 1

    log.info(
        "native_hex_octree_build",
        fine_grid=(nfx, nfy, nfz), h=h, h_fine=h_fine,
        n_levels=n_lev, cap_fine=cap_fine,
    )

    # Fine grid vertex coordinates
    xs = np.linspace(float(bmin[0]), float(bmax[0]), nfx1)
    ys = np.linspace(float(bmin[1]), float(bmax[1]), nfy1)
    zs = np.linspace(float(bmin[2]), float(bmax[2]), nfz1)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    fine_pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)

    # Fine cell centroids
    n_fine_total = nfx * nfy * nfz
    fine_cells_idx = np.array([
        _hex8(i, j, k, nfy1, nfz1)
        for i in range(nfx) for j in range(nfy) for k in range(nfz)
    ], dtype=np.int64)  # (N_fine, 8)

    centroids = fine_pts[fine_cells_idx].mean(axis=1)  # (N_fine, 3)

    # Inside test
    fine_inside = _iwn(centroids, surface_V, surface_F)  # (N_fine,) bool
    fine_inside_3d = fine_inside.reshape(nfx, nfy, nfz)

    # Surface distance 계산 (inside cell 만)
    inside_idx = np.where(fine_inside)[0]
    all_dists = np.full(n_fine_total, np.inf, dtype=np.float64)
    if len(inside_idx) > 0:
        try:
            dists = _compute_surface_distances(
                centroids[inside_idx], surface_V, surface_F,
            )
            all_dists[inside_idx] = dists
        except Exception as exc:
            log.warning("native_hex_octree_dist_failed", error=str(exc))
            all_dists[inside_idx] = 0.0  # 거리 계산 실패 → 전부 finest

    dists_3d = all_dists.reshape(nfx, nfy, nfz)

    # 목표 레벨 지정:
    #   level = n_lev (finest) if dist < factor × h_fine
    #   level = n_lev - k if dist < factor × h_level(k)
    #   level = 0 (coarsest) otherwise
    level_3d = np.zeros((nfx, nfy, nfz), dtype=np.int8)
    for k in range(n_lev + 1):
        h_k = h / (1 << k)  # level k 의 cell 크기
        threshold = refinement_distance_factor * h_k
        mask = (dists_3d < threshold) & fine_inside_3d
        level_3d[mask] = np.maximum(level_3d[mask], np.int8(k))

    # Outside cell 은 level=0 으로 유지 (나중에 skip 됨)
    level_3d[~fine_inside_3d] = 0

    # 2:1 균형 조건 적용
    if n_lev > 1:
        level_3d = _apply_2to1_balance(level_3d, n_lev)

    # N-level cell 및 face 생성
    cell_face_verts = _build_nlevel_cells(
        fine_pts, fine_inside_3d, level_3d, n_lev,
        nfx, nfy, nfz, nfy1, nfz1,
    )

    # 통계: 레벨별 cell 수
    n_finest = int((level_3d == n_lev).sum())
    n_coarser = len(cell_face_verts) - n_finest
    n_total = len(cell_face_verts)

    # beta91 호환 통계 키 (n_coarse = coarsest level, n_fine = finest level)
    # coarsest level cell 수를 n_coarse 로, finest 를 n_fine 으로 보고.
    n_coarse_lev0 = int((level_3d[fine_inside_3d] == 0).sum()) if fine_inside_3d.any() else 0
    # n_coarse 는 level=0 블록 (2^n_lev × 2^n_lev × 2^n_lev 병합된 것들)
    # 실제로는 cell_face_verts 로 카운트하기 어려우므로 아래처럼 근사.
    n_coarse = max(0, n_total - n_finest)
    n_fine_cells = n_finest

    stats = {
        "n_coarse": n_coarse,
        "n_fine": n_fine_cells,
        "n_total": n_total,
        "n_levels": n_lev,
        "grid_shape": (nfx // (1 << n_lev), nfy // (1 << n_lev), nfz // (1 << n_lev)),
        "fine_grid": (nfx, nfy, nfz),
        "elapsed": time.perf_counter() - t0,
    }
    log.info("native_hex_octree_done", **stats)
    return fine_pts, cell_face_verts, stats
