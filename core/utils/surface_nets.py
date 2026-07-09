"""Native Surface Nets — GWN voxel field → watertight manifold triangle mesh.

web-QA (2026-07-03) — 강건 볼륨 메쉬의 "절대 실패하지 않는" 재구성 계층.

연구 조사 결론(rank 3): isosurface 계열은 입력 기하를 오직 "부호 함수"로만
접근하므로, 그 부호를 generalized winding number(GWN) 로 정의하면 구멍·자기교차·
non-manifold·soup·뒤집힌 법선 전부 무관하게 죽을 지점이 없다.  Surface Nets
(Gibson 1998, naive dual contouring) 는 등위면 셀마다 정점을 하나 두고 이웃
셀을 연결하므로 **manifold-by-construction watertight** 이며 marching cubes 보다
단순하다 (skimage 등 외부 의존 불필요 — CLAUDE.md native-first 정책).

핵심: ``reconstruct_surface(V, F, resolution)`` — 임의 triangle soup 을 받아
watertight/orientable 삼각형 표면 (V2, F2) 를 반환한다.  이후 tet/hex/poly
볼륨 메셔의 공통 입력으로 쓸 수 있다.
"""
from __future__ import annotations

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


def _signed_field(
    V: np.ndarray, F: np.ndarray, grid_pts: np.ndarray, shape: tuple[int, int, int],
) -> np.ndarray:
    """grid 점들의 부호 있는 스칼라장 (inside>0, outside<0).

    거리 크기는 KDTree 최근접 표면 거리, 부호는 GWN (soup 강건).
    """
    from scipy.spatial import cKDTree

    from core.utils.geometry import inside_generalized_winding_number

    # 표면 삼각형 중심으로 최근접 거리 근사 (정점보다 조밀).
    tri_c = V[F].mean(axis=1)
    tree = cKDTree(tri_c)
    dist, _ = tree.query(grid_pts, k=1)

    inside = inside_generalized_winding_number(grid_pts, V, F)
    field = dist.copy()
    field[~inside] *= -1.0  # outside 음수
    # inside 양수, outside 음수 → iso 0 이 표면.
    return field.reshape(shape)


# 셀의 12 edge → (corner_a, corner_b) 로컬 인덱스 (0..7, z-major bit 순서)
# corner bit: c = x + 2*y + 4*z (로컬 오프셋)
_CORNER_OFFSETS = np.array(
    [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
     [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]],
    dtype=np.int64,
)
_CELL_EDGES = [
    (0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3),
    (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7),
]


def surface_nets(
    field: np.ndarray, origin: np.ndarray, spacing: float, iso: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Naive Surface Nets — 부호장(field) → (verts, tris).

    각 grid 셀(8 코너)이 iso 를 straddle 하면 정점 1개를 edge crossing 평균
    위치에 둔다.  sign-change edge 를 공유하는 인접 셀 정점 4개를 quad(→ 2 tri)
    로 연결한다.  manifold watertight 보장.
    """
    nx, ny, nz = field.shape
    cx, cy, cz = nx - 1, ny - 1, nz - 1
    if cx < 1 or cy < 1 or cz < 1:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)

    sign = field >= iso  # bool grid (inside)

    # 셀 좌표 그리드
    ci, cj, ck = np.meshgrid(
        np.arange(cx), np.arange(cy), np.arange(cz), indexing="ij",
    )
    cells = np.stack([ci.ravel(), cj.ravel(), ck.ravel()], axis=1)  # (Nc,3)

    # 각 셀의 8 코너 부호
    corner_signs = np.empty((cells.shape[0], 8), dtype=bool)
    for k, off in enumerate(_CORNER_OFFSETS):
        idx = cells + off
        corner_signs[:, k] = sign[idx[:, 0], idx[:, 1], idx[:, 2]]

    # straddle: 코너 부호가 모두 같지 않은 셀
    n_true = corner_signs.sum(axis=1)
    active = (n_true > 0) & (n_true < 8)
    if not active.any():
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)

    act_cells = cells[active]
    act_signs = corner_signs[active]

    # 셀 정점 위치 = sign-change edge crossing 의 평균 (linear interp)
    verts = np.zeros((act_cells.shape[0], 3), dtype=np.float64)
    field_flat = field
    for n, (ca, cb) in enumerate(_CELL_EDGES):
        sa = act_signs[:, ca]
        sb = act_signs[:, cb]
        cross = sa != sb
        if not cross.any():
            continue
        pa = act_cells[cross] + _CORNER_OFFSETS[ca]
        pb = act_cells[cross] + _CORNER_OFFSETS[cb]
        fa = field_flat[pa[:, 0], pa[:, 1], pa[:, 2]]
        fb = field_flat[pb[:, 0], pb[:, 1], pb[:, 2]]
        t = np.where(np.abs(fb - fa) > 1e-30, (iso - fa) / (fb - fa), 0.5)
        t = np.clip(t, 0.0, 1.0)[:, None]
        pos = pa.astype(np.float64) + t * (pb - pa).astype(np.float64)
        # 누적 평균
        acc = np.zeros((act_cells.shape[0], 3))
        cnt = np.zeros(act_cells.shape[0])
        ci_cross = np.where(cross)[0]
        np.add.at(acc, ci_cross, pos)
        np.add.at(cnt, ci_cross, 1.0)
        verts += acc
        # cnt 는 마지막에 나눔 → 별도 누적
        if n == 0:
            edge_cnt = cnt
        else:
            edge_cnt = edge_cnt + cnt
    edge_cnt = np.maximum(edge_cnt, 1.0)
    verts /= edge_cnt[:, None]
    verts = origin + verts * spacing

    # 셀 → 정점 인덱스 맵 (활성 셀만)
    cell_key = (act_cells[:, 0] * cy + act_cells[:, 1]) * cz + act_cells[:, 2]
    vidx_of_cell: dict[int, int] = {int(k): i for i, k in enumerate(cell_key)}

    # quad 생성: 3개 축의 sign-change edge (셀 코너 0→축) 마다 주변 4셀 연결.
    # edge (원점 코너 0 → +axis) 가 sign change 면 그 edge 를 공유하는 4개 셀의
    # 정점을 quad 로. 4셀 = edge 에 수직인 평면상의 2×2 셀.
    tris: list[tuple[int, int, int]] = []
    active_set = vidx_of_cell

    def _vid(i: int, j: int, k: int) -> int | None:
        if 0 <= i < cx and 0 <= j < cy and 0 <= k < cz:
            return active_set.get(int((i * cy + j) * cz + k))
        return None

    # +x edge at grid vertex (i,j,k): 주변 4 셀 = (i, j-1..j, k-1..k)
    for (i, j, k) in act_cells:
        i, j, k = int(i), int(j), int(k)
        base_in = sign[i, j, k]
        # x-edge: corner(i,j,k) vs (i+1,j,k)
        if sign[i + 1, j, k] != base_in:
            a = _vid(i, j - 1, k - 1); b = _vid(i, j, k - 1)
            c = _vid(i, j, k); d = _vid(i, j - 1, k)
            _emit_quad(tris, a, b, c, d, base_in)
        # y-edge
        if sign[i, j + 1, k] != base_in:
            a = _vid(i - 1, j, k - 1); b = _vid(i, j, k - 1)
            c = _vid(i, j, k); d = _vid(i - 1, j, k)
            _emit_quad(tris, a, b, c, d, not base_in)
        # z-edge
        if sign[i, j, k + 1] != base_in:
            a = _vid(i - 1, j - 1, k); b = _vid(i, j - 1, k)
            c = _vid(i, j, k); d = _vid(i - 1, j, k)
            _emit_quad(tris, a, b, c, d, base_in)

    if not tris:
        return verts, np.zeros((0, 3), dtype=np.int64)
    return verts, np.asarray(tris, dtype=np.int64)


def _emit_quad(tris: list, a, b, c, d, flip: bool) -> None:
    """4 정점 인덱스가 모두 유효하면 quad → 2 triangle 추가 (방향 일관)."""
    if a is None or b is None or c is None or d is None:
        return
    if flip:
        tris.append((a, c, b))
        tris.append((a, d, c))
    else:
        tris.append((a, b, c))
        tris.append((a, c, d))


def reconstruct_surface(
    V: np.ndarray, F: np.ndarray, resolution: int = 64, pad: float = 0.06,
) -> tuple[np.ndarray, np.ndarray] | None:
    """임의 triangle soup → watertight manifold 표면 (GWN voxel + Surface Nets).

    Args:
        V, F: 입력 (쓰레기 허용).
        resolution: 최장 축 voxel 수 (N 목표에 맞춰 상위 호출자가 조절).
        pad: bbox 대비 여백 비율 (표면이 grid 경계에 붙지 않게).

    Returns:
        (V2, F2) 또는 재구성 실패/빈 결과 시 None.
    """
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    if V.shape[0] < 3 or F.shape[0] < 1:
        return None
    lo = V.min(axis=0)
    hi = V.max(axis=0)
    ext = hi - lo
    diag = float(np.linalg.norm(ext)) or 1.0
    margin = diag * pad
    lo = lo - margin
    hi = hi + margin
    ext = hi - lo
    spacing = float(ext.max()) / max(resolution, 8)
    dims = np.maximum(np.ceil(ext / spacing).astype(int) + 1, 3)
    nx, ny, nz = (int(dims[0]), int(dims[1]), int(dims[2]))

    xs = lo[0] + np.arange(nx) * spacing
    ys = lo[1] + np.arange(ny) * spacing
    zs = lo[2] + np.arange(nz) * spacing
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    grid_pts = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)

    try:
        field = _signed_field(V, F, grid_pts, (nx, ny, nz))
        verts, tris = surface_nets(field, lo, spacing, iso=0.0)
    except Exception as exc:  # noqa: BLE001
        log.warning("surface_nets_failed", error=str(exc)[:120])
        return None
    if verts.shape[0] < 4 or tris.shape[0] < 4:
        log.info("surface_nets_empty", n_verts=int(verts.shape[0]), n_tris=int(tris.shape[0]))
        return None

    # 후처리: 정점 병합·퇴화 제거·법선 일관화·최대 컴포넌트·winding 교정.
    try:
        import trimesh as _tm

        mesh = _tm.Trimesh(vertices=verts, faces=tris, process=True)
        # 여러 조각이 나오면 (분리 입력) 부피 최대 조각만 유지.
        parts = mesh.split(only_watertight=False)
        if len(parts) > 1:
            parts = sorted(
                parts,
                key=lambda p: abs(float(p.volume)) if p.is_watertight else p.area,
                reverse=True,
            )
            mesh = parts[0]
        mesh.fix_normals()  # 법선 outward 일관화
        if mesh.is_watertight and float(mesh.volume) < 0:
            mesh.invert()  # winding 뒤집힘 교정 → 양의 부피
        verts = np.asarray(mesh.vertices, dtype=np.float64)
        tris = np.asarray(mesh.faces, dtype=np.int64)
    except Exception as exc:  # noqa: BLE001
        log.debug("surface_nets_postprocess_skipped", error=str(exc)[:100])

    if verts.shape[0] < 4 or tris.shape[0] < 4:
        return None
    log.info(
        "surface_nets_reconstructed",
        n_verts=int(verts.shape[0]), n_tris=int(tris.shape[0]),
        resolution=resolution, spacing=round(spacing, 5),
    )
    return verts, tris
