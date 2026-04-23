"""native_hex MVP 메쉬 생성기 — uniform hex grid + inside filter."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class NativeHexResult:
    success: bool
    elapsed: float
    n_cells: int = 0
    n_points: int = 0
    n_faces: int = 0
    message: str = ""


# OpenFOAM hex cell 의 6 face 정의 — 각 face 는 4 vertex (CCW from outside).
# hex vertex 순서: 0..7 (그림 ↓ OpenFOAM convention):
#   3 - 2
#   0 - 1     (bottom, z=0)
#   7 - 6
#   4 - 5     (top, z=+)
# faces (outward normal):
#   bottom  (0,3,2,1) normal -z
#   top     (4,5,6,7) normal +z
#   front   (0,1,5,4) normal -y
#   back    (3,7,6,2) normal +y
#   left    (0,4,7,3) normal -x
#   right   (1,2,6,5) normal +x
_HEX_FACES: tuple[tuple[int, int, int, int], ...] = (
    (0, 3, 2, 1),   # bottom -z
    (4, 5, 6, 7),   # top    +z
    (0, 1, 5, 4),   # front  -y
    (3, 7, 6, 2),   # back   +y
    (0, 4, 7, 3),   # left   -x
    (1, 2, 6, 5),   # right  +x
)


from core.utils.geometry import inside_winding_number as _inside_winding_number


def _write_polymesh_hex(
    vertices: np.ndarray, hexes: np.ndarray, case_dir: Path,
) -> dict[str, int]:
    """hex (N, 8) array → OpenFOAM polyMesh (``write_generic_polymesh`` wrapper).

    각 hex 셀의 6 face 를 OpenFOAM 외향 vertex 순서로 변환 → generic writer 위임.
    """
    from core.generator.polymesh_writer import write_generic_polymesh  # noqa: PLC0415

    cell_faces: list[list[list[int]]] = []
    for cell in hexes:
        faces = [[int(cell[v]) for v in local] for local in _HEX_FACES]
        cell_faces.append(faces)

    return write_generic_polymesh(vertices, cell_faces, case_dir)


def generate_native_hex(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 16,
    snap_boundary: bool = False,
    max_cells_per_axis: int = 50,
    preserve_features: bool = False,
    feature_angle_deg: float = 45.0,
) -> NativeHexResult:
    """uniform hex grid 생성 + inside filter.

    Args:
        vertices: (V, 3) 표면 점.
        faces: (F, 3) 표면 triangles.
        case_dir: 결과 case 디렉터리.
        target_edge_length: hex edge length. None 이면 bbox_diag / seed_density.
        seed_density: target_edge_length None 일 때 bbox_diag 분할 수.
        snap_boundary: True 면 boundary 근처 hex vertex 를 STL surface 로
            projection (Hausdorff 개선). skewness 저하 방지용 safety cap 내장.
            기본 False (backwards compat).
        max_cells_per_axis: 각 축당 최대 cell 수 (총 cell <= N^3). 기본 50 → 125k
            cell. 과도한 grid 폭주 방지. target_edge_length 가 너무 작아 cap 이
            걸리면 log 에 ``native_hex_grid_capped`` warning 을 남긴다.

    Returns:
        NativeHexResult.
    """
    t0 = time.perf_counter()
    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    if V.size == 0 or F.size == 0:
        return NativeHexResult(False, 0.0, message="빈 입력 mesh")

    bmin = V.min(axis=0); bmax = V.max(axis=0)
    diag = float(np.linalg.norm(bmax - bmin))
    if target_edge_length is None or target_edge_length <= 0:
        target_edge_length = diag / max(1, int(seed_density))
    h = float(target_edge_length)

    # 각 축별 grid size — max_cells_per_axis 로 제한 (과도한 셀 방지)
    cap = max(1, int(max_cells_per_axis))
    nxyz_req = np.maximum(
        np.ceil((bmax - bmin) / h).astype(int), 1,
    )
    nxyz = np.minimum(nxyz_req, cap)
    if np.any(nxyz_req > cap):
        log.warning(
            "native_hex_grid_capped",
            requested=nxyz_req.tolist(), capped=nxyz.tolist(), cap=cap,
            target_edge=h,
            hint="max_cells_per_axis 늘리거나 target_edge_length 증가 권장",
        )
    nx, ny, nz = int(nxyz[0]), int(nxyz[1]), int(nxyz[2])

    # vertex coords
    xs = np.linspace(bmin[0], bmax[0], nx + 1)
    ys = np.linspace(bmin[1], bmax[1], ny + 1)
    zs = np.linspace(bmin[2], bmax[2], nz + 1)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    grid_pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)

    def _pid(i: int, j: int, k: int) -> int:
        return i * (ny + 1) * (nz + 1) + j * (nz + 1) + k

    # 각 cell (i, j, k) 의 8 vertex id (OpenFOAM hex order)
    cells: list[tuple[int, ...]] = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                p0 = _pid(i,     j,     k    )
                p1 = _pid(i + 1, j,     k    )
                p2 = _pid(i + 1, j + 1, k    )
                p3 = _pid(i,     j + 1, k    )
                p4 = _pid(i,     j,     k + 1)
                p5 = _pid(i + 1, j,     k + 1)
                p6 = _pid(i + 1, j + 1, k + 1)
                p7 = _pid(i,     j + 1, k + 1)
                cells.append((p0, p1, p2, p3, p4, p5, p6, p7))

    if not cells:
        return NativeHexResult(
            False, time.perf_counter() - t0,
            message="grid 가 비어있음 (target_edge_length 가 bbox 보다 큼)",
        )

    hexes = np.array(cells, dtype=np.int64)
    # centroid 로 inside 판정
    centroids = grid_pts[hexes].mean(axis=1)
    inside = _inside_winding_number(centroids, V, F)
    kept = hexes[inside]
    if kept.shape[0] == 0:
        return NativeHexResult(
            False, time.perf_counter() - t0,
            message="inside hex 0 — target_edge_length 조정 필요",
        )

    # 사용된 vertex 만 압축
    used = np.unique(kept.ravel())
    remap = -np.ones(grid_pts.shape[0], dtype=np.int64)
    remap[used] = np.arange(used.shape[0])
    final_hexes = remap[kept].astype(np.int64)
    final_pts = grid_pts[used]

    # v0.4.0-beta22: optional boundary snap — hex vertex 를 STL surface 로 projection.
    # beta66: preserve_features 로 sharp corner 는 feature vertex 에 직접 snap.
    if snap_boundary:
        try:
            from core.generator.native_hex.snap import (  # noqa: PLC0415
                snap_hex_boundary_to_surface,
            )
            final_pts, snap_stats = snap_hex_boundary_to_surface(
                final_pts, V, F, target_edge=h,
                preserve_features=preserve_features,
                feature_angle_deg=feature_angle_deg,
            )
            log.info("native_hex_boundary_snap_applied", **snap_stats)
        except Exception as exc:
            log.warning("native_hex_boundary_snap_failed", error=str(exc))

    # 최소 system/controlDict + fvSchemes + fvSolution 생성 (checkMesh 가 요구).
    from core.generator.tier_layers_post import (  # noqa: PLC0415
        _ensure_minimal_controldict, _write_minimal_fv_dicts,
    )
    _ensure_minimal_controldict(case_dir)
    _write_minimal_fv_dicts(case_dir)

    try:
        stats = _write_polymesh_hex(final_pts, final_hexes, case_dir)
    except Exception as exc:
        return NativeHexResult(
            False, time.perf_counter() - t0,
            message=f"polyMesh 쓰기 실패: {exc}",
        )

    return NativeHexResult(
        success=True,
        elapsed=time.perf_counter() - t0,
        n_cells=int(stats["num_cells"]),
        n_points=int(stats["num_points"]),
        n_faces=int(stats["num_faces"]),
        message=(
            f"native_hex OK — cells={stats['num_cells']}, "
            f"points={stats['num_points']}, grid=({nx},{ny},{nz}), "
            f"target_edge={h:.4g}"
        ),
    )
