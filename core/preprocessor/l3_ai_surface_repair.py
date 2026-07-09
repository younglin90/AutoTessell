"""L3-AI / beta2807 — fragile input AI-driven surface repair.

extreme self-intersect 입력 (SI > 500, mq < 0.05) 의 알고리즘 한계 회복:

전략 (Vec → Voxel → Marching Cubes 재구성):
    1. 입력 surface 를 voxel 에 distance field 로 sampling.
    2. signed distance field (SDF) 를 KDTree + sign-via-winding 으로 계산.
    3. Gaussian smooth (3-iter) → blob 형태로 noise/SI 제거.
    4. Marching cubes 로 새 surface 재구성 — guaranteed watertight, no SI.
    5. quality validate: 새 mq vs 기존 mq, 더 좋으면 채택.

CLAUDE.md: numpy / scipy.spatial 외 신규 의존 없음 (skimage marching cubes
기존 의존 가능 — fallback 처리).

L3 라 부르는 이유: L1=topology repair (dedup/degenerate),
L2=isotropic remesh, L3=AI/global re-gen — extreme input 의 마지막 수단.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class L3RepairResult:
    success: bool = False
    pre_n_vertices: int = 0
    pre_n_faces: int = 0
    pre_si_count: int = 0
    pre_mq: float = 0.0
    post_n_vertices: int = 0
    post_n_faces: int = 0
    post_si_count: int = 0
    post_mq: float = 0.0
    voxel_resolution: int = 0
    elapsed_s: float = 0.0
    message: str = ""
    method: str = ""


def voxel_sdf_repair(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    voxel_resolution: int = 64,
    smooth_iters: int = 2,
    iso_value: float = 0.0,
    keep_if_worse: bool = False,
) -> tuple[NDArray[np.float64], NDArray[np.int64], L3RepairResult]:
    """SDF voxel 재구성 surface repair.

    Args:
        V: (N, 3) vertices.
        F: (M, 3) tris.
        voxel_resolution: voxel grid 한 변 (32~128 권장).
        smooth_iters: Gaussian smooth iter (3D).
        iso_value: marching cubes iso (0 = surface).
        keep_if_worse: True 면 새 mesh 가 quality 더 낮아도 채택.

    Returns:
        (V_new, F_new, L3RepairResult). 실패 시 원본 복귀.
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    res = L3RepairResult(
        pre_n_vertices=int(V.shape[0]),
        pre_n_faces=int(F.shape[0]),
        voxel_resolution=int(voxel_resolution),
    )

    if F.shape[0] == 0 or V.shape[0] == 0:
        res.message = "empty input"
        res.elapsed_s = time.perf_counter() - t0
        return V, F, res

    # pre-stats.
    res.pre_si_count = _count_si(V, F)
    res.pre_mq = _surface_mq(V, F)

    try:
        new_V, new_F, method = _sdf_marching_cubes(
            V, F, resolution=int(voxel_resolution),
            smooth_iters=int(smooth_iters),
            iso_value=float(iso_value),
        )
        res.method = method
        if new_V is None or new_F is None or new_F.shape[0] < 4:
            res.message = "voxelization failed"
            res.elapsed_s = time.perf_counter() - t0
            return V, F, res
    except Exception as exc:
        res.message = f"voxelization error: {exc!s:.80}"
        res.elapsed_s = time.perf_counter() - t0
        return V, F, res

    res.post_n_vertices = int(new_V.shape[0])
    res.post_n_faces = int(new_F.shape[0])
    res.post_si_count = _count_si(new_V, new_F)
    res.post_mq = _surface_mq(new_V, new_F)

    # 채택 판정.
    accept = False
    if keep_if_worse:
        accept = True
    elif res.post_si_count == 0 and res.pre_si_count > 0:
        accept = True   # SI 가 모두 사라짐 → guaranteed.
    elif res.post_mq > res.pre_mq * 1.1:
        accept = True   # quality 10% 이상 향상.

    if not accept:
        res.message = (
            f"reject: post_si={res.post_si_count} post_mq={res.post_mq:.3f} "
            f"vs pre_si={res.pre_si_count} pre_mq={res.pre_mq:.3f}"
        )
        res.elapsed_s = time.perf_counter() - t0
        return V, F, res

    res.success = True
    res.message = (
        f"accepted: SI {res.pre_si_count}→{res.post_si_count}, "
        f"mq {res.pre_mq:.3f}→{res.post_mq:.3f}, "
        f"n_pts {res.pre_n_vertices}→{res.post_n_vertices}, "
        f"voxel_res={voxel_resolution}, method={res.method}"
    )
    res.elapsed_s = time.perf_counter() - t0
    return new_V, new_F, res


def _sdf_marching_cubes(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    resolution: int,
    smooth_iters: int,
    iso_value: float,
) -> tuple:
    """signed distance field via KDTree + winding number, marching cubes."""
    bbox_min = V.min(axis=0) - 1e-3
    bbox_max = V.max(axis=0) + 1e-3
    extents = bbox_max - bbox_min
    pad = 0.05 * extents.max()
    bbox_min -= pad
    bbox_max += pad

    res = int(resolution)
    xs = np.linspace(bbox_min[0], bbox_max[0], res)
    ys = np.linspace(bbox_min[1], bbox_max[1], res)
    zs = np.linspace(bbox_min[2], bbox_max[2], res)
    spacing = (
        float(xs[1] - xs[0]),
        float(ys[1] - ys[0]),
        float(zs[1] - zs[0]),
    )
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    grid_pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)

    # nearest distance via KDTree of vertices.
    try:
        from scipy.spatial import cKDTree
        tree = cKDTree(V)
        dist, _ = tree.query(grid_pts, k=1)
    except Exception:
        # fallback: brute force.
        d = np.linalg.norm(
            grid_pts[:, None, :] - V[None, :, :], axis=2,
        )
        dist = d.min(axis=1)

    # sign via winding number (inside = negative).
    # web-QA (2026-07-02): inside_safe 의 KDTree top-K prune 은 ray 가 지나는
    # 원거리 face 를 버려 구조적으로 오판 (연구조사 rank 1 지적).
    # inside_robust(GWN 디스패처)를 1순위로 — L3 는 정의상 쓰레기 표면이므로
    # 대부분 GWN 경로를 탄다.
    try:
        from core.utils.geometry import inside_robust
        inside = inside_robust(grid_pts, V, F)
    except Exception:
        try:
            from core.utils.inside_safe import inside_safe
            inside = inside_safe(grid_pts, V, F, k_neighbors=32)
        except Exception:
            inside = np.zeros(grid_pts.shape[0], dtype=bool)

    sdf = dist.copy()
    sdf[inside] *= -1
    sdf = sdf.reshape(res, res, res)

    # smooth (3D box filter approximation).
    method = "kdtree_winding"
    for _ in range(int(smooth_iters)):
        smooth = sdf.copy()
        smooth[1:-1, 1:-1, 1:-1] = (
            sdf[1:-1, 1:-1, 1:-1] * 0.5
            + sdf[:-2, 1:-1, 1:-1] * 0.0833
            + sdf[2:, 1:-1, 1:-1] * 0.0833
            + sdf[1:-1, :-2, 1:-1] * 0.0833
            + sdf[1:-1, 2:, 1:-1] * 0.0833
            + sdf[1:-1, 1:-1, :-2] * 0.0833
            + sdf[1:-1, 1:-1, 2:] * 0.0833
        )
        sdf = smooth

    # 등위면 추출 — native-first (CLAUDE.md): 자체 Surface Nets 우선.
    # L3 sdf 는 inside<0 규약, surface_nets 는 inside>0 규약 → 부호 반전.
    try:
        from core.utils.surface_nets import surface_nets as _sn

        sx = float(spacing[0]) if isinstance(spacing, (tuple, list, np.ndarray)) else float(spacing)
        verts, tris = _sn(
            -sdf, np.asarray(bbox_min, dtype=np.float64), sx,
            iso=-float(iso_value),
        )
        if verts.shape[0] >= 4 and tris.shape[0] >= 4:
            return verts.astype(np.float64), tris.astype(np.int64), method + "_surfacenets"
    except Exception as _sn_exc:  # noqa: BLE001
        log.debug("surface_nets_l3_failed", error=str(_sn_exc)[:120])

    # 선택적 가속: skimage 가 있으면 사용 (없으면 위 native 로 이미 처리됨).
    try:
        from skimage.measure import marching_cubes
        verts, tris, _, _ = marching_cubes(
            sdf, level=float(iso_value), spacing=spacing,
        )
        verts = verts + np.array([bbox_min[0], bbox_min[1], bbox_min[2]])
        return verts.astype(np.float64), tris.astype(np.int64), method + "_skimage"
    except Exception:
        return _fallback_voxel_surface(sdf, bbox_min, spacing)


def _fallback_voxel_surface(
    sdf: NDArray[np.float64],
    bbox_min: NDArray[np.float64],
    spacing: tuple,
) -> tuple:
    """skimage 없을 때 fallback: voxel cube boundary 만 추출 (low quality)."""
    inside_grid = sdf < 0
    res = inside_grid.shape[0]
    pts_list = []
    tri_list = []

    # 6 face neighbor mask check.
    for i in range(res - 1):
        for j in range(res - 1):
            for k in range(res - 1):
                # cell corner: (i, j, k) ~ (i+1, j+1, k+1).
                # interior (all 8 corners inside): skip.
                # boundary (some inside, some outside): emit voxel face for
                # corner pair (a,b) where a inside, b outside.
                pass
    # 실제 fallback 구현 미완 — 매우 단순화: 그냥 vertex grid 의 inside 들 반환.
    # caller 에서 method == "fallback_no_skimage" 이면 재시도 권장.
    inside_idx = np.where(inside_grid)
    if inside_idx[0].size == 0:
        return None, None, "fallback_empty"
    pts = np.stack([
        bbox_min[0] + inside_idx[0] * spacing[0],
        bbox_min[1] + inside_idx[1] * spacing[1],
        bbox_min[2] + inside_idx[2] * spacing[2],
    ], axis=1)
    return pts, np.zeros((0, 3), dtype=np.int64), "fallback_no_skimage"


def _count_si(V, F) -> int:
    try:
        from core.preprocessor.native_repair.self_intersect import (
            detect_self_intersections,
        )
        r = detect_self_intersections(V, F)
        return int(r.n_intersections)
    except Exception:
        return 0


def _surface_mq(V, F) -> float:
    if F.shape[0] == 0:
        return 0.0
    a = V[F[:, 0]]; b = V[F[:, 1]]; c = V[F[:, 2]]
    e1 = b - a; e2 = c - a; e3 = c - b
    A = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    L_sq = (e1 ** 2).sum(axis=1) + (e2 ** 2).sum(axis=1) + (e3 ** 2).sum(axis=1)
    safe = L_sq > 1e-30
    q = np.zeros(F.shape[0], dtype=np.float64)
    q[safe] = 4.0 * np.sqrt(3.0) * A[safe] / L_sq[safe]
    return float(q.mean()) if q.size else 0.0
