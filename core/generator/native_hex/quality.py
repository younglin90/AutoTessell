"""X1 — native_hex 결과의 cell quality 측정.

OpenFOAM checkMesh 의 핵심 메트릭 (non-orthogonality / skewness / aspect)
을 numpy 로 직접 계산. snappyHexMesh / cfMesh 와 동일한 평가 척도.
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

_NATIVE_HEX_QUALITY: Any | None = None
_NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED = False


def _load_native_hex_quality() -> Any | None:
    """Load optional C++ fixed-topology quality primitives."""
    global _NATIVE_HEX_QUALITY, _NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED
    if _NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED:
        return _NATIVE_HEX_QUALITY
    _NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED = True

    candidate_dirs: list[Path] = []
    env_dir = os.environ.get("AUTOTESSELL_EXT_BUILD_DIR", "").strip()
    if env_dir:
        candidate_dirs.append(Path(env_dir))
    candidate_dirs.append(Path(__file__).resolve().parents[3] / "auto_tessell_core" / "build")
    for candidate in candidate_dirs:
        if candidate.is_dir():
            candidate_s = str(candidate)
            if candidate_s not in sys.path:
                sys.path.insert(0, candidate_s)

    try:
        _NATIVE_HEX_QUALITY = importlib.import_module("native_hex_quality")
    except Exception:  # noqa: BLE001
        _NATIVE_HEX_QUALITY = None
    return _NATIVE_HEX_QUALITY


def _native_quality_values(
    points: np.ndarray, hexes: np.ndarray
) -> tuple[int, np.ndarray, np.ndarray, np.ndarray, float] | None:
    module = _load_native_hex_quality()
    kernel = getattr(module, "hex_quality_primitives", None) if module is not None else None
    if kernel is None:
        return None
    try:
        face_count, non_orths, skews, aspects, min_face_area = kernel(points, hexes)
        non_orths = np.asarray(non_orths, dtype=np.float64)
        skews = np.asarray(skews, dtype=np.float64)
        aspects = np.asarray(aspects, dtype=np.float64)
        if (
            non_orths.ndim != 1
            or skews.ndim != 1
            or aspects.shape != (len(hexes),)
            or non_orths.size == 0
            or skews.size == 0
        ):
            raise ValueError("native hex quality kernel returned invalid shapes")
        return int(face_count), non_orths, skews, aspects, float(min_face_area)
    except Exception:  # noqa: BLE001
        return None


def _native_generic_cell_volumes(
    points: np.ndarray, cell_faces: list[list[list[int]]]
) -> np.ndarray | None:
    module = _load_native_hex_quality()
    kernel = getattr(module, "generic_cell_signed_volumes", None) if module is not None else None
    if kernel is None:
        return None
    try:
        volumes = np.asarray(kernel(points, cell_faces), dtype=np.float64)
        if volumes.shape != (len(cell_faces),):
            raise ValueError("native generic cell volumes returned invalid shape")
        return volumes
    except Exception:  # noqa: BLE001
        return None


def _native_generic_cell_face_signs(
    points: np.ndarray, cell_faces: list[list[int]]
) -> tuple[np.ndarray, float] | None:
    module = _load_native_hex_quality()
    kernel = getattr(module, "generic_cell_face_signs", None) if module is not None else None
    if kernel is None:
        return None
    try:
        signs, magnitude = kernel(points, cell_faces)
        signs = np.asarray(signs, dtype=np.float64)
        if signs.shape != (len(cell_faces),):
            raise ValueError("native generic cell signs returned invalid shape")
        return signs, float(magnitude)
    except Exception:  # noqa: BLE001
        return None


def _native_generic_side_metrics(
    points: np.ndarray, cell_faces: list[list[list[int]]]
) -> tuple[float, float, float] | None:
    module = _load_native_hex_quality()
    kernel = getattr(module, "generic_side_metrics", None) if module is not None else None
    if kernel is None:
        return None
    try:
        skewness, non_orthogonality, negative_volumes = kernel(points, cell_faces)
        return (
            float(skewness),
            float(non_orthogonality),
            float(negative_volumes),
        )
    except Exception:  # noqa: BLE001
        return None


# OpenFOAM hex face local indexing (mesher.py 와 동일).
_HEX_FACES: tuple[tuple[int, int, int, int], ...] = (
    (0, 3, 2, 1),
    (4, 5, 6, 7),
    (0, 1, 5, 4),
    (3, 7, 6, 2),
    (0, 4, 7, 3),
    (1, 2, 6, 5),
)


@dataclass
class HexQualityReport:
    n_cells: int
    n_faces: int
    max_non_orthogonality_deg: float
    mean_non_orthogonality_deg: float
    p95_non_orthogonality_deg: float
    max_skewness: float
    mean_skewness: float
    max_aspect: float
    mean_aspect: float
    min_face_area: float


def _quad_normal_centroid_area(
    pts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """quad face: (N, 4, 3) → (N, 3) normal (unit), centroid, area."""
    A = pts[:, 0]
    B = pts[:, 1]
    C = pts[:, 2]
    D = pts[:, 3]
    cen = (A + B + C + D) * 0.25
    # 두 삼각형 분할 평균.
    n1 = np.cross(B - A, C - A)
    n2 = np.cross(C - A, D - A)
    n_sum = n1 + n2
    norm = np.linalg.norm(n_sum, axis=1)
    safe = norm > 1e-30
    unit = np.zeros_like(n_sum)
    unit[safe] = n_sum[safe] / norm[safe, None]
    area = 0.5 * (np.linalg.norm(n1, axis=1) + np.linalg.norm(n2, axis=1))
    return unit, cen, area


def hex_quality_report(pts: np.ndarray, hexes: np.ndarray) -> HexQualityReport:
    """uniform/octree hex mesh 의 OpenFOAM-style 품질 통계.

    - non-orthogonality: 두 인접 셀의 cell-cell vector 와 face normal 사이 각도.
      checkMesh 와 동일 정의.
    - skewness: face centroid 와 cell-cell vector 교차점 사이 거리 / face_area^0.5.
    - aspect: cell 의 최장 edge / 최단 edge.
    """
    pts = np.asarray(pts, dtype=np.float64)
    hexes = np.asarray(hexes, dtype=np.int64)
    if hexes.size == 0:
        return HexQualityReport(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    n_cells = hexes.shape[0]
    native_values = _native_quality_values(pts, hexes)
    if native_values is not None:
        n_faces_total, non_orths_arr, skews_arr, aspects_arr, min_face_area = native_values
        return HexQualityReport(
            n_cells=int(n_cells),
            n_faces=int(n_faces_total),
            max_non_orthogonality_deg=float(np.max(non_orths_arr)),
            mean_non_orthogonality_deg=float(np.mean(non_orths_arr)),
            p95_non_orthogonality_deg=float(np.percentile(non_orths_arr, 95)),
            max_skewness=float(np.max(skews_arr)),
            mean_skewness=float(np.mean(skews_arr)),
            max_aspect=float(np.max(aspects_arr)),
            mean_aspect=float(np.mean(aspects_arr)),
            min_face_area=float(min_face_area),
        )

    cell_centroids = pts[hexes].mean(axis=1)

    # 각 cell 의 6 face → owner_idx, neighbor 쌍.
    # face key (vertex sorted tuple) 로 매칭.
    # Vectorized: build all (n_cells×6) face entries in batch.
    _hf_arr = np.array(_HEX_FACES, dtype=np.int64)  # (6, 4)
    n_f = len(_HEX_FACES)  # 6
    # face_verts[ci, fi, :] = vertex indices of face fi in cell ci
    face_verts_raw = hexes[:, _hf_arr]  # (n_cells, 6, 4)
    face_verts_flat = face_verts_raw.reshape(-1, 4)  # (n_cells*6, 4)
    face_keys_arr = np.sort(face_verts_flat, axis=1)  # sorted vertex keys
    face_owner_arr = np.repeat(np.arange(n_cells, dtype=np.int64), n_f)  # (n_cells*6,)
    face_local_arr = np.tile(np.arange(n_f, dtype=np.int64), n_cells)  # (n_cells*6,)

    face_owner = face_owner_arr.tolist()
    face_local = face_local_arr.tolist()

    # face → owner cells dict.
    # C-PERF-75 / beta2526 — vectorize via lexsort + group-boundary.
    face_dict: dict[tuple[int, int, int, int], list[int]] = {}
    if face_keys_arr.size > 0:
        order = np.lexsort(
            (face_keys_arr[:, 3], face_keys_arr[:, 2], face_keys_arr[:, 1], face_keys_arr[:, 0]),
        )
        k_s = face_keys_arr[order]
        i_s = np.arange(face_keys_arr.shape[0])[order]
        diff = np.r_[True, np.any(k_s[1:] != k_s[:-1], axis=1)]
        starts = np.where(diff)[0]
        ends = np.r_[starts[1:], len(k_s)]
        for s, e in zip(starts.tolist(), ends.tolist()):
            kt = (int(k_s[s, 0]), int(k_s[s, 1]), int(k_s[s, 2]), int(k_s[s, 3]))
            face_dict[kt] = i_s[s:e].tolist()

    non_orths: list[float] = []
    skews: list[float] = []
    n_faces_total = 0
    min_face_area = float("inf")
    for k, idxs in face_dict.items():
        n_faces_total += 1
        if len(idxs) != 2:
            continue  # boundary face — non-ortho 측정 안 함.
        i_a, i_b = idxs
        ca = face_owner[i_a]
        cb = face_owner[i_b]
        local_a = face_local[i_a]
        # face vertex 좌표 (cell A 기준).
        verts = pts[hexes[ca, list(_HEX_FACES[local_a])]]
        unit_n, cen_f, area_f = _quad_normal_centroid_area(verts[None])
        n_vec = unit_n[0]
        cen = cen_f[0]
        area = float(area_f[0])
        if area < min_face_area:
            min_face_area = area
        # cell-cell vector.
        d = cell_centroids[cb] - cell_centroids[ca]
        d_norm = float(np.linalg.norm(d))
        if d_norm < 1e-30:
            continue
        d_unit = d / d_norm
        cos_a = float(np.clip(abs(np.dot(d_unit, n_vec)), 0.0, 1.0))
        non_orth_deg = float(np.degrees(np.arccos(cos_a)))
        non_orths.append(non_orth_deg)
        # skewness: cell-cell vector 가 face plane 과 만나는 점과 cen 의 거리.
        # 평면식: (P - cen) · n = 0 → t = (cen - ca) · n / (d_unit · n).
        denom = float(np.dot(d_unit, n_vec))
        if abs(denom) < 1e-30:
            continue
        t = float(np.dot(cen - cell_centroids[ca], n_vec)) / denom
        intersect = cell_centroids[ca] + t * d_unit
        skew_d = float(np.linalg.norm(intersect - cen))
        if area > 0:
            skews.append(skew_d / np.sqrt(area))

    if not non_orths:
        non_orths = [0.0]
    if not skews:
        skews = [0.0]

    # aspect: cell 의 max/min edge — vectorized over all cells at once.
    _edge_a = np.array([0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 3], dtype=np.int64)
    _edge_b = np.array([1, 2, 3, 0, 5, 6, 7, 4, 4, 5, 6, 7], dtype=np.int64)
    # cell_pts: (n_cells, 8, 3)
    cell_pts_all = pts[hexes]
    # edge vectors: (n_cells, 12, 3)
    ev = cell_pts_all[:, _edge_b, :] - cell_pts_all[:, _edge_a, :]
    # edge lengths: (n_cells, 12)
    elens_all = np.linalg.norm(ev, axis=2)
    e_max = elens_all.max(axis=1)  # (n_cells,)
    # min ignoring degenerate edges (< 1e-30)
    elens_safe = np.where(elens_all > 1e-30, elens_all, np.inf)
    e_min = elens_safe.min(axis=1)  # (n_cells,)
    e_min = np.maximum(e_min, 1e-30)
    aspects_arr = e_max / e_min  # (n_cells,)

    return HexQualityReport(
        n_cells=int(n_cells),
        n_faces=int(n_faces_total),
        max_non_orthogonality_deg=float(np.max(non_orths)),
        mean_non_orthogonality_deg=float(np.mean(non_orths)),
        p95_non_orthogonality_deg=float(np.percentile(non_orths, 95)),
        max_skewness=float(np.max(skews)),
        mean_skewness=float(np.mean(skews)),
        max_aspect=float(np.max(aspects_arr)),
        mean_aspect=float(np.mean(aspects_arr)),
        min_face_area=float(min_face_area if min_face_area != float("inf") else 0.0),
    )


def hex_quality_grade(report: HexQualityReport) -> str:
    """checkMesh 기준 grade.

    A: max_non_ortho < 50°, max_skew < 1.0
    B: max_non_ortho < 70°, max_skew < 4.0
    C: max_non_ortho < 80°, max_skew < 8.0
    D: 그 외 / 빈 mesh.
    """
    if report.n_cells == 0:
        return "D"
    if report.max_non_orthogonality_deg < 50.0 and report.max_skewness < 1.0:
        return "A"
    if report.max_non_orthogonality_deg < 70.0 and report.max_skewness < 4.0:
        return "B"
    if report.max_non_orthogonality_deg < 80.0 and report.max_skewness < 8.0:
        return "C"
    return "D"
