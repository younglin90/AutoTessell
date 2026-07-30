"""native_hex MVP 메쉬 생성기 — uniform hex grid + inside filter."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import numpy as np

from core.utils.logging import get_logger
from core.utils.native_extensions import load_native_metrics

if TYPE_CHECKING:
    from core.generator.native_hex.source_feature_sidecar_l1 import (
        AuthoritativeSourceFeatureManifest,
    )

log = get_logger(__name__)

try:
    from core.generator.native_tet._native import (
        hex_validate_volumes_batch as _c_hex_validate_volumes_batch,
    )
except Exception:  # pragma: no cover - native extension optional
    _c_hex_validate_volumes_batch = None

# HEX_CACHE (beta2177) — single-slot LRU adjacency cache keyed on hex_cells.tobytes().
# Mirrors PERF3/4 (R113/R114) tet adjacency cache.  Default ON.
# Set AUTO_TESSELL_HEX_CACHE_OFF=1 to disable.


class _HexAdjCache(NamedTuple):
    """Cached adjacency maps for a hex mesh."""

    face_map: "dict[tuple[int, int, int, int], list[int]]"  # sorted-face → [cell_idx, ...]
    edge_nbrs: "list[set[int]]"  # vertex → neighbour vertex set
    boundary_verts: "set[int]"  # vertices on boundary faces


_hex_adj_cache: tuple[bytes, _HexAdjCache] | None = None  # (key, cache)


def _build_hex_adjacency(hex_cells: np.ndarray) -> _HexAdjCache:
    """Build face_map + edge_nbrs + boundary_verts for *hex_cells*.

    Single-slot LRU: if hex_cells.tobytes() matches the cached key,
    return cached result without rebuilding.
    """
    import os as _os_cache

    global _hex_adj_cache

    if not _os_cache.environ.get("AUTO_TESSELL_HEX_CACHE_OFF"):
        key = hex_cells.tobytes()
        if _hex_adj_cache is not None and _hex_adj_cache[0] == key:
            return _hex_adj_cache[1]

    n_cells = hex_cells.shape[0]

    # face_map: sorted 4-tuple → list of owner cell indices
    # C-PERF-51 / beta2502 — vectorize via lexsort + group-boundary.
    if n_cells == 0:
        face_map: dict[tuple[int, int, int, int], list[int]] = {}
        boundary_verts: set[int] = set()
    else:
        _HEX_FACES_IDX = np.array(_HEX_FACES, dtype=np.int64)  # (6, 4)
        # gather all face vertices: (n_cells, 6, 4)
        faces_arr = np.sort(
            hex_cells[:, _HEX_FACES_IDX].reshape(-1, 4),
            axis=1,
        )
        ci_face = np.repeat(np.arange(n_cells, dtype=np.int64), 6)
        order_hf = np.lexsort(
            (faces_arr[:, 3], faces_arr[:, 2], faces_arr[:, 1], faces_arr[:, 0]),
        )
        f_s = faces_arr[order_hf]
        ci_s = ci_face[order_hf]
        diff_hf = np.r_[True, np.any(f_s[1:] != f_s[:-1], axis=1)]
        starts_hf = np.where(diff_hf)[0]
        ends_hf = np.r_[starts_hf[1:], len(f_s)]
        sizes_hf = ends_hf - starts_hf
        face_map = {}
        for s, e in zip(starts_hf.tolist(), ends_hf.tolist()):
            k = (int(f_s[s, 0]), int(f_s[s, 1]), int(f_s[s, 2]), int(f_s[s, 3]))
            face_map[k] = ci_s[s:e].tolist()

        # boundary vertices: faces with exactly 1 owner.
        bnd_starts = starts_hf[sizes_hf == 1]
        boundary_verts = set()
        if bnd_starts.size > 0:
            boundary_verts.update(np.unique(f_s[bnd_starts].ravel()).tolist())

    # edge neighbour map for Laplacian smooth
    # C-PERF-52 / beta2503 — vectorize via flat src/dst (24 directed edges
    # per hex = 12 pairs × 2 dirs) + sort + bincount-offset + np.unique.
    _EDGE_PAIRS = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    ]
    n_pts = int(hex_cells.max()) + 1 if n_cells > 0 else 0
    if n_cells == 0:
        edge_nbrs: list[set[int]] = [set() for _ in range(n_pts)]
    else:
        ep_arr = np.array(_EDGE_PAIRS, dtype=np.int64)  # (12, 2)
        # both directions: (24, 2) per hex
        ep_dir = np.concatenate([ep_arr, ep_arr[:, [1, 0]]])  # (24, 2)
        src_en = hex_cells[:, ep_dir[:, 0]].reshape(-1).astype(np.int64)
        dst_en = hex_cells[:, ep_dir[:, 1]].reshape(-1).astype(np.int64)
        order_en = np.argsort(src_en, kind="stable")
        src_s = src_en[order_en]
        dst_s = dst_en[order_en]
        counts_en = np.bincount(src_s, minlength=n_pts)
        offs_en = np.concatenate(([0], np.cumsum(counts_en).astype(np.int64)))
        edge_nbrs = [
            set(np.unique(dst_s[offs_en[i] : offs_en[i + 1]]).tolist()) for i in range(n_pts)
        ]

    result = _HexAdjCache(face_map=face_map, edge_nbrs=edge_nbrs, boundary_verts=boundary_verts)

    if not _os_cache.environ.get("AUTO_TESSELL_HEX_CACHE_OFF"):
        key = hex_cells.tobytes()
        _hex_adj_cache = (key, result)

    return result


@dataclass
class NativeHexResult:
    success: bool
    elapsed: float
    n_cells: int = 0
    n_points: int = 0
    n_faces: int = 0
    message: str = ""
    # beta88: 볼륨 커버리지 통계
    fill_ratio: float = 0.0  # kept_cells / total_grid_cells (stair-step 품질 지표)
    grid_shape: tuple[int, int, int] = (0, 0, 0)
    n_grid_total: int = 0  # inside filter 이전 전체 grid cell 수
    # X1 (beta1640) — checkMesh-style quality + grade.
    quality_grade: str = "?"
    max_non_orthogonality_deg: float = -1.0
    mean_non_orthogonality_deg: float = -1.0
    max_skewness: float = -1.0
    mean_skewness: float = -1.0
    max_aspect: float = -1.0
    plane_coverage: float = -1.0
    plane_area_coverage: float = -1.0
    # beta2337 — pre-mesh self-intersect (P2.6 chain). None = 측정 안 됨,
    # 0 = clean, >0 = 입력 SI 존재. native_tet (beta2336) 와 동일 필드.
    n_self_intersect_pre: int | None = None
    # C-QUAL-11 / beta2407 — mesh_integrity_suspect (NativeTetResult / NativePolyResult parity).
    # n_cells < 50 (절대 floor) 또는 V_surf >= 100 + n_cells < V_surf/32 시 True.
    mesh_integrity_suspect: bool = False
    cell_census: dict[str, int] | None = None
    hex_count: int | None = None
    prism_count: int | None = None
    tet_count: int | None = None
    other_count: int | None = None
    poly_count: int | None = None
    hex_count_fraction: float | None = None
    prism_count_fraction: float | None = None
    tet_count_fraction: float | None = None
    other_count_fraction: float | None = None
    hex_volume_fraction: float | None = None
    prism_volume_fraction: float | None = None
    tet_volume_fraction: float | None = None
    other_volume_fraction: float | None = None
    poly_volume_fraction: float | None = None
    cell_count_fractions: dict[str, float] | None = None
    cell_volume_fractions: dict[str, float] | None = None
    cell_volumes: dict[str, float] | None = None
    total_volume: float | None = None
    score_che: float | None = None
    n_hex_clusters: int | None = None
    largest_cluster_frac: float | None = None
    untangle_beta: float | None = None
    untangle_min_corner_jacobian: float | None = None
    untangle_local_mean_volume: float | None = None
    untangle_beta_margin: float | None = None
    untangle_beta_margin_ratio: float | None = None
    untangle_beta_pass: bool | None = None


def _prepare_native_hex_surface_input(
    vertices: object,
    faces: object,
) -> tuple[np.ndarray | None, np.ndarray | None, str | None]:
    """Convert only well-formed finite indexed triangles for native hex.

    This is deliberately a narrow ingress check.  It does not repair input or
    impose closed-manifold, orientation, feature, or component requirements.
    Valid source geometry remains byte-for-byte caller-owned.
    """
    try:
        raw_points = np.asarray(vertices)
        raw_faces = np.asarray(faces)
    except (TypeError, ValueError):
        return None, None, "array_conversion"

    if raw_points.size == 0 or raw_faces.size == 0:
        return None, None, "empty_mesh"
    if raw_points.ndim != 2 or raw_points.shape[1:] != (3,):
        return None, None, "vertices_must_have_shape_n_by_3"
    if raw_faces.ndim != 2 or raw_faces.shape[1:] != (3,):
        return None, None, "faces_must_have_shape_n_by_3"

    try:
        points = np.asarray(raw_points, dtype=np.float64)
        face_values = np.asarray(raw_faces, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        return None, None, "non_numeric_input"
    if not np.all(np.isfinite(points)):
        return None, None, "non_finite_vertex"
    if not np.all(np.isfinite(face_values)):
        return None, None, "non_finite_face_index"
    if np.any(face_values != np.floor(face_values)):
        return None, None, "non_integral_face_index"
    if np.any(face_values < 0) or np.any(face_values >= len(points)):
        return None, None, "face_index_out_of_range"

    triangles = face_values.astype(np.int64, copy=False)
    if np.any(
        (triangles[:, 0] == triangles[:, 1])
        | (triangles[:, 1] == triangles[:, 2])
        | (triangles[:, 2] == triangles[:, 0])
    ):
        return None, None, "repeated_face_vertex"
    return points, triangles, None


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
    (0, 3, 2, 1),  # bottom -z
    (4, 5, 6, 7),  # top    +z
    (0, 1, 5, 4),  # front  -y
    (3, 7, 6, 2),  # back   +y
    (0, 4, 7, 3),  # left   -x
    (1, 2, 6, 5),  # right  +x
)


# web-QA (2026-07-02): ray-parity → inside_robust 디스패처.
# closed manifold 는 기존 ray parity(빠름) 그대로, 구멍·non-manifold·soup 는
# generalized winding number 로 자동 전환 — 쓰레기 표면 inside 오판 방지.
from core.utils.geometry import inside_robust as _inside_winding_number


def _write_polymesh_hex(
    vertices: np.ndarray,
    hexes: np.ndarray,
    case_dir: Path,
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


def _native_hex_phase0_metrics(
    case_dir: Path,
    fallback_points: np.ndarray,
    fallback_cell_faces: list[list[list[int]]],
    *,
    path: str,
    n_written: int,
) -> dict[str, object]:
    """Compute report-only Phase 0 metrics from the written topology."""
    from core.generator.native_hex.metrics import (
        compute_native_hex_metrics,
        metrics_log_fields,
        read_written_polymesh_cells,
    )

    written = read_written_polymesh_cells(case_dir)
    if written is None or len(written[1]) != int(n_written):
        points = fallback_points
        cell_faces = fallback_cell_faces
        log.warning(
            "native_hex_phase0_written_topology_unavailable",
            path=path,
            n_written=int(n_written),
            n_metric_cells=len(cell_faces),
        )
    else:
        points, cell_faces = written

    metrics = compute_native_hex_metrics(points, cell_faces)
    fields = metrics_log_fields(metrics)
    log.info(
        "native_hex_phase0_metrics",
        path=path,
        n_written=int(n_written),
        census_cells=int(sum(metrics.cell_census.values())),
        **fields,
    )
    return fields


def _estimate_bl_final_cells_from_cell_faces(
    cell_faces: list[list[list[int]]],
    *,
    n_layers: int,
) -> tuple[int, int, int, int]:
    """Estimate final hex+BL cell count before writing polyMesh.

    Native BL triangulates polygonal wall faces and inserts one prism per
    triangle per layer. For hex walls that means two prism cells per quad per
    layer, not one.
    """
    n_base = int(len(cell_faces))
    layers = max(0, int(n_layers))
    if n_base <= 0 or layers <= 0:
        return n_base, 0, 0, n_base

    face_counts: dict[tuple[int, ...], int] = {}
    for faces_of_cell in cell_faces:
        for face in faces_of_cell:
            if len(face) < 3:
                continue
            key = tuple(sorted(int(v) for v in face))
            face_counts[key] = face_counts.get(key, 0) + 1
    n_boundary_faces = 0
    n_boundary_facets = 0
    for key, count in face_counts.items():
        if count != 1:
            continue
        n_boundary_faces += 1
        n_boundary_facets += max(1, len(key) - 2)
    return (
        n_base,
        int(n_boundary_faces),
        int(n_boundary_facets),
        int(n_base + n_boundary_facets * layers),
    )


# VAL2 (beta2148) — global negative-volume hex cell validation (3-engine defensive parity).
# env AUTO_TESSELL_VAL2_OFF=1 to disable. Default ON.
def validate_hex_cell_volumes(
    hex_pts: np.ndarray,
    hex_cells: np.ndarray,
    *,
    degenerate_eps: float = 1e-20,
) -> tuple[np.ndarray, int, int]:
    """For each hex (8 verts), decompose into 6 tets, sum signed volumes.

    If V < 0, attempt to flip orientation by swapping top/bottom layers:
        [0,1,2,3,4,5,6,7] → [4,5,6,7,0,1,2,3]
    Re-check; if still V < 0, log degenerate and mark.

    Returns:
        (hex_cells_fixed, n_flipped, n_degenerate)
    """
    import os as _os  # noqa: PLC0415

    if _os.environ.get("AUTO_TESSELL_VAL2_OFF"):
        return hex_cells, 0, 0

    hex_cells = np.asarray(hex_cells, dtype=np.int64).copy()
    pts = np.asarray(hex_pts, dtype=np.float64)
    n = len(hex_cells)
    if n == 0:
        log.info("native_hex_validate", n_cells=0, n_flipped=0, n_degenerate=0)
        return hex_cells, 0, 0

    native_metrics = load_native_metrics()
    if native_metrics is not None and hasattr(native_metrics, "validate_hex_volumes"):
        try:
            fixed, n_flipped, n_degenerate = native_metrics.validate_hex_volumes(
                pts,
                hex_cells,
                float(degenerate_eps),
            )
            fixed_arr = np.asarray(fixed, dtype=np.int64)
            log.info(
                "native_hex_validate",
                n_cells=n,
                n_flipped=int(n_flipped),
                n_degenerate=int(n_degenerate),
                backend="pybind",
            )
            return fixed_arr, int(n_flipped), int(n_degenerate)
        except Exception as exc:  # noqa: BLE001
            log.debug("native_metrics.validate_hex_volumes failed", error=str(exc))

    if _c_hex_validate_volumes_batch is not None:
        native = _c_hex_validate_volumes_batch(pts, hex_cells, float(degenerate_eps))
        if native is not None:
            fixed, n_flipped, n_degenerate = native
            log.info(
                "native_hex_validate",
                n_cells=n,
                n_flipped=n_flipped,
                n_degenerate=n_degenerate,
            )
            return fixed, n_flipped, n_degenerate

    # 6-tet decomposition of a hex (local vertex indices).
    # Standard decomposition into 5 or 6 tets; use 6-tet fan from vertex 0.
    _HEX_TETS = np.array(
        [
            [0, 1, 3, 4],
            [1, 2, 3, 6],
            [3, 4, 6, 7],
            [1, 4, 5, 6],
            [1, 3, 4, 6],
            [0, 3, 4, 7],  # unused but keeps symmetry; use first 5 only
        ],
        dtype=np.int64,
    )

    def _hex_signed_vol(cell: np.ndarray) -> float:
        """Signed volume of hex via 5-tet decomposition."""
        _5TETS = [
            [0, 1, 3, 4],
            [1, 2, 3, 6],
            [3, 4, 6, 7],
            [1, 4, 5, 6],
            [1, 3, 4, 6],
        ]
        total = 0.0
        for tet_idx in _5TETS:
            v = pts[cell[tet_idx]]
            total += float(np.dot(v[1] - v[0], np.cross(v[2] - v[0], v[3] - v[0])))
        return total

    n_flipped = 0
    n_degenerate = 0
    # C-PERF-54 / beta2505 — bulk pre-compute volumes, only loop over negative.
    if n > 0:
        _5T = np.array(
            [[0, 1, 3, 4], [1, 2, 3, 6], [3, 4, 6, 7], [1, 4, 5, 6], [1, 3, 4, 6]], dtype=np.int64
        )
        verts = pts[hex_cells[:, _5T]]  # (N, 5, 4, 3)
        v0_b = verts[:, :, 0, :]
        v1_b = verts[:, :, 1, :] - v0_b
        v2_b = verts[:, :, 2, :] - v0_b
        v3_b = verts[:, :, 3, :] - v0_b
        vols = (v1_b * np.cross(v2_b, v3_b)).sum(axis=2).sum(axis=1)
        neg_idx = np.where(vols < -float(degenerate_eps))[0]
        for ci_int in neg_idx.tolist():
            ci = int(ci_int)
            vol = float(vols[ci])
            orig = hex_cells[ci].copy()
            hex_cells[ci] = orig[[4, 5, 6, 7, 0, 1, 2, 3]]
            vol2 = _hex_signed_vol(hex_cells[ci])
            if vol2 < -float(degenerate_eps):
                hex_cells[ci] = orig
                n_degenerate += 1
                log.warning(
                    "native_hex_degenerate_volume",
                    cell_idx=ci,
                    vol=round(vol, 6),
                )
            else:
                n_flipped += 1

    log.info(
        "native_hex_validate",
        n_cells=n,
        n_flipped=n_flipped,
        n_degenerate=n_degenerate,
    )
    return hex_cells, n_flipped, n_degenerate


# VAL3 (beta2161) — per-pass negative-volume hex tracker (diagnostic, default ON).
# env AUTO_TESSELL_HEX_VAL3_OFF=1 to disable. Mirror of R105 VAL3 (tet).
def _count_neg_vol_hex(hex_pts: np.ndarray, hex_cells: np.ndarray) -> int:
    """Count hex cells with negative signed volume (5-tet decomposition). Read-only."""
    import os as _os_v3

    if _os_v3.environ.get("AUTO_TESSELL_HEX_VAL3_OFF"):
        return 0
    if hex_cells is None or len(hex_cells) == 0:
        return 0
    pts = np.asarray(hex_pts, dtype=np.float64)
    cells = np.asarray(hex_cells, dtype=np.int64)
    # Vectorized 5-tet signed-volume sum over all cells.
    # _5TETS local indices: (5, 4)
    _5T = np.array(
        [[0, 1, 3, 4], [1, 2, 3, 6], [3, 4, 6, 7], [1, 4, 5, 6], [1, 3, 4, 6]], dtype=np.int64
    )
    # verts shape: (N, 5, 4, 3)
    verts = pts[cells[:, _5T]]  # (N, 5, 4, 3)
    v0 = verts[:, :, 0, :]  # (N, 5, 3)
    v1 = verts[:, :, 1, :] - v0  # (N, 5, 3)
    v2 = verts[:, :, 2, :] - v0  # (N, 5, 3)
    v3 = verts[:, :, 3, :] - v0  # (N, 5, 3)
    cross = np.cross(v2, v3)  # (N, 5, 3)
    dot = (v1 * cross).sum(axis=2)  # (N, 5)
    vol = dot.sum(axis=1)  # (N,)
    return int((vol < 0.0).sum())


def _reduce_nonortho_post(
    hex_pts: np.ndarray,
    hex_cells: np.ndarray,
    *,
    threshold_deg: float = 48.0,
    top_k: int = 40,
    min_improve_deg: float = 1.0,
) -> np.ndarray:
    """HEX_QUALITY1: local vert re-snap to reduce non-orthogonality.

    For each internal face with non-ortho > threshold_deg (top_k worst),
    nudge the 4 face verts by 0.1 × cell-cell-vector projection.
    STRICT GUARD: revert if max non-ortho over incident faces does not
    improve by at least min_improve_deg.

    Returns updated hex_pts (copy if any moves accepted).
    """
    from core.generator.native_hex.quality import (  # noqa: PLC0415
        _native_hex_face_nonorthogonality,
    )

    pts = hex_pts.copy()
    n_cells = hex_cells.shape[0]

    # HEX_CACHE: reuse cached face_map if hex_cells unchanged.
    _adj = _build_hex_adjacency(hex_cells)
    face_map = _adj.face_map

    def _face_nonortho(p: np.ndarray, v4: tuple[int, int, int, int]) -> float:
        """Non-orthogonality of a quad face between its two owner cells."""
        key = tuple(sorted(v4))  # type: ignore[assignment]
        owners = face_map.get(key, [])  # type: ignore[arg-type]
        if len(owners) < 2:
            return 0.0  # boundary face — skip
        c0 = p[hex_cells[owners[0]]].mean(axis=0)
        c1 = p[hex_cells[owners[1]]].mean(axis=0)
        cc = c1 - c0
        cc_len = float(np.linalg.norm(cc))
        if cc_len < 1e-30:
            return 0.0
        # face normal from the quad (v4 CCW order)
        a, b, c, d = [p[x] for x in v4]
        n_vec = np.cross(c - a, d - b)
        n_len = float(np.linalg.norm(n_vec))
        if n_len < 1e-30:
            return 0.0
        cos_a = abs(float(np.dot(n_vec / n_len, cc / cc_len)))
        cos_a = min(1.0, cos_a)
        return float(np.degrees(np.arccos(cos_a)))

    def _face_nonortho_many(
        p: np.ndarray,
        specs: list[tuple[tuple[int, int, int, int], int, int]],
    ) -> np.ndarray:
        if not specs:
            return np.zeros(0, dtype=np.float64)
        face_array = np.asarray([spec[0] for spec in specs], dtype=np.int64)
        owner_array = np.asarray(
            [[spec[1], spec[2]] for spec in specs], dtype=np.int64
        )
        native_angles = _native_hex_face_nonorthogonality(
            p, hex_cells, face_array, owner_array
        )
        if native_angles is not None:
            return native_angles
        return np.asarray(
            [_face_nonortho(p, spec[0]) for spec in specs],
            dtype=np.float64,
        )

    # Collect internal faces and their non-ortho angles.
    internal: list[tuple[float, tuple[int, int, int, int], int, int]] = []
    internal_specs: list[tuple[tuple[int, int, int, int], int, int]] = []
    for ci in range(n_cells):
        for face_local in _HEX_FACES:
            v4 = tuple(int(hex_cells[ci, k]) for k in face_local)
            key = tuple(sorted(v4))  # type: ignore[assignment]
            owners = face_map.get(key, [])  # type: ignore[arg-type]
            if len(owners) == 2 and owners[0] == ci:  # process once per face
                internal_specs.append((v4, owners[0], owners[1]))  # type: ignore[arg-type]
    internal_angles = _face_nonortho_many(pts, internal_specs)
    for ang, (v4, owner0, owner1) in zip(internal_angles, internal_specs):
        if ang > threshold_deg:
            internal.append((float(ang), v4, owner0, owner1))

    if not internal:
        return pts  # nothing to do

    # Sort worst first, take top_k.
    internal.sort(key=lambda t: t[0], reverse=True)
    internal = internal[:top_k]

    n_moved = 0
    for ang_pre, v4, ci0, ci1 in internal:
        c0 = pts[hex_cells[ci0]].mean(axis=0)
        c1 = pts[hex_cells[ci1]].mean(axis=0)
        cc = c1 - c0
        cc_len = float(np.linalg.norm(cc))
        if cc_len < 1e-30:
            continue

        # face centroid & normal
        face_verts = pts[list(v4)]
        face_cen = face_verts.mean(axis=0)
        n_vec = np.cross(face_verts[2] - face_verts[0], face_verts[3] - face_verts[1])
        n_len = float(np.linalg.norm(n_vec))
        if n_len < 1e-30:
            continue
        n_hat = n_vec / n_len
        # projection of cc onto n_hat — nudge direction
        proj = float(np.dot(cc / cc_len, n_hat))
        delta = 0.1 * proj * n_hat * cc_len

        # pre-incident non-ortho for guard
        incident_specs: list[tuple[tuple[int, int, int, int], int, int]] = []
        for ci in (ci0, ci1):
            for fl in _HEX_FACES:
                incident_face = tuple(int(hex_cells[ci, k]) for k in fl)
                incident_owners = face_map.get(tuple(sorted(incident_face)), [])
                if len(incident_owners) >= 2:
                    incident_specs.append(
                        (incident_face, incident_owners[0], incident_owners[1])
                    )
                else:
                    incident_specs.append((incident_face, -1, -1))
        pre_max = float(np.max(_face_nonortho_many(pts, incident_specs)))

        # Apply move
        orig = {vi: pts[vi].copy() for vi in v4}
        for vi in v4:
            pts[vi] = pts[vi] + delta

        post_max = float(np.max(_face_nonortho_many(pts, incident_specs)))
        if post_max <= pre_max - min_improve_deg:
            n_moved += 1
        else:
            # revert
            for vi, p in orig.items():
                pts[vi] = p

    log.info("hex_quality_postpass", n_candidate=len(internal), n_moved=n_moved)
    return pts


# BETA_HEX_WALLFIT (beta1) — per-vertex guarded wall-fit snap (staircase 제거).
# env AUTO_TESSELL_HEX_WALLFIT_OFF=1 to disable.
_WF_HEX_FACES = np.array(_HEX_FACES, dtype=np.int64)  # (6, 4) local-vertex face table


def _hex_array_to_cell_faces(hexes: np.ndarray) -> list[list[list[int]]]:
    """Convert an (N, 8) hex-connectivity array to the list-of-faces form."""
    faces_all = hexes[:, _WF_HEX_FACES]  # (N, 6, 4)
    return [[[int(v) for v in face] for face in cell] for cell in faces_all]


def _wall_fit_snap(
    pts: np.ndarray,
    cell_faces: list[list[list[int]]],
    V: np.ndarray,
    F: np.ndarray,
    target_edge: float,
    *,
    tol: float,
    ratio: float,
    iters: int,
    source_path: str | Path | None = None,
    source_feature_manifest: AuthoritativeSourceFeatureManifest | None = None,
) -> tuple[np.ndarray, dict[str, object]]:
    """Project boundary verts onto the input surface with a per-vertex guard.

    Motif: snappyHexMesh snap-step + fTetWild envelope. Each boundary vertex is
    projected to the closest point on the nearest input triangle and the move is
    accepted only when BOTH hold: (a) the vertex's surface distance strictly
    decreases (kills the blunt-cap non-monotonicity, card §이론), and (b) every
    incident cell keeps every face's centroid-signed orientation and a
    non-collapsed volume (no local tangle/inversion). Any violation reverts THAT
    vertex only (local, not the legacy global skew-revert).

    ``cell_faces`` is the generic polyMesh cell → face → vertex-id form so this
    works both for the octree/adaptive path (``oct_cells``) and the uniform-grid
    hex array (converted via :func:`_hex_array_to_cell_faces`).  The vertex only
    ever moves ONTO an input triangle inside the envelope
    ``|p - v| <= ratio * target_edge`` — surface coverage can only improve and
    off-surface void can never be created (solid invariants preserved).
    """
    from collections import defaultdict  # noqa: PLC0415

    from core.generator.native_hex.quality import (  # noqa: PLC0415
        _native_generic_cell_face_signs,
    )
    from core.generator.native_hex.snap import _closest_point_on_triangle  # noqa: PLC0415
    from core.utils.kdtree import NumpyKDTree  # noqa: PLC0415

    stats = {
        "n_target": 0,
        "n_snapped": 0,
        "n_snapped_partial": 0,
        "n_reject_vol": 0,
        "n_reject_dist": 0,
        "n_reject_envelope": 0,
        "n_reject_face_area": 0,
    }
    sF = np.asarray(F, dtype=np.int64)
    sV = np.asarray(V, dtype=np.float64)
    if len(cell_faces) == 0 or sF.shape[0] == 0:
        return np.asarray(pts, dtype=np.float64).copy(), stats

    pts = np.asarray(pts, dtype=np.float64).copy()
    original_pts = pts.copy()

    # boundary faces appear in exactly one cell; their verts are the surface.
    face_cells: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for ci, cell in enumerate(cell_faces):
        for face in cell:
            face_cells[tuple(sorted(int(v) for v in face))].append(ci)
    boundary_verts: set[int] = set()
    for key, owners in face_cells.items():
        if len(owners) == 1:
            boundary_verts.update(key)
    if not boundary_verts:
        return pts, stats

    # vertex -> incident cell set (boundary verts only).
    incident: dict[int, set[int]] = {v: set() for v in boundary_verts}
    for ci, cell in enumerate(cell_faces):
        for v in {int(x) for face in cell for x in face} & boundary_verts:
            incident[v].add(ci)

    # Local sizing: per boundary vertex, the max edge length among all faces of
    # its incident cells. Captures the coarse-octree-cell scale at level
    # transitions so fine quality's per-vertex envelope isn't clamped by the
    # global finest-cell target_edge (card HEX-WALLFIT-FINE).
    local_scale: dict[int, float] = {}
    for v, cells in incident.items():
        m = 0.0
        for ci in cells:
            for face in cell_faces[ci]:
                fv = [int(x) for x in face]
                n = len(fv)
                for i in range(n):
                    e = float(np.linalg.norm(pts[fv[i]] - pts[fv[(i + 1) % n]]))
                    if e > m:
                        m = e
        local_scale[v] = m

    tri_A = sV[sF[:, 0]]
    tri_B = sV[sF[:, 1]]
    tri_C = sV[sF[:, 2]]
    tri_cen = (tri_A + tri_B + tri_C) / 3.0
    tree = NumpyKDTree(tri_cen)
    k = min(8, tri_cen.shape[0])
    cap_floor = float(ratio * target_edge)
    eps = max(1e-15, 1e-6 * target_edge**3)
    face_area_guard_enabled = os.environ.get(
        "AUTO_TESSELL_HEX_WALLFIT_FACE_AREA_GUARD", ""
    ).strip().lower() in {"1", "true", "yes"}
    face_area_eps = max((float(target_edge) * 1.0e-12) ** 2, 1.0e-30)
    candidate_quality_audit = None
    candidate_source_provenance = None
    if os.environ.get("AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        from core.generator.native_hex.wallfit_quality import (  # noqa: PLC0415, I001
            CandidateQualityAudit,
            snapshot as _candidate_quality_snapshot,
            source_candidate_provenance_context,
        )

        candidate_quality_audit = CandidateQualityAudit()
        candidate_source_provenance = source_candidate_provenance_context(
            sV,
            sF,
            source_path=source_path,
            manifest=source_feature_manifest,
        )

    def _cell_signs(ci: int) -> tuple[np.ndarray, float]:
        """Per-face centroid-signed tet-sum + total |vol| of cell *ci*."""
        cell = cell_faces[ci]
        native_signs = _native_generic_cell_face_signs(pts, cell)
        if native_signs is not None:
            return native_signs
        verts = sorted({int(v) for face in cell for v in face})
        c = pts[np.asarray(verts, dtype=np.int64)].mean(axis=0)
        sgn = np.empty(len(cell))
        mag = 0.0
        for fi, face in enumerate(cell):
            p = pts[np.asarray([int(v) for v in face], dtype=np.int64)] - c
            s = 0.0
            for i in range(1, len(face) - 1):
                s += float(np.dot(p[0], np.cross(p[i], p[i + 1])))
            sgn[fi] = s
            mag += abs(s)
        return sgn, mag

    # Reference face signs per incident cell — local no-inversion guard.
    ref: dict[int, np.ndarray] = {}
    for cells in incident.values():
        for ci in cells:
            if ci not in ref:
                ref[ci] = np.sign(_cell_signs(ci)[0])

    def _cell_ok(ci: int) -> bool:
        sgn, mag = _cell_signs(ci)
        if mag <= eps:
            return False
        if face_area_guard_enabled:
            for face in cell_faces[ci]:
                if len(face) < 3:
                    stats["n_reject_face_area"] += 1
                    return False
                anchor = pts[int(face[0])]
                face_area = 0.0
                for face_index in range(1, len(face) - 1):
                    face_area += 0.5 * float(
                        np.linalg.norm(
                            np.cross(
                                pts[int(face[face_index])] - anchor,
                                pts[int(face[face_index + 1])] - anchor,
                            )
                        )
                    )
                if face_area <= face_area_eps:
                    stats["n_reject_face_area"] += 1
                    return False
        r = ref[ci]
        # every face that had a definite orientation keeps it (no flip).
        return bool(np.all(np.sign(sgn)[r != 0.0] == r[r != 0.0]))

    def _project(P: np.ndarray, cand: np.ndarray) -> tuple[float, np.ndarray]:
        best_d2 = float("inf")
        best_pt = P
        for t in cand.tolist():
            q = _closest_point_on_triangle(P, tri_A[t], tri_B[t], tri_C[t])
            d2 = float(((q - P) ** 2).sum())
            if d2 < best_d2:
                best_d2 = d2
                best_pt = q
        return best_d2, best_pt

    boundary = np.array(sorted(boundary_verts), dtype=np.int64)
    for _ in range(int(iters)):
        _, nn = tree.query(pts[boundary], k=k)
        nn = np.atleast_2d(np.asarray(nn))
        entries: list[tuple[float, np.ndarray, np.ndarray, int]] = []
        for bi, vi in enumerate(boundary.tolist()):
            cand = nn[bi]
            cand = cand[cand < tri_cen.shape[0]]
            if cand.size == 0:
                continue
            d2_0, p0 = _project(pts[vi], cand)
            entries.append((d2_0, p0, cand, vi))
        entries.sort(key=lambda e: -e[0])  # worst deviation first
        moved = 0
        for d2_0, p0, cand, vi in entries:
            d0 = d2_0**0.5
            if d0 <= tol:
                continue
            stats["n_target"] += 1
            cap_v = max(cap_floor, ratio * local_scale.get(vi, target_edge))
            if float(np.linalg.norm(p0 - pts[vi])) > cap_v:
                stats["n_reject_envelope"] += 1
                continue  # outside envelope
            provenance = (
                candidate_source_provenance.classify_projection_target(p0)
                if candidate_source_provenance is not None
                else None
            )
            orig = pts[vi].copy()
            candidate_before = (
                _candidate_quality_snapshot(pts, cell_faces, incident[vi])
                if candidate_quality_audit is not None
                else None
            )
            pts[vi] = p0
            candidate_trial = (
                _candidate_quality_snapshot(pts, cell_faces, incident[vi])
                if candidate_quality_audit is not None
                else None
            )
            d1 = _project(pts[vi], cand)[0] ** 0.5  # ~0 (p0 is on a triangle)
            if not (d1 < d0 - 1e-15):
                pts[vi] = orig
                stats["n_reject_dist"] += 1
                if candidate_quality_audit is not None:
                    assert candidate_before is not None and candidate_trial is not None
                    candidate_quality_audit.record(
                        vertex=vi,
                        outcome="rejected",
                        before=candidate_before,
                        trial=candidate_trial,
                        after=candidate_before,
                        distance_before=d0,
                        distance_after=d0,
                        source_provenance=provenance,
                    )
                continue
            if all(_cell_ok(ci) for ci in incident[vi]):
                stats["n_snapped"] += 1
                moved += 1
                if candidate_quality_audit is not None:
                    assert candidate_before is not None and candidate_trial is not None
                    candidate_quality_audit.record(
                        vertex=vi,
                        outcome="full",
                        before=candidate_before,
                        trial=candidate_trial,
                        after=candidate_trial,
                        distance_before=d0,
                        distance_after=d1,
                        source_provenance=provenance,
                    )
            else:
                # Full projection flips a face — backtrack to the largest
                # fraction t of orig->p0 that still passes the same guard
                # (card HEX-WALLFIT-BACKTRACK), instead of reverting outright.
                lo, hi = 0.0, 1.0
                for _ in range(12):
                    mid = (lo + hi) / 2.0
                    pts[vi] = orig + mid * (p0 - orig)
                    if all(_cell_ok(ci) for ci in incident[vi]):
                        lo = mid
                    else:
                        hi = mid
                d_partial = (
                    _project(orig + lo * (p0 - orig), cand)[0] ** 0.5 if lo > 0.0 else d0
                )
                if lo > 0.0 and d_partial < d0 - 1e-15:
                    pts[vi] = orig + lo * (p0 - orig)
                    stats["n_snapped_partial"] += 1
                    moved += 1
                    if candidate_quality_audit is not None:
                        assert candidate_before is not None and candidate_trial is not None
                        candidate_after = _candidate_quality_snapshot(
                            pts, cell_faces, incident[vi]
                        )
                        candidate_quality_audit.record(
                            vertex=vi,
                            outcome="partial",
                            before=candidate_before,
                            trial=candidate_trial,
                            after=candidate_after,
                            distance_before=d0,
                            distance_after=d_partial,
                            source_provenance=provenance,
                        )
                else:
                    pts[vi] = orig
                    stats["n_reject_vol"] += 1
                    if candidate_quality_audit is not None:
                        assert candidate_before is not None and candidate_trial is not None
                        candidate_quality_audit.record(
                            vertex=vi,
                            outcome="rejected",
                            before=candidate_before,
                            trial=candidate_trial,
                            after=candidate_before,
                            distance_before=d0,
                            distance_after=d0,
                            source_provenance=provenance,
                        )
        if moved == 0:
            break  # cube early-exit: nothing to fit
    if candidate_quality_audit is not None:
        def _surface_distance_stats(query_points: np.ndarray) -> dict[str, object]:
            _, nearest = tree.query(query_points[boundary], k=k)
            nearest = np.atleast_2d(np.asarray(nearest))
            distances: list[float] = []
            for index, vertex in enumerate(boundary.tolist()):
                candidates = nearest[index]
                candidates = candidates[candidates < tri_cen.shape[0]]
                if candidates.size == 0:
                    continue
                distances.append(_project(query_points[vertex], candidates)[0] ** 0.5)
            if not distances:
                return {"n": 0, "mean": None, "p50": None, "p95": None, "maximum": None}
            values = np.asarray(distances, dtype=np.float64)
            return {
                "n": int(values.size),
                "mean": float(np.mean(values)),
                "p50": float(np.percentile(values, 50)),
                "p95": float(np.percentile(values, 95)),
                "maximum": float(np.max(values)),
            }

        before_surface_distance = _surface_distance_stats(original_pts)
        after_surface_distance = _surface_distance_stats(pts)
        candidate_report = candidate_quality_audit.to_dict()
        candidate_report["stage_surface_distance_before"] = before_surface_distance
        candidate_report["stage_surface_distance_after"] = after_surface_distance
        candidate_report["stage_surface_distance_max_delta"] = (
            float(after_surface_distance["maximum"])
            - float(before_surface_distance["maximum"])
            if before_surface_distance["maximum"] is not None
            and after_surface_distance["maximum"] is not None
            else None
        )
        candidate_report["stage_surface_distance_mean_delta"] = (
            float(after_surface_distance["mean"])
            - float(before_surface_distance["mean"])
            if before_surface_distance["mean"] is not None
            and after_surface_distance["mean"] is not None
            else None
        )
        stats["candidate_quality"] = candidate_report
        log.info(
            "native_hex_wall_fit_candidate_quality_summary",
            n_candidates=candidate_report["n_candidates"],
            n_full=candidate_report["n_full"],
            n_partial=candidate_report["n_partial"],
            n_rejected=candidate_report["n_rejected"],
            n_applied_distance_improved=candidate_report[
                "n_applied_distance_improved"
            ],
            n_distance_improved_quality_regression=candidate_report[
                "n_distance_improved_quality_regression"
            ],
            strict_quality_nonregressing=candidate_report[
                "strict_quality_nonregressing"
            ],
            p95_quality_nonregressing=candidate_report[
                "p95_quality_nonregressing"
            ],
            combined_quality_nonregressing=candidate_report[
                "combined_quality_nonregressing"
            ],
            source_provenance_authoritative=candidate_report[
                "n_source_provenance_authoritative"
            ],
            source_provenance_unavailable=candidate_report[
                "n_source_provenance_unavailable"
            ],
            source_provenance_ambiguous=candidate_report[
                "n_source_provenance_ambiguous"
            ],
            pareto_frontier_size=candidate_report["pareto_frontier_size"],
            boundary_key_changes=candidate_report["n_boundary_key_change"],
            boundary_area_changes=candidate_report["n_boundary_area_change"],
            max_abs_boundary_area_delta=candidate_report[
                "max_abs_boundary_area_delta"
            ],
            max_relative_boundary_area_delta=candidate_report[
                "max_relative_boundary_area_delta"
            ],
            max_applied_skew_delta=candidate_report["max_applied_skew_delta"],
            max_applied_warpage_delta=candidate_report[
                "max_applied_warpage_delta"
            ],
            stage_surface_distance_before=candidate_report[
                "stage_surface_distance_before"
            ],
            stage_surface_distance_after=candidate_report[
                "stage_surface_distance_after"
            ],
            stage_surface_distance_max_delta=candidate_report[
                "stage_surface_distance_max_delta"
            ],
            stage_surface_distance_mean_delta=candidate_report[
                "stage_surface_distance_mean_delta"
            ],
        )
    return pts, stats


def _relax_boundary_sliver_interior(
    pts: np.ndarray,
    cell_faces: "list[list[list[int]]]",
    tau: float = 0.5,
    alpha: float = 0.5,
    iters: int = 2,
) -> tuple[np.ndarray, dict[str, float]]:
    """post-``_wall_fit_snap`` boundary sliver 셀의 wall-normal 두께(|nd|) 복원.

    ``cell_faces`` 는 ``_wall_fit_snap`` 과 동일한 generic polyMesh cell->face->vert
    형식(옥트리 adaptive 경로의 hanging-node 면도 지원, uniform 경로는
    ``_hex_array_to_cell_faces`` 로 변환해 전달) — ``hex_quality_report``/
    ``_count_neg_vol_hex`` 는 (N,8) 전제라 옥트리 경로엔 못 쓰므로, 이 함수가 checker
    와 동일 정의의 boundary/internal skewness·non-orthogonality·부호반전 셀 수를
    자체 계산해 ``stats`` 로 반환한다 (호출부 smart-guard 가 최종 mesh 값으로
    accept/revert 판정).

    표면 정점(모든 boundary face 의 vertex)은 완전 동결 — wall_dev 재회귀 절대
    금지, 최우선 가드. ``|nd| < tau*h`` 인 sliver 셀의 자유(non-boundary) 정점만
    face-normal 반대 방향(안쪽)으로 ``alpha*(target-|nd|)`` 만큼 directed relax.
    """
    from collections import defaultdict  # noqa: PLC0415

    from core.generator.native_hex.quality import (  # noqa: PLC0415
        _native_generic_side_metrics,
    )

    stats: dict[str, float] = dict.fromkeys(
        (
            "sliver_cells",
            "moved_verts",
            "pre_bskew",
            "post_bskew",
            "pre_int_skew",
            "post_int_skew",
            "pre_no",
            "post_no",
            "pre_neg_vol",
            "post_neg_vol",
        ),
        0.0,
    )
    pts = np.asarray(pts, dtype=np.float64).copy()
    if not cell_faces:
        return pts, stats
    owners: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for ci, cell in enumerate(cell_faces):
        for face in cell:
            owners[tuple(sorted(int(v) for v in face))].append(ci)
    boundary_faces: list[tuple[int, list[int]]] = []
    internal_faces: list[tuple[int, int, list[int]]] = []
    boundary_verts: set[int] = set()
    seen: set[tuple[int, ...]] = set()
    for ci, cell in enumerate(cell_faces):
        for face in cell:
            fv = [int(v) for v in face]
            key = tuple(sorted(fv))
            o = owners[key]
            if len(o) == 1:
                boundary_faces.append((ci, fv))
                boundary_verts.update(fv)
            elif len(o) == 2 and key not in seen:
                seen.add(key)
                internal_faces.append((o[0], o[1], fv))
    if not boundary_faces:
        return pts, stats
    cell_verts = [sorted({int(v) for face in cell for v in face}) for cell in cell_faces]

    def _cc(ci: int, cur: np.ndarray) -> np.ndarray:
        return cur[np.asarray(cell_verts[ci], dtype=np.int64)].mean(axis=0)

    def _face_geom(fv: list[int], cur: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        p = cur[np.asarray(fv, dtype=np.int64)]
        fc = p.mean(axis=0)
        nvec = np.zeros(3)
        n = len(fv)
        for i in range(n):  # Newell's method — arbitrary (incl. non-quad) polygon
            a, b = p[i], p[(i + 1) % n]
            nvec[0] += (a[1] - b[1]) * (a[2] + b[2])
            nvec[1] += (a[2] - b[2]) * (a[0] + b[0])
            nvec[2] += (a[0] - b[0]) * (a[1] + b[1])
        nmag = float(np.linalg.norm(nvec))
        return fc, (nvec / nmag if nmag > 1e-30 else nvec)

    def _signed_vol(ci: int, cur: np.ndarray) -> float:
        c = _cc(ci, cur)
        total = 0.0
        for face in cell_faces[ci]:
            p = cur[np.asarray(face, dtype=np.int64)]
            for i in range(1, len(face) - 1):
                total += float(np.dot(p[0] - c, np.cross(p[i] - c, p[i + 1] - c))) / 6.0
        return total

    areas = []
    for _, fv in boundary_faces:
        p = pts[np.asarray(fv, dtype=np.int64)]
        c = p.mean(axis=0)
        n = len(fv)
        a = sum(
            float(np.linalg.norm(np.cross(p[i] - c, p[(i + 1) % n] - c))) / 2.0 for i in range(n)
        )
        areas.append(a)
    h_est = float(np.sqrt(np.median(np.asarray(areas)))) if areas else 0.0
    if h_est <= 1e-12:
        return pts, stats
    target, thresh = 0.5 * h_est, tau * h_est

    def _scan(
        cur: np.ndarray, relax: bool
    ) -> tuple[float, dict[int, np.ndarray], dict[int, int], int]:
        max_bs, acc, wt, nsliv = 0.0, {}, {}, 0
        for ci, fv in boundary_faces:
            cc = _cc(ci, cur)
            fc, nhat = _face_geom(fv, cur)
            if not np.any(nhat):
                continue
            nd = float(np.dot(fc - cc, nhat))
            tmiss = float(np.linalg.norm((fc - cc) - nd * nhat))
            bs = tmiss / max(abs(nd), 1e-12)
            max_bs = max(max_bs, bs)
            if relax and abs(nd) < thresh:
                free = [v for v in cell_verts[ci] if v not in boundary_verts]
                if not free:
                    continue
                nsliv += 1
                step = alpha * max(target - abs(nd), 0.0)
                disp = -step * nhat if nd >= 0 else step * nhat
                for v in free:
                    acc[v] = acc.get(v, np.zeros(3)) + disp
                    wt[v] = wt.get(v, 0) + 1
        return max_bs, acc, wt, nsliv

    def _side_metrics(cur: np.ndarray) -> tuple[float, float, float]:
        native_metrics = _native_generic_side_metrics(cur, cell_faces)
        if native_metrics is not None:
            return native_metrics
        max_sk, max_no = 0.0, 0.0
        for ci0, ci1, fv in internal_faces:
            cc0, cc1 = _cc(ci0, cur), _cc(ci1, cur)
            d = cc1 - cc0
            dmag = float(np.linalg.norm(d))
            if dmag < 1e-30:
                continue
            fc, nhat = _face_geom(fv, cur)
            t = float(np.dot(fc - cc0, d)) / (dmag**2)
            max_sk = max(max_sk, float(np.linalg.norm(fc - (cc0 + t * d))) / dmag)
            if np.any(nhat):
                cosang = min(1.0, max(0.0, abs(float(np.dot(nhat, d))) / dmag))
                max_no = max(max_no, float(np.degrees(np.arccos(cosang))))
        from core.generator.native_hex.quality import (  # noqa: PLC0415
            _native_generic_cell_volumes,
        )

        native_volumes = _native_generic_cell_volumes(cur, cell_faces)
        if native_volumes is None:
            neg = sum(
                1
                for ci in range(len(cell_faces))
                if _signed_vol(ci, cur) <= 0.0
            )
        else:
            neg = int(np.count_nonzero(native_volumes <= 0.0))
        return max_sk, max_no, float(neg)

    stats["pre_bskew"] = _scan(pts, relax=False)[0]
    stats["pre_int_skew"], stats["pre_no"], stats["pre_neg_vol"] = _side_metrics(pts)
    n_sliver, n_moved = 0, 0
    for _ in range(max(1, int(iters))):
        _, acc, wt, nsliv = _scan(pts, relax=True)
        if not acc:
            break
        for v, a in acc.items():
            pts[v] = pts[v] + a / wt[v]
        n_sliver, n_moved = nsliv, len(acc)
    stats["sliver_cells"], stats["moved_verts"] = float(n_sliver), float(n_moved)
    stats["post_bskew"] = _scan(pts, relax=False)[0]
    stats["post_int_skew"], stats["post_no"], stats["post_neg_vol"] = _side_metrics(pts)
    return pts, stats


def generate_native_hex(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    target_cells: int | None = None,
    max_cells: int | None = None,
    bl_layers: int | None = None,
    post_layers_num_layers: int | None = None,
    seed_density: int = 16,
    snap_boundary: bool = False,
    max_cells_per_axis: int = 50,
    preserve_features: bool = False,
    feature_angle_deg: float = 45.0,
    adaptive: bool = False,
    n_levels: int = 2,
    refinement_distance_factor: float = 2.0,
    snap_iterations: int = 0,
    # X3 (beta1840) — snap 후 boundary vertex Laplacian smooth.
    enable_post_smooth: bool = False,
    post_smooth_iterations: int = 2,
    post_smooth_relax: float = 0.3,
    # P2.4 / beta2313 — snappy nBufferCellsNoExtrude 동등 buffer layer.
    # 0=비활성, 1=1-cell 두께 buffer (default), 2+=더 두꺼운 buffer.
    # _add_buffer_layer_between_levels (octree.py) 가 직접 사용.
    # 이 인자는 HARNESS_PARAMS / GUI spec / CLI 도달용 — 실제 octree
    # 호출은 환경변수 AUTO_TESSELL_HEX_BUFFER_LAYER 를 검사하므로 여기서
    # 환경변수 임시 설정하는 단발 wiring.
    hex_buffer_cells: int = 1,
    **_unused: object,
) -> NativeHexResult:
    # C-PERF-3 / beta2388 — wall-clock soft budget 진단.
    # validator 발견: hard mesh #1 (V=3116) 의 fine hex 가 627s.
    # AUTO_TESSELL_HEX_BUDGET_S env 로 budget 설정 → 초과 시 warn 로그
    # (실제 cancel 은 아직 없음 — 후속 카드에서 graceful early-exit 추가).
    # 현재는 측정만 — bench 결과 분석에 활용.
    import os as _os_hex_budget

    _hex_budget_log_threshold = float(
        _os_hex_budget.environ.get("AUTO_TESSELL_HEX_BUDGET_LOG_S", "120"),
    )
    _hex_t_start = __import__("time").perf_counter()
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
    V, F, input_error = _prepare_native_hex_surface_input(vertices, faces)
    if input_error == "empty_mesh":
        return NativeHexResult(False, 0.0, message="빈 입력 mesh")
    if input_error is not None:
        return NativeHexResult(False, 0.0, message=f"native_hex_invalid_input:{input_error}")

    assert V is not None and F is not None

    # beta2338 — pre-mesh self-intersect capture (P2.6 chain).
    # ≤5000 face 만 측정 (KDTree 비용 회피). result.n_self_intersect_pre 에
    # 저장되어 harness / bench / GUI 에서 활용 가능.
    _pre_mesh_si_count: int | None = None
    try:
        if int(F.shape[0]) <= 5000:
            from core.preprocessor.native_repair.self_intersect import (
                detect_self_intersections as _det_si_hex,
            )

            _r_si = _det_si_hex(V, F)
            _pre_mesh_si_count = int(_r_si.n_intersections)
            if _r_si.has_self_intersection:
                log.warning(
                    "native_hex_pre_mesh_self_intersect",
                    n_intersections=_pre_mesh_si_count,
                    n_faces=int(F.shape[0]),
                )
    except Exception as _exc_si:
        log.debug("native_hex_si_diag_skipped", reason=str(_exc_si)[:120])

    # PRE3 (beta2149) — input CVT isotropic remesh on high edge-length-ratio.
    # Botsch & Kobbelt 2004 isotropic remesh — gated by edge_length_ratio > 100
    # or n_faces > 200 000. Default ON; set AUTO_TESSELL_PRE3_HEX_OFF=1 to disable.
    import os as _os_hex

    if not _os_hex.environ.get("AUTO_TESSELL_PRE3_HEX_OFF") and F.shape[0] >= 100:
        try:
            _pre3_edges = np.concatenate(
                [
                    V[F[:, 0]] - V[F[:, 1]],
                    V[F[:, 1]] - V[F[:, 2]],
                    V[F[:, 2]] - V[F[:, 0]],
                ],
                axis=0,
            )
            _pre3_lens = np.linalg.norm(_pre3_edges, axis=1)
            _pre3_lens = _pre3_lens[_pre3_lens > 0]
            _pre3_ratio = float(_pre3_lens.max() / _pre3_lens.min()) if len(_pre3_lens) > 0 else 0.0
            _pre3_nf = int(F.shape[0])
            if _pre3_ratio > 100.0 or _pre3_nf > 200_000:
                from core.preprocessor.native_remesh import isotropic_remesh

                _pre3_bmin = V.min(axis=0)
                _pre3_bmax = V.max(axis=0)
                _pre3_diag = float(np.linalg.norm(_pre3_bmax - _pre3_bmin))
                _pre3_target = _pre3_diag / 100.0
                V_pre3, F_pre3 = isotropic_remesh(V, F, target_edge_length=_pre3_target)
                if F_pre3.shape[0] > _pre3_nf * 2:
                    log.debug(
                        "native_hex_pre3_remesh_skipped_facecount",
                        faces_before=_pre3_nf,
                        faces_after=int(F_pre3.shape[0]),
                    )
                else:
                    V = V_pre3.astype(np.float64)
                    F = F_pre3.astype(np.int64)
                    log.info(
                        "native_hex_pre3_remesh",
                        edge_length_ratio=round(_pre3_ratio, 2),
                        faces_before=_pre3_nf,
                        faces_after=int(F.shape[0]),
                        target_edge_length=round(_pre3_target, 6),
                    )
        except Exception as _pre3_exc:
            log.warning("pre3_hex_remesh_failed", reason=str(_pre3_exc))

    bmin_pre = V.min(axis=0)
    bmax_pre = V.max(axis=0)
    diag_pre = float(np.linalg.norm(bmax_pre - bmin_pre))

    # BETA2820: small-bbox pre-flight seed_density bump (proactive, before grid build).
    # diag_pre < THRESH 이고 target_edge_length user-set 이 아니면 seed_density 를 pre-bump.
    _sbp_on = os.environ.get("AUTO_TESSELL_HEX_SMALL_BBOX_PREFLIGHT", "1") != "0"
    _te_user_set_pre = target_edge_length is not None and float(target_edge_length) > 0
    if _sbp_on and not _te_user_set_pre:
        _THRESH = float(os.environ.get("AUTO_TESSELL_HEX_SMALL_BBOX_THRESH", "1.0"))
        if 1e-9 < diag_pre < _THRESH:
            _sd_orig = int(seed_density)
            _factor = (_THRESH / diag_pre) ** 0.5
            _eff_sd = max(_sd_orig, int(np.ceil(seed_density * _factor)))
            seed_density = min(_eff_sd, _sd_orig * 8)
            log.info(
                "native_hex_small_bbox_preflight",
                diag=round(diag_pre, 6),
                seed_density_orig=_sd_orig,
                seed_density_eff=int(seed_density),
            )

    _cell_budget = int(max_cells or target_cells or 0)
    _budget_layers = int(post_layers_num_layers or bl_layers or 0)
    _volume_budget = _cell_budget
    if _cell_budget > 0 and _budget_layers > 0:
        # cfMesh-style BL budgeting: BL cells scale with boundary area (O(n^2)),
        # not volume cells (O(n^3)). The old 3.5/layer divisor over-reserved for
        # BL and made simple BL3 cubes land below the 0.5*target lower gate.
        _bl_budget_per_layer = float(os.environ.get("AUTO_TESSELL_HEX_BL_BUDGET_PER_LAYER", "1.2"))
        _volume_budget = max(
            1,
            int(float(_cell_budget) / (1.0 + _bl_budget_per_layer * float(_budget_layers))),
        )
    h_pre = (
        float(target_edge_length)
        if (target_edge_length is not None and target_edge_length > 0)
        else diag_pre / max(1, int(seed_density))
    )
    if _cell_budget > 0 and h_pre > 0.0:
        ext_pre = np.maximum(bmax_pre - bmin_pre, 1e-12)
        refine_factor = 1 << max(0, int(n_levels) if adaptive else 0)
        h_est = h_pre / float(refine_factor)
        est_cells_pre = int(np.prod(np.maximum(np.ceil(ext_pre / h_est), 1)))
        if est_cells_pre > _volume_budget:
            h_budget = float(
                (float(np.prod(ext_pre)) * float(refine_factor**3) / float(_volume_budget))
                ** (1.0 / 3.0)
            )
            if h_budget > h_pre:
                log.info(
                    "native_hex_budget_edge_enlarged",
                    target_cells=int(target_cells or 0),
                    max_cells=int(max_cells or 0),
                    est_cells=est_cells_pre,
                    volume_budget=int(_volume_budget),
                    budget_layers=int(_budget_layers),
                    refinement_factor=int(refine_factor),
                    edge_old=round(float(h_pre), 8),
                    edge_new=round(float(h_budget), 8),
                )
                h_pre = h_budget
                target_edge_length = h_budget

    # beta91: adaptive octree refinement (2-level, surface near → fine, interior → coarse)
    if adaptive:
        try:
            from core.generator.native_hex.octree import build_octree_hex_cells  # noqa: PLC0415

            # P2.4 / beta2313 — hex_buffer_cells kwarg → env var 로 octree 에 전달.
            import os as _os_hbc

            _prev_buf = _os_hbc.environ.get("AUTO_TESSELL_HEX_BUFFER_LAYER")
            _os_hbc.environ["AUTO_TESSELL_HEX_BUFFER_LAYER"] = str(int(hex_buffer_cells))
            try:
                oct_pts, oct_cells, oct_stats = build_octree_hex_cells(
                    V,
                    F,
                    bmin_pre,
                    bmax_pre,
                    h_pre,
                    max_cells_per_axis=max_cells_per_axis,
                    n_levels=n_levels,
                    refinement_distance_factor=refinement_distance_factor,
                )
                _rebudget_on = (
                    os.environ.get("AUTO_TESSELL_HEX_FINAL_REBUDGET", "1") != "0"
                    and _cell_budget > 0
                    and _budget_layers > 0
                    and len(oct_cells) > 0
                )
                if _rebudget_on:
                    _low_ratio = float(os.environ.get("AUTO_TESSELL_HEX_FINAL_LOW_RATIO", "0.5"))
                    _high_ratio = float(os.environ.get("AUTO_TESSELL_HEX_FINAL_HIGH_RATIO", "2.0"))
                    _target_low = max(1, int(round(float(_cell_budget) * _low_ratio)))
                    _target_high = max(
                        _target_low,
                        int(round(float(_cell_budget) * _high_ratio)),
                    )
                    _passes = max(
                        0,
                        int(os.environ.get("AUTO_TESSELL_HEX_FINAL_REBUDGET_PASSES", "2")),
                    )
                    _exp = max(
                        1.0,
                        float(os.environ.get("AUTO_TESSELL_HEX_FINAL_REBUDGET_EXP", "2.35")),
                    )
                    for _rb_pass in range(_passes):
                        (
                            _base_n,
                            _bnd_n,
                            _bnd_facets_n,
                            _est_final,
                        ) = _estimate_bl_final_cells_from_cell_faces(
                            oct_cells,
                            n_layers=int(_budget_layers),
                        )
                        if _target_low <= _est_final <= _target_high:
                            break
                        if _est_final > _target_high:
                            _target_final = max(
                                1.0,
                                float(_target_high) * 0.9,
                            )
                            _factor = (float(_est_final) / _target_final) ** (1.0 / _exp)
                            _factor = min(max(_factor, 1.03), 1.85)
                        else:
                            _target_final = max(
                                1.0,
                                float(_target_low) * 1.1,
                            )
                            _factor = (float(max(_est_final, 1)) / _target_final) ** (1.0 / _exp)
                            _factor = max(min(_factor, 0.97), 0.55)
                        _h_next = float(h_pre) * float(_factor)
                        if not np.isfinite(_h_next) or _h_next <= 0:
                            break
                        if abs(_h_next / max(float(h_pre), 1e-30) - 1.0) < 0.02:
                            break
                        log.info(
                            "native_hex_final_rebudget",
                            pass_index=int(_rb_pass + 1),
                            base_cells=int(_base_n),
                            boundary_faces=int(_bnd_n),
                            boundary_facets=int(_bnd_facets_n),
                            estimated_final_cells=int(_est_final),
                            target_low=int(_target_low),
                            target_high=int(_target_high),
                            budget_layers=int(_budget_layers),
                            edge_old=round(float(h_pre), 8),
                            edge_new=round(float(_h_next), 8),
                        )
                        h_pre = float(_h_next)
                        target_edge_length = float(_h_next)
                        oct_pts, oct_cells, oct_stats = build_octree_hex_cells(
                            V,
                            F,
                            bmin_pre,
                            bmax_pre,
                            h_pre,
                            max_cells_per_axis=max_cells_per_axis,
                            n_levels=n_levels,
                            refinement_distance_factor=refinement_distance_factor,
                        )
                    (
                        _base_n,
                        _bnd_n,
                        _bnd_facets_n,
                        _est_final,
                    ) = _estimate_bl_final_cells_from_cell_faces(
                        oct_cells,
                        n_layers=int(_budget_layers),
                    )
                    log.info(
                        "native_hex_final_rebudget_done",
                        base_cells=int(_base_n),
                        boundary_faces=int(_bnd_n),
                        boundary_facets=int(_bnd_facets_n),
                        estimated_final_cells=int(_est_final),
                        target_low=int(_target_low),
                        target_high=int(_target_high),
                    )
            finally:
                # 환경변수 복원 — 외부 caller 영향 0.
                if _prev_buf is None:
                    _os_hbc.environ.pop("AUTO_TESSELL_HEX_BUFFER_LAYER", None)
                else:
                    _os_hbc.environ["AUTO_TESSELL_HEX_BUFFER_LAYER"] = _prev_buf
            if oct_cells:
                _transition_diag_enabled = os.environ.get(
                    "AUTO_TESSELL_HEX_TRANSITION_PROVENANCE_DIAG", ""
                ).strip().lower() in ("1", "true", "yes")
                if _transition_diag_enabled:
                    _transition_summary = oct_stats.get("transition_provenance", {})
                    log.info(
                        "native_hex_transition_provenance_before_writer",
                        path="octree",
                        **_transition_summary,
                    )
                _transition_quality_enabled = os.environ.get(
                    "AUTO_TESSELL_HEX_TRANSITION_QUALITY_DIAG", ""
                ).strip().lower() in ("1", "true", "yes")
                _transition_quality_metadata = oct_stats.get(
                    "_transition_quality_metadata", []
                )
                _log_transition_quality_stage = None
                if _transition_quality_enabled:
                    from core.generator.native_hex.transition_quality import (  # noqa: PLC0415
                        audit_transition_quality,
                    )

                    def _log_transition_quality_stage(
                        _stage_name: str, _stage_points: np.ndarray
                    ) -> None:
                        _quality_report = audit_transition_quality(
                            np.asarray(_stage_points, dtype=np.float64),
                            oct_cells,
                            cell_metadata=_transition_quality_metadata,
                        )
                        log.info(
                            "native_hex_transition_quality_stage",
                            path="octree",
                            stage=_stage_name,
                            **_quality_report.to_dict(),
                        )

                    _log_transition_quality_stage("before_snap", oct_pts)
                # beta94: iterative snap step (adaptive 경로)
                if snap_iterations > 0:
                    try:
                        from core.generator.native_hex.snap import (  # noqa: PLC0415
                            snap_to_surface_iterative,
                        )

                        h_snap = h_pre / float(1 << max(0, int(n_levels)))
                        oct_pts, snap_stats_it = snap_to_surface_iterative(
                            oct_pts,
                            V,
                            F,
                            h_snap,
                            n_iter=snap_iterations,
                            relax=0.5,
                        )
                        log.info(
                            "native_hex_iterative_snap_applied",
                            n_iter=snap_iterations,
                            **{k: v for k, v in snap_stats_it.items() if k != "n_snapped_per_iter"},
                        )
                    except Exception as exc:
                        log.warning("native_hex_iterative_snap_failed", error=str(exc))
                if _log_transition_quality_stage is not None:
                    _log_transition_quality_stage("after_iterative_snap", oct_pts)

                # BETA_HEX_WALLFIT (beta1) — per-vertex guarded wall-fit on the
                # adaptive/octree mesh (the standard/fine path). Runs after the
                # iterative snap, projects side-wall verts onto the input surface
                # with a per-vertex strict-decrease + no-inversion guard. Cube
                # early-exits (verts already on planes). env
                # AUTO_TESSELL_HEX_WALLFIT_OFF=1 disables.
                if snap_boundary and not os.environ.get("AUTO_TESSELL_HEX_WALLFIT_OFF"):
                    try:
                        _h_wf = h_pre / float(1 << max(0, int(n_levels)))
                        oct_pts, _wf_stats = _wall_fit_snap(
                            np.asarray(oct_pts, dtype=np.float64),
                            oct_cells,
                            V,
                            F,
                            _h_wf,
                            tol=0.1 * _h_wf,
                            ratio=1.0,
                            iters=3,
                        )
                        log.info("native_hex_wall_fit", path="octree", **_wf_stats)
                        if _log_transition_quality_stage is not None:
                            _log_transition_quality_stage("after_wall_fit", oct_pts)

                        # HEX-SKEW-INNER-RELAX (beta_hex4) — post-wall-fit boundary
                        # sliver (|nd| collapsed by the snap) 두께 복원. 표면 정점
                        # frozen ⇒ wall_dev 불변. 전량 accept/revert (Klingner
                        # smart) — 최종 mesh 실측 기준(octree hanging-node 면 포함,
                        # generic cell_faces 경로이므로 hex_quality_report 대신 자체
                        # 계산한 stats 사용).
                        if not os.environ.get("AUTO_TESSELL_HEX_SKEW_RELAX_OFF"):
                            _rlx_pts, _rlx_stats = _relax_boundary_sliver_interior(
                                oct_pts, oct_cells
                            )
                            _eps = 1e-9
                            _accept = (
                                _rlx_stats["post_bskew"] < _rlx_stats["pre_bskew"] - _eps
                                and _rlx_stats["post_int_skew"]
                                <= _rlx_stats["pre_int_skew"] + _eps
                                and _rlx_stats["post_no"] <= _rlx_stats["pre_no"] + _eps
                                and _rlx_stats["post_neg_vol"] == 0.0
                            )
                            if _accept:
                                oct_pts = _rlx_pts
                                log.info("native_hex_skew_relax_applied", path="octree", **_rlx_stats)
                            else:
                                log.info(
                                    "native_hex_skew_relax_revert", path="octree", **_rlx_stats
                                )
                    except Exception as exc:
                        log.warning("native_hex_wall_fit_failed", error=str(exc))
                if _log_transition_quality_stage is not None:
                    _log_transition_quality_stage(
                        "after_wall_fit_and_skew_relax", oct_pts
                    )

                # HEX-MATCH-2 (2026-07-26) — Staten-2010/Ledoux-2010 local pillow
                # insertion on boundary quads our own OpenFOAM skew formula flags,
                # behind a hard quality gate with per-candidate reject-and-rollback
                # and a whole-pass grade rollback (see match_repair.py). Inserts
                # interior cells only; no boundary vertex is ever repositioned.
                # Default OFF — env AUTO_TESSELL_HEX_MATCH2=1 enables — matching
                # the not-yet-broadly-verified mesh-editing precedent the tet track
                # set for FSL Wave 1 / TET-FLOW-2. Wired here, on the octree path's
                # generic cell-face output, because that is the path the fine
                # quality level takes and is pre-BL by construction (the BL pass
                # re-triangulates the wall and would hide these quads).
                if os.environ.get("AUTO_TESSELL_HEX_MATCH2", "").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    try:
                        from core.generator.native_hex.match_repair import (  # noqa: PLC0415
                            run_match_repair,
                        )

                        _m2_pts, _m2_cells, _m2_report = run_match_repair(
                            "octree", np.asarray(oct_pts, dtype=np.float64), oct_cells
                        )
                        if _m2_report.n_committed > 0 and not _m2_report.pass_rolled_back:
                            oct_pts, oct_cells = _m2_pts, _m2_cells
                    except Exception as exc:
                        log.warning("native_hex_match2_failed", error=str(exc))

                from core.generator.polymesh_writer import write_generic_polymesh  # noqa: PLC0415
                from core.generator.tier_layers_post import (  # noqa: PLC0415
                    _ensure_minimal_controldict,
                    _write_minimal_fv_dicts,
                )

                _ensure_minimal_controldict(case_dir)
                _write_minimal_fv_dicts(case_dir)
                stats = write_generic_polymesh(oct_pts, oct_cells, case_dir)
                n_t = int(stats["num_cells"])
                if _transition_quality_enabled:
                    from core.generator.native_hex.metrics import (  # noqa: PLC0415
                        read_written_polymesh_cells,
                    )
                    from core.generator.native_hex.transition_quality import (  # noqa: PLC0415
                        audit_transition_quality,
                    )

                    _written = read_written_polymesh_cells(case_dir)
                    if _written is None:
                        log.warning(
                            "native_hex_transition_quality_writer_unavailable",
                            path="octree",
                        )
                    else:
                        _written_pts, _written_cells = _written
                        _writer_quality_report = audit_transition_quality(
                            np.asarray(oct_pts, dtype=np.float64),
                            oct_cells,
                            cell_metadata=_transition_quality_metadata,
                            writer_points=np.asarray(_written_pts, dtype=np.float64),
                            writer_cell_faces=_written_cells,
                        )
                        log.info(
                            "native_hex_transition_quality_writer",
                            path="octree",
                            **_writer_quality_report.to_dict(),
                        )
                if _transition_diag_enabled:
                    log.info(
                        "native_hex_transition_provenance_writer_boundary",
                        path="octree",
                        builder_cell_metadata=int(
                            _transition_summary.get("n_cell_metadata", 0)
                        ),
                        written_cells=n_t,
                        writer_metadata_forwarded=False,
                        loss_stage="generic_polymesh_writer_boundary",
                    )
                _phase0_fields = _native_hex_phase0_metrics(
                    case_dir,
                    np.asarray(oct_pts, dtype=np.float64),
                    oct_cells,
                    path="octree",
                    n_written=n_t,
                )
                fill = n_t / max(
                    1,
                    oct_stats["n_coarse"]
                    + oct_stats["n_fine"]
                    + (
                        oct_stats["fine_grid"][0]
                        * oct_stats["fine_grid"][1]
                        * oct_stats["fine_grid"][2]
                        - oct_stats["n_fine"]
                    ),
                )
                return NativeHexResult(
                    success=True,
                    elapsed=time.perf_counter() - t0,
                    n_cells=n_t,
                    n_points=int(stats["num_points"]),
                    n_faces=int(stats["num_faces"]),
                    fill_ratio=float(oct_stats["n_total"])
                    / max(
                        1,
                        oct_stats["fine_grid"][0]
                        * oct_stats["fine_grid"][1]
                        * oct_stats["fine_grid"][2],
                    ),
                    grid_shape=tuple(oct_stats["grid_shape"]),
                    n_grid_total=oct_stats["n_coarse"] + oct_stats["n_fine"],
                    message=(
                        f"native_hex octree OK — cells={n_t} "
                        f"(coarse={oct_stats['n_coarse']}, fine={oct_stats['n_fine']})"
                    ),
                    # beta2341 — octree path 도 SI populate (uniform path 와 일관).
                    n_self_intersect_pre=_pre_mesh_si_count,
                    **_phase0_fields,
                )
            log.warning("native_hex_octree_empty_fallback", msg="no cells produced, falling back")
        except Exception as exc:
            log.warning("native_hex_octree_failed", error=str(exc), fallback="uniform grid")

    bmin = V.min(axis=0)
    bmax = V.max(axis=0)
    diag = float(np.linalg.norm(bmax - bmin))
    # P1 (beta2232): target_edge_length 가 사용자 명시인지 플래그 저장.
    _p1_te_user_set = target_edge_length is not None and float(target_edge_length) > 0
    if target_edge_length is None or target_edge_length <= 0:
        target_edge_length = diag / max(1, int(seed_density))
    h = float(target_edge_length)

    # 각 축별 grid size — max_cells_per_axis 로 제한 (과도한 셀 방지)
    cap = max(1, int(max_cells_per_axis))
    if not _te_user_set_pre and _volume_budget > 0:
        # ``target_cells`` is a user-facing count request, not merely an
        # upper-bound hint.  The old uniform path only enlarged ``h`` when a
        # seed-density grid exceeded the budget; a larger requested count
        # could therefore leave the mesh unchanged.  Choose the nearest
        # aspect-ratio-preserving integer lattice instead.  This is deliberately
        # limited to the implicit-edge path: an explicit edge length remains an
        # exact caller override, and ``max_cells_per_axis`` remains a hard cap.
        extent = np.maximum(bmax - bmin, 1.0e-12)
        lattice_scale = (float(_volume_budget) / float(np.prod(extent))) ** (1.0 / 3.0)
        nxyz_req = np.maximum(np.rint(extent * lattice_scale).astype(int), 1)
        nxyz = np.minimum(nxyz_req, cap)
        h = float(np.max(extent / nxyz))
        log.info(
            "native_hex_target_lattice",
            target_cells=int(target_cells or 0),
            max_cells=int(max_cells or 0),
            volume_budget=int(_volume_budget),
            requested=nxyz_req.tolist(),
            selected=nxyz.tolist(),
            target_edge=round(h, 8),
        )
    else:
        nxyz_req = np.maximum(
            np.ceil((bmax - bmin) / h).astype(int),
            1,
        )
        nxyz = np.minimum(nxyz_req, cap)
    if np.any(nxyz_req > cap):
        log.warning(
            "native_hex_grid_capped",
            requested=nxyz_req.tolist(),
            capped=nxyz.tolist(),
            cap=cap,
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

    # Vectorized hex cell vertex index construction (OpenFOAM order)
    ny1 = ny + 1
    nz1 = nz + 1
    _ia = np.arange(nx, dtype=np.int64)
    _ja = np.arange(ny, dtype=np.int64)
    _ka = np.arange(nz, dtype=np.int64)
    _CI, _CJ, _CK = np.meshgrid(_ia, _ja, _ka, indexing="ij")
    _base_c = _CI.ravel() * (ny1 * nz1) + _CJ.ravel() * nz1 + _CK.ravel()
    # 8 vertex offsets (di,dj,dk): OpenFOAM hex order p0..p7
    _od = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
        dtype=np.int64,
    )
    _voff = _od[:, 0] * (ny1 * nz1) + _od[:, 1] * nz1 + _od[:, 2]  # (8,)
    hexes_all = (_base_c[:, None] + _voff[None, :]).astype(np.int64)  # (N, 8)

    if hexes_all.shape[0] == 0:
        return NativeHexResult(
            False,
            time.perf_counter() - t0,
            message="grid 가 비어있음 (target_edge_length 가 bbox 보다 큼)",
            n_self_intersect_pre=_pre_mesh_si_count,
        )

    hexes = hexes_all
    n_grid_total = hexes.shape[0]
    # centroid 로 inside 판정
    centroids = grid_pts[hexes].mean(axis=1)
    inside = _inside_winding_number(centroids, V, F)
    kept = hexes[inside]
    # P1.1 / beta2581 — small-count auto escalate.
    #   trigger 확장: kept==0 → kept<50 (절대 floor 기준).
    #   small-bbox 케이스에서 hex 수가 50 미만으로 떨어지면 mesh_integrity_suspect
    #   flag (line 137) 가 켜지고 grade A 평가에서 disqualify. 이전 escalate
    #   는 kept==0 만 trigger 였으나, 1<=kept<50 인 thin/small case 도 escalate
    #   대상에 포함. n_kept_post > _smallhex_floor 이거나 n_kept_post >
    #   pre_kept * 1.5 면 escalate 채택.
    _smallhex_floor = int(os.environ.get("AUTO_TESSELL_HEX_SMALL_FLOOR", "50"))
    _pre_kept = int(kept.shape[0])
    if _pre_kept < _smallhex_floor:
        # P1 (beta2232 + beta2305) — small bbox auto escalate.
        # target_edge_length 가 사용자 명시 (user_set) 가 아니면, default
        # seed_density 의 grid spacing 이 너무 커서 hex centroid 모두 외부인
        # 케이스. seed_density ×1.7 × 5 회 retry, 매 retry 마다 cap 도 함께
        # ×1.5 로 raise (직전 시도가 per-axis cap 에 binding 된 경우 의미 회복).
        if not _p1_te_user_set:
            # GAP2 / beta2766 — 5→8 retries + 마지막 2회 더 공격적 (2.5x).
            # GAP2-extra / beta2768 — retry 9-10 에서 cap 자동 4x raise (small-bbox
            # 극한 case 의 마지막 회복 시도).
            # 목표: hex grade A 18/20 → 19+/20 (extreme 1 case 회복).
            _retries_max = 10
            for _retry in range(_retries_max):
                # GAP2: retry 6-8 에서 2.5x growth, retry 9-10 에서 cap 4x raise.
                if _retry < 5:
                    _growth = 1.7
                elif _retry < 8:
                    _growth = 2.5
                else:
                    _growth = 3.0  # retry 9-10: 더 공격적
                _new_sd = int(seed_density * (_growth ** (_retry + 1)))
                _new_h = diag / max(1, _new_sd)
                # beta2305: cap 도 escalate — 이전엔 cap=50 binding 으로 인해
                # seed_density 만 늘려봤자 nxyz 가 cap 에서 멈춰 효과 없었음.
                # GAP2-extra: retry 9-10 cap 4x → small-bbox extreme 회복.
                _cap_factor = 4.0 if _retry >= 8 else 1.5
                _new_cap = int(cap * (_cap_factor ** (_retry + 1)))
                # grid 재생성 (line 525-556 의 inline 코드 reproduction).
                _nxyz_req = np.maximum(
                    np.ceil((bmax - bmin) / _new_h).astype(int),
                    1,
                )
                _nxyz = np.minimum(_nxyz_req, _new_cap)
                _nx, _ny, _nz = int(_nxyz[0]), int(_nxyz[1]), int(_nxyz[2])
                _xs = np.linspace(bmin[0], bmax[0], _nx + 1)
                _ys = np.linspace(bmin[1], bmax[1], _ny + 1)
                _zs = np.linspace(bmin[2], bmax[2], _nz + 1)
                _X, _Y, _Z = np.meshgrid(_xs, _ys, _zs, indexing="ij")
                _grid_pts2 = np.stack([_X.ravel(), _Y.ravel(), _Z.ravel()], axis=1)
                _ny1 = _ny + 1
                _nz1 = _nz + 1
                _ia = np.arange(_nx, dtype=np.int64)
                _ja = np.arange(_ny, dtype=np.int64)
                _ka = np.arange(_nz, dtype=np.int64)
                _CI, _CJ, _CK = np.meshgrid(_ia, _ja, _ka, indexing="ij")
                _base_c = _CI.ravel() * (_ny1 * _nz1) + _CJ.ravel() * _nz1 + _CK.ravel()
                _od = np.array(
                    [
                        [0, 0, 0],
                        [1, 0, 0],
                        [1, 1, 0],
                        [0, 1, 0],
                        [0, 0, 1],
                        [1, 0, 1],
                        [1, 1, 1],
                        [0, 1, 1],
                    ],
                    dtype=np.int64,
                )
                _voff = _od[:, 0] * (_ny1 * _nz1) + _od[:, 1] * _nz1 + _od[:, 2]
                _hexes_all2 = (_base_c[:, None] + _voff[None, :]).astype(np.int64)
                if _hexes_all2.shape[0] == 0:
                    continue
                _centroids2 = _grid_pts2[_hexes_all2].mean(axis=1)
                _inside2 = _inside_winding_number(_centroids2, V, F)
                _kept2 = _hexes_all2[_inside2]
                # P1.1 / beta2581 — accept escalate only when post-kept clears
                # _smallhex_floor OR is >=1.5× pre. 0→k 은 항상 채택.
                _post_n = int(_kept2.shape[0])
                _accept_escalate = (
                    (_pre_kept == 0 and _post_n > 0)
                    or (_post_n >= _smallhex_floor)
                    or (_post_n >= int(_pre_kept * 1.5) and _post_n > _pre_kept)
                )
                if _accept_escalate:
                    log.info(
                        "native_hex_p1_auto_escalate",
                        seed_density_old=int(seed_density),
                        seed_density_new=_new_sd,
                        cap_old=int(cap),
                        cap_new=int(_new_cap),
                        retry=_retry + 1,
                        n_kept=int(_kept2.shape[0]),
                        pre_kept=_pre_kept,
                        smallhex_floor=_smallhex_floor,
                    )
                    grid_pts = _grid_pts2
                    hexes = _kept2
                    kept = _kept2
                    n_grid_total = _hexes_all2.shape[0]
                    seed_density = _new_sd
                    h = _new_h
                    cap = _new_cap  # beta2305: 후속 처리도 raised cap 사용.
                    break
        if kept.shape[0] == 0:
            return NativeHexResult(
                False,
                time.perf_counter() - t0,
                message="inside hex 0 — target_edge_length 조정 필요",
                n_self_intersect_pre=_pre_mesh_si_count,
            )

    # 사용된 vertex 만 압축
    used = np.unique(kept.ravel())
    remap = -np.ones(grid_pts.shape[0], dtype=np.int64)
    remap[used] = np.arange(used.shape[0])
    final_hexes = remap[kept].astype(np.int64)
    final_pts = grid_pts[used]

    # v0.4.0-beta22: optional boundary snap — hex vertex 를 STL surface 로 projection.
    # beta66: preserve_features 로 sharp corner 는 feature vertex 에 직접 snap.
    # X2 (beta1830) — surface-aware revert: snap 후 quality 가 강한 악화면 revert.
    if snap_boundary:
        try:
            from core.generator.native_hex.snap import (  # noqa: PLC0415
                snap_hex_boundary_to_surface,
            )
            from core.generator.native_hex.quality import (  # noqa: PLC0415
                hex_quality_report,
            )

            prev_pts_snap = final_pts.copy()
            try:
                prev_q = hex_quality_report(final_pts, final_hexes)
                prev_skew = prev_q.max_skewness
                prev_no = float(getattr(prev_q, "max_non_orthogonality_deg", 0.0))
            except Exception:
                prev_skew = 0.0
                prev_no = 0.0

            final_pts, snap_stats = snap_hex_boundary_to_surface(
                final_pts,
                V,
                F,
                target_edge=h,
                preserve_features=preserve_features,
                feature_angle_deg=feature_angle_deg,
            )
            log.info("native_hex_boundary_snap_applied", **snap_stats)

            # snap 후 quality 검증.
            # GAP-EXTREME / beta2776 — non-orthogonality 90° 회피 추가.
            # 100029 같은 hard 케이스: skew 차이는 작지만 non-ortho 가 90° 도달
            # → grade D 직행. non-ortho 가 60°+ 악화 시 revert.
            try:
                new_q = hex_quality_report(final_pts, final_hexes)
                new_skew = new_q.max_skewness
                new_no = float(getattr(new_q, "max_non_orthogonality_deg", 0.0))
                _revert = (prev_skew >= 0 and new_skew > prev_skew + 4.0) or (
                    new_no >= 89.0 and (prev_no < 70.0 or prev_no - new_no < -20.0)
                )
                if _revert:
                    log.warning(
                        "native_hex_snap_revert",
                        prev_skew=round(prev_skew, 3),
                        new_skew=round(new_skew, 3),
                        prev_no=round(prev_no, 2),
                        new_no=round(new_no, 2),
                    )
                    final_pts = prev_pts_snap
            except Exception:
                pass

            # BETA_HEX_WALLFIT (beta1) — per-vertex guarded wall-fit AFTER the
            # legacy snap. The legacy global skew-revert above stays for the
            # legacy snap; this pass has its own local per-vertex guard (strict
            # surface-distance decrease AND incident signed-vol > eps), so a bad
            # corner reverts alone instead of discarding the whole snap.
            if not os.environ.get("AUTO_TESSELL_HEX_WALLFIT_OFF"):
                final_pts, _wf_stats = _wall_fit_snap(
                    final_pts,
                    _hex_array_to_cell_faces(final_hexes),
                    V,
                    F,
                    h,
                    tol=0.1 * h,
                    ratio=1.0,
                    iters=3,
                )
                log.info("native_hex_wall_fit", path="uniform", **_wf_stats)

            # HEX-SKEW-INNER-RELAX (beta_hex4) — post-wall-fit boundary sliver
            # (|nd| collapsed by the snap) 두께 복원. 표면 정점 frozen ⇒ wall_dev
            # 불변. 전량 accept/revert (Klingner smart) — 최종 mesh 실측 기준.
            if not os.environ.get("AUTO_TESSELL_HEX_SKEW_RELAX_OFF"):
                _rlx_pts, _rlx_stats = _relax_boundary_sliver_interior(
                    final_pts, _hex_array_to_cell_faces(final_hexes)
                )
                _eps = 1e-9
                _accept = (
                    _rlx_stats["post_bskew"] < _rlx_stats["pre_bskew"] - _eps
                    and _rlx_stats["post_int_skew"] <= _rlx_stats["pre_int_skew"] + _eps
                    and _rlx_stats["post_no"] <= _rlx_stats["pre_no"] + _eps
                    and _rlx_stats["post_neg_vol"] == 0.0
                )
                if _accept:
                    final_pts = _rlx_pts
                    log.info("native_hex_skew_relax_applied", path="uniform", **_rlx_stats)
                else:
                    log.info("native_hex_skew_relax_revert", path="uniform", **_rlx_stats)
        except Exception as exc:
            log.warning("native_hex_boundary_snap_failed", error=str(exc))

    # X3 (beta1840) — boundary vertex Laplacian smooth (post-snap).
    if enable_post_smooth and final_hexes.shape[0] > 0:
        try:
            from core.generator.native_hex.quality import (  # noqa: PLC0415
                hex_quality_report,
            )

            # HEX_CACHE: boundary_verts + edge_nbrs from cache.
            _sm_adj = _build_hex_adjacency(final_hexes)
            boundary_v: set[int] = _sm_adj.boundary_verts
            nbrs: list[set[int]] = _sm_adj.edge_nbrs
            prev_pts_sm = final_pts.copy()
            try:
                prev_skew_sm = hex_quality_report(final_pts, final_hexes).max_skewness
            except Exception:
                prev_skew_sm = 0.0
            for _ in range(int(post_smooth_iterations)):
                new_pts = final_pts.copy()
                for vi in boundary_v:
                    if not nbrs[vi]:
                        continue
                    cen = final_pts[list(nbrs[vi])].mean(axis=0)
                    new_pts[vi] = final_pts[vi] + float(post_smooth_relax) * (cen - final_pts[vi])
                final_pts = new_pts
            try:
                new_skew_sm = hex_quality_report(final_pts, final_hexes).max_skewness
                if new_skew_sm > prev_skew_sm + 2.0:
                    log.warning(
                        "native_hex_post_smooth_revert",
                        prev=round(prev_skew_sm, 3),
                        new=round(new_skew_sm, 3),
                    )
                    final_pts = prev_pts_sm
                else:
                    log.info(
                        "native_hex_post_smooth",
                        n_iter=int(post_smooth_iterations),
                        n_bnd=int(len(boundary_v)),
                        skew=round(new_skew_sm, 3),
                    )
            except Exception:
                pass
        except Exception as exc:
            log.debug("native_hex_post_smooth_skipped", reason=str(exc))

    # VAL3 (beta2161) — per-pass neg-vol tracker initialisation.
    _val3_prev = _count_neg_vol_hex(final_pts, final_hexes)
    log.info("native_hex_neg_vol_track", pass_name="post_filter", n_neg=_val3_prev, delta=0)

    # WWW7 (beta2130) — feature edge snap (default ON, env AUTO_TESSELL_WWW7_OFF disables).
    # C-PERF-10 / beta2429 — pass timing log (perf attribution).
    # C-PERF-12 / beta2431 — env AUTO_TESSELL_HEX_WWW7_BUDGET_S 로 cap.
    # default ∞ (no cap). hard mesh 에서 600s+ 걸리던 케이스 사용자 control.
    _t_www7 = __import__("time").perf_counter()
    _www7_budget_s = float(_os_hex_budget.environ.get("AUTO_TESSELL_HEX_WWW7_BUDGET_S", "0"))
    if _www7_budget_s > 0 and __import__("time").perf_counter() - _hex_t_start > _www7_budget_s:
        log.warning(
            "native_hex_www7_budget_skipped",
            elapsed_s=round(__import__("time").perf_counter() - _hex_t_start, 1),
            budget_s=_www7_budget_s,
        )
    elif final_hexes.shape[0] > 0 and final_pts.shape[0] >= 100:
        try:
            from core.generator.native_hex.snap import snap_to_feature_edges  # noqa: PLC0415

            final_pts, www7_stats = snap_to_feature_edges(
                final_pts,
                final_hexes,
                V,
                F,
                top_k=200,
                feature_angle_deg=30.0,
            )
            if www7_stats.get("n_snapped", 0) > 0 or "skipped" not in www7_stats:
                log.info("native_hex_www7_done", **{k: v for k, v in www7_stats.items()})
        except Exception as exc:
            log.debug("native_hex_www7_skipped", reason=str(exc))

    _val3_n = _count_neg_vol_hex(final_pts, final_hexes)
    log.info(
        "native_hex_neg_vol_track", pass_name="WWW7", n_neg=_val3_n, delta=_val3_n - _val3_prev
    )
    _val3_prev = _val3_n
    log.info(
        "native_hex_pass_timing",
        pass_name="WWW7",
        dt_ms=int((__import__("time").perf_counter() - _t_www7) * 1000),
    )

    # HEX_QUALITY1 (beta2137) — non-ortho local post-pass (snappyHexMesh postSnap analog).
    # env AUTO_TESSELL_HEX_QUALITY1_OFF disables. Default ON.
    import os as _os  # noqa: PLC0415

    # C-PERF-11 / beta2430 — HEX_QUALITY1 pass timing (perf attribution).
    _t_hq1 = __import__("time").perf_counter()
    if final_hexes.shape[0] >= 50 and not _os.environ.get("AUTO_TESSELL_HEX_QUALITY1_OFF"):
        try:
            final_pts = _reduce_nonortho_post(final_pts, final_hexes)
        except Exception as exc:
            log.debug("native_hex_quality1_skipped", reason=str(exc))

    _val3_n = _count_neg_vol_hex(final_pts, final_hexes)
    log.info(
        "native_hex_neg_vol_track",
        pass_name="HEX_QUALITY1",
        n_neg=_val3_n,
        delta=_val3_n - _val3_prev,
    )
    _val3_prev = _val3_n
    log.info(
        "native_hex_pass_timing",
        pass_name="HEX_QUALITY1",
        dt_ms=int((__import__("time").perf_counter() - _t_hq1) * 1000),
    )

    # VAL2 (beta2148) — negative-volume hex validation (default ON).
    try:
        final_hexes, _val2_flipped, _val2_degen = validate_hex_cell_volumes(
            final_pts,
            final_hexes,
        )
    except Exception as _val2_exc:
        log.debug("native_hex_val2_skipped", reason=str(_val2_exc))

    _val3_n = _count_neg_vol_hex(final_pts, final_hexes)
    log.info(
        "native_hex_neg_vol_track", pass_name="VAL2_post", n_neg=_val3_n, delta=_val3_n - _val3_prev
    )

    # 최소 system/controlDict + fvSchemes + fvSolution 생성 (checkMesh 가 요구).
    from core.generator.tier_layers_post import (  # noqa: PLC0415
        _ensure_minimal_controldict,
        _write_minimal_fv_dicts,
    )

    _ensure_minimal_controldict(case_dir)
    _write_minimal_fv_dicts(case_dir)

    try:
        stats = _write_polymesh_hex(final_pts, final_hexes, case_dir)
    except Exception as exc:
        return NativeHexResult(
            False,
            time.perf_counter() - t0,
            message=f"polyMesh 쓰기 실패: {exc}",
            n_self_intersect_pre=_pre_mesh_si_count,
        )

    _n_kept = int(stats["num_cells"])
    _phase0_fields = _native_hex_phase0_metrics(
        case_dir,
        np.asarray(final_pts, dtype=np.float64),
        _hex_array_to_cell_faces(final_hexes),
        path="uniform",
        n_written=_n_kept,
    )
    _fill = _n_kept / max(1, n_grid_total)
    if _fill < 0.3:
        log.info(
            "native_hex_low_fill_ratio",
            fill_ratio=_fill,
            n_kept=_n_kept,
            n_grid_total=n_grid_total,
            hint="target_edge_length 를 줄이거나 seed_density 를 높이면 fill 개선",
        )

    # X1 (beta1640) — checkMesh-style quality + plane_coverage + grade.
    grade = "?"
    max_no = -1.0
    mean_no = -1.0
    max_sk = -1.0
    mean_sk = -1.0
    max_asp = -1.0
    plane_cov = -1.0
    plane_area = -1.0
    try:
        from core.generator.native_hex.quality import (
            hex_quality_report,
            hex_quality_grade,
        )

        q = hex_quality_report(final_pts, final_hexes)
        grade = hex_quality_grade(q)
        max_no = q.max_non_orthogonality_deg
        mean_no = q.mean_non_orthogonality_deg
        max_sk = q.max_skewness
        mean_sk = q.mean_skewness
        max_asp = q.max_aspect
        log.info(
            "native_hex_quality_gate",
            grade=grade,
            max_non_ortho=round(max_no, 2),
            mean_non_ortho=round(mean_no, 2),
            max_skew=round(max_sk, 3),
            max_aspect=round(max_asp, 2),
        )
    except Exception as exc:
        log.debug("native_hex_quality_skipped", reason=str(exc))

    try:
        from core.generator.native_tet.plane_coverage import (
            _triangle_planes_and_areas,
            _group_by_plane,
        )

        # hex boundary face (1-owner) 추출 → 2 triangle 로 분할.
        # C-PERF-53 / beta2504 — vectorize via lexsort group sizes.
        bnd_tris: list[list[int]] = []
        if final_hexes.shape[0] > 0:
            _HF_IDX = np.array(_HEX_FACES, dtype=np.int64)  # (6, 4)
            faces_v = final_hexes[:, _HF_IDX].reshape(-1, 4)  # (6C, 4)
            faces_sorted = np.sort(faces_v, axis=1)
            ci_arr = np.repeat(np.arange(final_hexes.shape[0]), 6)
            order_bf = np.lexsort(
                (faces_sorted[:, 3], faces_sorted[:, 2], faces_sorted[:, 1], faces_sorted[:, 0]),
            )
            fs_s = faces_sorted[order_bf]
            faces_orig = faces_v[order_bf]  # for actual quad verts
            ci_s = ci_arr[order_bf]
            diff_bf = np.r_[True, np.any(fs_s[1:] != fs_s[:-1], axis=1)]
            starts_bf = np.where(diff_bf)[0]
            sizes_bf = np.diff(np.r_[starts_bf, len(fs_s)])
            bnd_face_starts = starts_bf[sizes_bf == 1]
            for s in bnd_face_starts.tolist():
                v = faces_orig[s].tolist()
                bnd_tris.append([v[0], v[1], v[2]])
                bnd_tris.append([v[0], v[2], v[3]])
        if bnd_tris:
            B_tri = np.asarray(bnd_tris, dtype=np.int64)
            bbox_diag = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0))) + 1e-30
            in_unit, in_off, in_area = _triangle_planes_and_areas(V, F)
            bn_unit, bn_off, bn_area = _triangle_planes_and_areas(final_pts, B_tri)
            in_groups = _group_by_plane(
                in_unit,
                in_off,
                normal_tol=5e-2,
                offset_rel_tol=5e-3,
                bbox_diag=bbox_diag,
            )
            bn_groups = _group_by_plane(
                bn_unit,
                bn_off,
                normal_tol=5e-2,
                offset_rel_tol=5e-3,
                bbox_diag=bbox_diag,
            )
            n_in = len(in_groups)
            n_covered = 0
            total_in_area = 0.0
            total_match_area = 0.0
            for k_g, idxs in in_groups.items():
                a_in = float(in_area[idxs].sum())
                total_in_area += a_in
                if k_g in bn_groups:
                    a_b = float(bn_area[bn_groups[k_g]].sum())
                    if a_in > 0 and abs(a_b - a_in) / a_in <= 0.10:
                        n_covered += 1
                        total_match_area += a_in
                    else:
                        ratio = min(a_b, a_in) / max(a_in, 1e-30)
                        total_match_area += ratio * a_in
            plane_cov = n_covered / max(n_in, 1) if n_in else 1.0
            plane_area = total_match_area / total_in_area if total_in_area > 0 else 1.0
    except Exception as exc:
        log.debug("native_hex_plane_cov_skipped", reason=str(exc))

    # RUN_SUMMARY (beta2157) — aggregate post-pass counts (observability only).
    log.info(
        "native_hex_run_summary",
        n_cells=_n_kept,
        n_points=int(stats["num_points"]),
        grade=grade,
        n_val_flipped=int(locals().get("_val2_flipped", 0) or 0),
        n_val_degen=int(locals().get("_val2_degen", 0) or 0),
        fill_ratio=round(_fill, 4),
        elapsed=round(time.perf_counter() - t0, 3),
        **_phase0_fields,
    )

    # C-PERF-3 / beta2388 — wall-clock budget 진단.
    _hex_elapsed = __import__("time").perf_counter() - _hex_t_start
    if _hex_elapsed > _hex_budget_log_threshold:
        log.warning(
            "native_hex_wall_clock_high",
            component="native_hex",
            phase="beta2388",
            elapsed_s=round(_hex_elapsed, 1),
            threshold_s=_hex_budget_log_threshold,
            n_cells=_n_kept,
            grade=grade,
        )

    # C-QUAL-11 / beta2407 — hex mesh_integrity_suspect (parity with tet/poly).
    _n_surface_v_hex = int(np.asarray(vertices).shape[0])
    _hex_suspect = bool(
        _n_kept > 0
        and ((_n_surface_v_hex >= 100 and _n_kept < _n_surface_v_hex // 32) or _n_kept < 50)
    )
    if _hex_suspect:
        log.warning(
            "native_hex_mesh_integrity_suspect",
            component="native_hex",
            phase="beta2407",
            n_cells=_n_kept,
            n_surface_v=_n_surface_v_hex,
            ratio=round(_n_kept / max(1, _n_surface_v_hex), 4),
        )
    return NativeHexResult(
        success=True,
        elapsed=time.perf_counter() - t0,
        n_cells=_n_kept,
        n_points=int(stats["num_points"]),
        n_faces=int(stats["num_faces"]),
        fill_ratio=_fill,
        grid_shape=(nx, ny, nz),
        n_grid_total=n_grid_total,
        message=(
            f"native_hex OK — cells={_n_kept}, "
            f"points={stats['num_points']}, grid=({nx},{ny},{nz}), "
            f"fill={_fill:.1%}, target_edge={h:.4g}, grade={grade}"
        ),
        quality_grade=grade,
        max_non_orthogonality_deg=float(max_no),
        mean_non_orthogonality_deg=float(mean_no),
        max_skewness=float(max_sk),
        mean_skewness=float(mean_sk),
        max_aspect=float(max_asp),
        plane_coverage=float(plane_cov),
        plane_area_coverage=float(plane_area),
        # beta2338 — pre-mesh SI count.
        n_self_intersect_pre=_pre_mesh_si_count,
        mesh_integrity_suspect=_hex_suspect,
        **_phase0_fields,
    )
