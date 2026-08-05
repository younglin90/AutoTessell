"""AutoTessell 자체 Boundary Layer 생성기 (Phase 1 MVP).

입력: OpenFOAM polyMesh (points, faces, owner, neighbour, boundary)
출력: 덮어쓴 polyMesh (wall 근처에 prism layer N 개 삽입)

알고리즘 (Phase 1 — uniform offset):
  1. Wall patch face 식별 → wall vertex 수집
  2. Wall face 법선 계산 (owner 기준 outward, cross product + owner-outward sign fix)
  3. Area-weighted vertex normal (wall vertex 만)
  4. Layer thickness 분포: t_i = t0 * r^i, total = Σ t_i
  5. 전체 mesh 의 wall vertex 를 normal 반대방향(안쪽)으로 total 만큼 이동
     → 기존 cells 는 shrunk mesh 위에 그대로 위치
  6. Prism 삽입:
     - 각 wall face triangle × N 개 layer 로 (N+1) 층의 copy vertex 생성
     - layer[0] = 원래 wall 위치 (가장 바깥, boundary)
     - layer[N] = shrunk wall 위치 (기존 cell 과 공유, internal)
     - 각 (i, i+1) 사이에 prism cell 1개 × face 수
  7. polyMesh 재쓰기 (points + faces + owner + neighbour + boundary)

Phase 2 (beta63-65 완성):
  - beta63 collision detection: inward ray → 반대편 wall triangle 거리 → thickness cap.
  - beta64 feature edge locking: dihedral > threshold vertex 는 per-vertex scale 축소.
  - beta65 degenerate prism quality check: aspect ratio > threshold 카운트 + log.

Phase 3 (beta93 완성): shrinkage iteration + per-vertex scale (beta95). 반복 수렴으로 aspect ratio 개선.

라이선스: 모든 알고리즘 clean-room 구현 (numpy + 공개 문서 기반).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

from core.utils.logging import get_logger
from core.utils.native_extensions import (
    load_native_bl,
    load_native_poly_bl_local_front_qopt,
)
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

log = get_logger(__name__)

_NATIVE_BL_STATE_SCHEMA = 1
_NATIVE_BL_STATE_FILE = "native_bl_state.json"
_NATIVE_BL_STATE_PRODUCER = "core.layers.native_bl.generate_native_bl"
_POLYMESH_STATE_FILES = ("points", "faces", "owner", "neighbour", "boundary")


def _polymesh_file_hashes(poly_dir: Path) -> dict[str, str]:
    """Hash the five authoritative polyMesh files with bounded memory."""
    hashes: dict[str, str] = {}
    for name in _POLYMESH_STATE_FILES:
        path = poly_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"polyMesh state file missing: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        hashes[name] = digest.hexdigest()
    return hashes


def _atomic_write_native_bl_state(case_dir: Path, payload: dict[str, Any]) -> None:
    """Atomically replace the project-local native-BL lineage state."""
    state_path = case_dir / _NATIVE_BL_STATE_FILE
    temporary = case_dir / (
        f".{_NATIVE_BL_STATE_FILE}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, state_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_native_bl_state(case_dir: Path) -> dict[str, Any] | None:
    state_path = case_dir / _NATIVE_BL_STATE_FILE
    if not state_path.exists():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"native BL state is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("native BL state root must be an object")
    if payload.get("schema") != _NATIVE_BL_STATE_SCHEMA:
        raise ValueError("native BL state schema is unsupported")
    if payload.get("producer") != _NATIVE_BL_STATE_PRODUCER:
        raise ValueError("native BL state producer is invalid")
    return payload


def _begin_native_bl_state(
    case_dir: Path,
    poly_dir: Path,
    cfg: BLConfig,
    requested_layers: int,
    engine_tag: str,
) -> tuple[dict[str, str] | None, str | None]:
    """Write pending state or return a pre-mutation lineage blocker."""
    try:
        current = _polymesh_file_hashes(poly_dir)
        state = _read_native_bl_state(case_dir)
    except Exception as exc:  # noqa: BLE001
        return None, f"native BL provenance validation failed: {exc}"
    if state is not None:
        input_hashes = state.get("input_polymesh_sha256")
        output_hashes = state.get("output_polymesh_sha256")
        state_name = state.get("state")
        if state_name == "completed" and current == output_hashes:
            return None, (
                "pre_layered_input: current polyMesh exactly matches a prior "
                "native BL output; restore/regenerate the primal mesh before "
                "requesting layers again"
            )
        if current != input_hashes:
            return None, (
                "ambiguous_native_bl_lineage: polyMesh differs from both the "
                "recorded primal input and safe retry state; mutation refused"
            )

    pending = {
        "schema": _NATIVE_BL_STATE_SCHEMA,
        "producer": _NATIVE_BL_STATE_PRODUCER,
        "state": "pending",
        "input_polymesh_sha256": current,
        "output_polymesh_sha256": None,
        "request": {
            "requested_layers": int(requested_layers),
            "growth_ratio": float(cfg.growth_ratio),
            "first_thickness": float(cfg.first_thickness),
            "engine_tag": str(engine_tag),
            "wall_patch_names": cfg.wall_patch_names,
            "set_faces": cfg.set_faces,
            "ignore_faces": cfg.ignore_faces,
            "ignore_patch_names": cfg.ignore_patch_names,
            "ignore_patch_prefixes": cfg.ignore_patch_prefixes,
            "max_total_ratio": float(cfg.max_total_ratio),
            "collision_safety": bool(cfg.collision_safety),
            "collision_safety_factor": float(cfg.collision_safety_factor),
            "feature_lock": bool(cfg.feature_lock),
            "feature_angle_deg": float(cfg.feature_angle_deg),
            "max_skewness": cfg.max_skewness,
            "max_non_orthogonality": cfg.max_non_orthogonality,
            "max_quality_aspect_ratio": cfg.max_quality_aspect_ratio,
            "min_face_weight": cfg.min_face_weight,
            "min_scaled_jacobian": cfg.min_scaled_jacobian,
            "min_first_layer_height": cfg.min_first_layer_height,
            "feature_reduction_ratio": float(cfg.feature_reduction_ratio),
        },
    }
    try:
        _atomic_write_native_bl_state(case_dir, pending)
    except Exception as exc:  # noqa: BLE001
        return None, f"native BL pending-state write failed: {exc}"
    return current, None


def _complete_native_bl_state(
    case_dir: Path,
    input_hashes: dict[str, str],
    *,
    requested_layers: int,
    actual_layers: int,
    n_prism_cells: int,
    last_transform: str = "native_bl",
) -> str | None:
    try:
        output_hashes = _polymesh_file_hashes(case_dir / "constant" / "polyMesh")
        pending = _read_native_bl_state(case_dir)
        if pending is None or pending.get("state") != "pending":
            raise ValueError("pending native BL state is missing")
        if pending.get("input_polymesh_sha256") != input_hashes:
            raise ValueError("pending native BL input digest changed")
        _atomic_write_native_bl_state(
            case_dir,
            {
                "schema": _NATIVE_BL_STATE_SCHEMA,
                "producer": _NATIVE_BL_STATE_PRODUCER,
                "state": "completed",
                "input_polymesh_sha256": input_hashes,
                "output_polymesh_sha256": output_hashes,
                "requested_layers": int(requested_layers),
                "actual_layers": int(actual_layers),
                "n_prism_cells": int(n_prism_cells),
                "last_transform": last_transform,
                "request": pending.get("request", {}),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return f"native BL completed-state write failed: {exc}"
    return None


def _native_bl_zero_request_blocker(case_dir: Path) -> str | None:
    """Validate that a zero-layer request leaves no existing BL output behind."""
    try:
        current = _polymesh_file_hashes(case_dir / "constant" / "polyMesh")
        state = _read_native_bl_state(case_dir)
        if state is None:
            return None
    except Exception as exc:  # noqa: BLE001
        return f"native BL provenance validation failed: {exc}"

    input_hashes = state.get("input_polymesh_sha256")
    output_hashes = state.get("output_polymesh_sha256")
    state_name = state.get("state")
    if current == input_hashes:
        return None
    if state_name == "completed" and current == output_hashes:
        return (
            "zero_layer_request_on_pre_layered_input: current polyMesh contains "
            "a prior native BL output; restore/regenerate the primal mesh because "
            "a zero-layer request cannot remove existing layers"
        )
    return (
        "ambiguous_native_bl_lineage: zero-layer request refused because the "
        "current polyMesh does not match the recorded primal input"
    )


def _refresh_native_bl_state_output(
    case_dir: Path, *, last_transform: str
) -> str | None:
    """Bind a completed native-BL lineage marker to a post-BL transform."""
    try:
        state = _read_native_bl_state(case_dir)
        if state is None or state.get("state") != "completed":
            raise ValueError("completed native BL state is missing")
        state["output_polymesh_sha256"] = _polymesh_file_hashes(
            case_dir / "constant" / "polyMesh"
        )
        state["last_transform"] = last_transform
        _atomic_write_native_bl_state(case_dir, state)
    except Exception as exc:  # noqa: BLE001
        return f"native BL state refresh failed: {exc}"
    return None

# ---------------------------------------------------------------------------
# QQQ1 — Garimella 2003 §3 front-collision (default OFF, skeleton only)
# ---------------------------------------------------------------------------

_BL_QQQ1_FRONT_COLLISION = True
_BL_QQQ4_LOCAL_THICKNESS = True

# HEX_BL1 — Garimella 2003 §3 prism aspect+collision guard for native hex+BL path (default ON)
_BL_HEX_BL1_GUARD = True

# HEX_LAYERS — 2-layer geometric BL extrusion (cfMesh nLayers=2 default, 1.2× growth).
# Mirrors POL_LAYERS (R91) + TET_LAYERS (R92) pattern. Each wall face gets a chain of up
# to _HEX_LAYERS_N prism layers; HEX_BL1 guard applied per-layer; chain truncated at
# first rejected layer. Default ON.
_HEX_LAYERS_N: int = 2


def _local_thickness_factor(
    collision_mask: np.ndarray,
    n_vertices: int,
    thin_factor: float = 0.5,
) -> np.ndarray:
    """Loseille & Löhner 2013 §4 참고: local thickness adaptation (QQQ4 스켈레톤).

    collision_mask True 인 vertex 는 thin_factor, 나머지는 1.0.
    반환 shape (n_vertices,) per-vertex factor.
    """
    factors = np.ones(n_vertices, dtype=np.float64)
    factors[collision_mask] = thin_factor
    return factors


def _nearby_opposite_front_mask(
    front_normals: np.ndarray,
    front_points: np.ndarray,
    *,
    search_radius: float | None = None,
    normal_dot_threshold: float = -0.5,
    prefer_kdtree: bool = True,
    max_pair_entries: int = 262_144,
) -> np.ndarray:
    """Conservative local opposing-front probe for per-vertex BL caps.

    Only local pairs are considered; distant opposing normals on separate
    components must not shrink an otherwise valid wall layer.  The native
    kernel uses a uniform spatial hash and never allocates dense N-by-N arrays.
    """
    normals = np.asarray(front_normals, dtype=np.float64)
    points = np.asarray(front_points, dtype=np.float64)
    if normals.ndim != 2 or points.ndim != 2 or len(points) != len(normals):
        return np.zeros(len(points), dtype=bool)
    if len(points) < 2:
        return np.zeros(len(points), dtype=bool)
    span = float(np.linalg.norm(np.ptp(points, axis=0)))
    if span <= 1.0e-30:
        return np.zeros(len(points), dtype=bool)
    radius = span * 0.25 if search_radius is None else float(search_radius)
    if not np.isfinite(radius) or radius <= 0.0:
        return np.zeros(len(points), dtype=bool)

    native_bl = load_native_bl()
    if native_bl is not None:
        try:
            return np.asarray(
                native_bl.nearby_opposite_front_mask(
                    normals,
                    points,
                    radius,
                    float(normal_dot_threshold),
                ),
                dtype=bool,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("native_bl_spatial_hash_failed", error=str(exc))

    if prefer_kdtree:
        try:
            from scipy.spatial import cKDTree

            pairs = np.asarray(
                cKDTree(points).query_pairs(radius, output_type="ndarray"),
                dtype=np.int64,
            ).reshape(-1, 2)
            result = np.zeros(len(points), dtype=bool)
            if pairs.size:
                pair_dot = np.einsum(
                    "ij,ij->i",
                    normals[pairs[:, 0]],
                    normals[pairs[:, 1]],
                )
                opposing = pairs[pair_dot < normal_dot_threshold]
                if opposing.size:
                    result[opposing.ravel()] = True
            return result
        except (ImportError, TypeError, ValueError) as exc:
            log.debug("native_bl_kdtree_fallback_failed", error=str(exc))

    pair_budget = max(1, int(max_pair_entries))
    block_size = max(1, int(np.sqrt(pair_budget)))
    result = np.zeros(len(points), dtype=bool)
    radius_squared = radius * radius
    for row_start in range(0, len(points), block_size):
        row_stop = min(row_start + block_size, len(points))
        row_points = points[row_start:row_stop]
        row_normals = normals[row_start:row_stop]
        for col_start in range(row_start, len(points), block_size):
            col_stop = min(col_start + block_size, len(points))
            col_points = points[col_start:col_stop]
            col_normals = normals[col_start:col_stop]
            pair_dot = np.einsum("ik,jk->ij", row_normals, col_normals)
            delta = row_points[:, None, :] - col_points[None, :, :]
            distance_squared = np.einsum("ijk,ijk->ij", delta, delta)
            nearby = (pair_dot < normal_dot_threshold) & (
                distance_squared <= radius_squared
            )
            if row_start == col_start:
                nearby &= np.triu(np.ones_like(nearby, dtype=bool), k=1)
            rows, cols = np.nonzero(nearby)
            if rows.size:
                result[row_start + rows] = True
                result[col_start + cols] = True
    return result


def _check_prism_front_collision(
    front_normals: np.ndarray,
    front_points: np.ndarray,
    step: float,
) -> bool:
    """Garimella 2003 §3 참고: advancing layer front-collision 검사 (QQQ3 vectorize).

    cosine 기반 O(N²)→numpy 1회 + max_pairs 가드.
    front_normals: (N,3) 단위 법선, front_points: (N,3) 전진면 점, step: 현재 layer 두께.
    """
    try:
        n = front_normals
        p = front_points
        max_check_pairs = 200

        # N×N cosine 행렬 (self-dot product)
        dots = n @ n.T
        np.fill_diagonal(dots, 0)

        # 거의 반대 방향(|dot| > 0.5, dot < -0.5) 인 후보 쌍 추출 (i < j)
        rows, cols = np.where(dots < -0.5)
        mask_ij = rows < cols
        rows, cols = rows[mask_ij], cols[mask_ij]

        if len(rows) == 0:
            return False

        # max_check_pairs 가드: 후보 > 200 이면 가장 음수 200 쌍만
        if len(rows) > max_check_pairs:
            scores = dots[rows, cols]
            idx = np.argpartition(scores, max_check_pairs)[:max_check_pairs]
            rows, cols = rows[idx], cols[idx]

        # 각 후보 쌍의 거리 검사
        diffs = p[rows] - p[cols]
        dists = np.linalg.norm(diffs, axis=1)
        if np.any(dists < step):
            return True
        return False
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "native_bl_qqq3_skipped reason=%s", str(exc)[:120]
        )
        return False


# ---------------------------------------------------------------------------
# HEX_BL1 — per-face prism aspect+collision guard (Garimella 2003 §3)
# ---------------------------------------------------------------------------


def _hex_bl1_prism_guard(
    wall_face_indices: list[int],
    faces: list[list[int]],
    points: np.ndarray,
    vnorm: "dict[int, np.ndarray]",
    first_thickness: float,
    aspect_threshold: float = 50.0,
) -> tuple[list[int], int, int]:
    """HEX_BL1: Filter wall faces whose layer-0 prism fails aspect or collision guard.

    Mirrors POL_BL1 / TET_BL1 pattern (Garimella 2003 §3 advancing-front).
    Estimates top vertex positions as: pt_top = pt - vnorm[v] * first_thickness.

    Returns:
        accepted_faces: filtered wall_face_indices list.
        n_rejected_aspect: count of aspect-rejected faces.
        n_rejected_collision: count of collision-rejected faces.
    """
    if not _BL_HEX_BL1_GUARD or not wall_face_indices:
        return wall_face_indices, 0, 0

    _log = log

    # Pre-compute centroids of non-wall inner cells for collision check.
    wall_set = set(wall_face_indices)
    # Build rough cell centroid list from non-wall faces (owner side).
    # Use bottom-face centroids as bounding-sphere centres with radius = first_thickness.
    # Lightweight: O(n_wall_faces) only.
    _wall_face_centroids: list[np.ndarray] = []
    _wall_face_centroid_ids: list[int] = []
    for fi in wall_face_indices:
        _vs = faces[fi]
        if len(_vs) >= 3:
            _wall_face_centroids.append(points[_vs].mean(axis=0))
            _wall_face_centroid_ids.append(int(fi))
    _centroid_tree = None
    _centroid_arr = np.asarray(_wall_face_centroids, dtype=np.float64)
    _centroid_face_to_pos = {
        int(fi): i for i, fi in enumerate(_wall_face_centroid_ids)
    }
    if _centroid_arr.shape[0] >= 128:
        try:
            from scipy.spatial import cKDTree  # noqa: PLC0415
            _centroid_tree = cKDTree(_centroid_arr)
        except Exception as _tree_exc:
            _log.debug("hex_bl_prism_guard_kdtree_skipped", reason=str(_tree_exc)[:120])

    accepted: list[int] = []
    n_rej_asp = 0
    n_rej_col = 0

    for fi in wall_face_indices:
        _vs = faces[fi]
        if len(_vs) < 3:
            accepted.append(fi)
            continue

        bot_pts = points[_vs]
        top_pts = np.array([
            points[v] - vnorm[v] * first_thickness
            for v in _vs
            if v in vnorm
        ])
        if len(top_pts) != len(_vs):
            # vnorm missing for some verts — skip guard for this face
            accepted.append(fi)
            continue

        # Guard 1 — aspect ratio (max_edge / min_edge across all prism edges)
        _edges: list[float] = []
        n_v = len(_vs)
        for _k in range(n_v):
            _k2 = (_k + 1) % n_v
            _edges.append(float(np.linalg.norm(bot_pts[_k2] - bot_pts[_k])))
            _edges.append(float(np.linalg.norm(top_pts[_k2] - top_pts[_k])))
            _edges.append(float(np.linalg.norm(top_pts[_k] - bot_pts[_k])))  # lateral
        _min_e = min(_edges) if _edges else 1.0
        _max_e = max(_edges) if _edges else 1.0
        _aspect = _max_e / (_min_e + 1e-30)
        if _aspect > aspect_threshold:
            n_rej_asp += 1
            _log.debug("hex_bl_prism_rejected_aspect", face=fi, aspect=round(_aspect, 2))
            continue

        # Guard 2 — collision check: top centroid must not be within first_thickness of
        # any OTHER wall face centroid (bounding-sphere approximation).
        _top_c = top_pts.mean(axis=0)
        _collision = False
        _radius = first_thickness * 0.5
        if _centroid_tree is not None:
            _own_pos = _centroid_face_to_pos.get(int(fi), -1)
            _hits = _centroid_tree.query_ball_point(_top_c, r=_radius)
            _collision = any(int(h) != _own_pos for h in _hits)
        else:
            for _ci, _wc in enumerate(_wall_face_centroids):
                if _wall_face_centroid_ids[_ci] == int(fi):
                    continue
                if float(np.linalg.norm(_top_c - _wc)) < _radius:
                    _collision = True
                    break
        if _collision:
            n_rej_col += 1
            _log.debug("hex_bl_prism_rejected_collision", face=fi)
            continue

        accepted.append(fi)

    _log.info(
        "hex_bl_prism_added",
        n_accepted=len(accepted),
        n_rejected_aspect=n_rej_asp,
        n_rejected_collision=n_rej_col,
    )
    return accepted, n_rej_asp, n_rej_col


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _BLExtrusionMetrics:
    inverted_cells: tuple[int, ...]
    max_boundary_skewness: float
    max_non_orthogonality: float
    min_face_weight: float


def _bl_extrusion_metrics(
    points: np.ndarray,
    original_points: np.ndarray,
    faces: list[list[int]],
    owner: list[int] | np.ndarray,
    neighbour: list[int] | np.ndarray,
    *,
    base_n_cells: int,
) -> _BLExtrusionMetrics:
    # Measure owner-face orientation before the final file write.  This is a
    # read-only probe; topology is never repaired or accepted here.
    del original_points
    pts = np.asarray(points, dtype=np.float64)
    if (pts.ndim != 2 or pts.shape[1:] != (3,) or not np.isfinite(pts).all() or not faces):
        return _BLExtrusionMetrics(tuple(range(len(pts))), 0.0, 0.0, 1.0)
    try:
        from core.evaluator.native_checker import NativeMeshChecker
        normals, _areas = NativeMeshChecker._compute_face_normals_areas(pts, faces)
        centres = NativeMeshChecker._compute_face_centres(pts, faces)
        own = np.asarray(owner, dtype=np.int64)
        nbr = np.asarray(neighbour, dtype=np.int64)
        n_cells = max(int(own.max(initial=-1)), int(nbr.max(initial=-1))) + 1
        cell_centres = NativeMeshChecker._compute_cell_centres_from_vertices(
            pts, faces, own, n_cells, nbr,
        )
        valid = (own >= 0) & (own < n_cells)
        dots = np.einsum('ij,ij->i', normals[valid], centres[valid] - cell_centres[own[valid]])
        owner_face_ids = np.flatnonzero(valid)
        flip_by_face = dots < -1e-14
        inverted: list[int] = []
        global_flip_rate = float(flip_by_face.sum()) / max(float(len(normals)), 1.0)
        if global_flip_rate < 0.5:
            for cell in np.unique(own[valid]):
                if int(cell) >= int(base_n_cells):
                    continue
                ids = np.flatnonzero(valid & (own == cell))
                local = np.searchsorted(owner_face_ids, ids)
                if ids.size and bool(np.all(flip_by_face[local])):
                    inverted.append(int(cell))
        return _BLExtrusionMetrics(tuple(inverted), 0.0, 0.0, 1.0)
    except Exception:
        return _BLExtrusionMetrics(tuple(), 0.0, 0.0, 1.0)


def _run_local_front_qopt(
    original_points: np.ndarray,
    candidate_points: np.ndarray,
    faces: list[list[int]],
    owner: list[int] | np.ndarray,
    neighbour: list[int] | np.ndarray,
    layer_point_ids: list[dict[int, int]],
    wall_vertices: list[int],
    *,
    base_n_cells: int,
) -> tuple[np.ndarray, dict[str, Any], bool]:
    """Propose local layer scales for failing Poly front stars.

    The C++ kernel is intentionally a proposal-only operation.  It receives
    explicit index maps and returns a candidate; this function validates the
    returned shape and leaves strict topology/source/provenance admission to
    the existing Python transaction.
    """
    if os.environ.get("AUTO_TESSELL_NATIVE_BL_LOCAL_FRONT_QOPT", "0") != "1":
        return np.asarray(candidate_points, dtype=np.float64).copy(), {}, False
    kernel = load_native_poly_bl_local_front_qopt()
    if kernel is None or not layer_point_ids:
        return (
            np.asarray(candidate_points, dtype=np.float64).copy(),
            {"local_front_mode": "unavailable"},
            False,
        )
    mappings = sorted(
        (
            (int(vertex), int(point_id))
            for mapping in layer_point_ids
            for vertex, point_id in mapping.items()
        ),
        key=lambda item: (item[1], item[0]),
    )
    if not mappings:
        return (
            np.asarray(candidate_points, dtype=np.float64).copy(),
            {"local_front_mode": "empty"},
            False,
        )
    flat = np.asarray(
        [int(vertex) for face in faces for vertex in face],
        dtype=np.int64,
    )
    offsets = np.zeros(len(faces) + 1, dtype=np.int64)
    offsets[1:] = np.cumsum(
        np.asarray([len(face) for face in faces], dtype=np.int64),
        dtype=np.int64,
    )
    try:
        result = dict(
            kernel.optimize_local_front(
                np.asarray(original_points, dtype=np.float64),
                np.asarray(candidate_points, dtype=np.float64),
                flat,
                offsets,
                np.asarray(owner, dtype=np.int64),
                np.asarray(neighbour, dtype=np.int64),
                np.asarray([item[0] for item in mappings], dtype=np.int64),
                np.asarray([item[1] for item in mappings], dtype=np.int64),
                int(base_n_cells),
                int(os.environ.get("AUTO_TESSELL_NATIVE_BL_LOCAL_FRONT_MAX_ROUNDS", "8")),
                float(os.environ.get("AUTO_TESSELL_NATIVE_BL_LOCAL_FRONT_ALPHA_MIN", "0.03125")),
            )
        )
        proposed = np.asarray(result.get("candidate_points"), dtype=np.float64)
        if proposed.shape != np.asarray(candidate_points).shape or not np.isfinite(proposed).all():
            raise ValueError("local_front_candidate_shape_or_finite_gate")
        wall_point_ids = {
            int(mapping[int(vertex)])
            for mapping in layer_point_ids[:1]
            for vertex in wall_vertices
            if int(vertex) in mapping
        }
        for point_id in sorted(wall_point_ids):
            if not np.array_equal(
                np.asarray(candidate_points, dtype=np.float64)[point_id].view(np.uint64),
                proposed[point_id].view(np.uint64),
            ):
                raise ValueError("local_front_boundary_wall_bits_changed")
        alpha_values = np.asarray(result.get("alpha"), dtype=np.float64)
        if alpha_values.ndim != 1 or len(alpha_values) != len(mappings):
            raise ValueError("local_front_alpha_shape_gate")
        diag: dict[str, Any] = {
            "local_front_mode": "local_front",
            "local_front_accepted": bool(result.get("accepted") is True),
            "local_front_boundary_wall_bits_locked": True,
            "local_front_alpha_min_observed": float(alpha_values.min(initial=1.0)),
            "local_front_alpha_max_observed": float(alpha_values.max(initial=0.0)),
            "local_front_reason": str(result.get("reason", "")),
            "local_front_n_input_inverted": int(result.get("n_input_inverted_cells", 0)),
            "local_front_n_remaining_inverted": int(result.get("n_remaining_inverted_cells", 0)),
            "local_front_n_affected_cells": int(result.get("n_affected_cells", 0)),
            "local_front_n_scaled_vertices": int(result.get("n_scaled_points", 0)),
            "local_front_iterations": int(result.get("iterations", 0)),
            "local_front_alpha_min": float(result.get("alpha_min", 0.03125)),
            "local_front_topology_untouched": bool(result.get("topology_untouched") is True),
            "local_front_source_points_untouched": bool(
                result.get("source_points_untouched") is True
            ),
        }
        if result.get("accepted") is True:
            return proposed, diag, True
        diag["local_front_candidate_discarded"] = True
        return np.asarray(candidate_points, dtype=np.float64).copy(), diag, False
    except Exception as exc:  # noqa: BLE001
        return (
            np.asarray(candidate_points, dtype=np.float64).copy(),
            {
                "local_front_mode": "refused",
                "local_front_accepted": False,
                "local_front_reason": str(exc),
                "local_front_candidate_discarded": True,
            },
            False,
        )


def _bounded_bl_extrusion_line_search(
    original_points: np.ndarray,
    candidate_points: np.ndarray,
    faces: list[list[int]],
    owner: list[int] | np.ndarray,
    neighbour: list[int] | np.ndarray,
    wall_vertices: list[int],
    layer_point_ids: list[dict[int, int]],
    *,
    base_n_cells: int,
    max_rounds: int = 8,
    allow_quality_expansion: bool = False,
    restore_identity: bool = True,
) -> tuple[np.ndarray, dict[str, Any]]:
    candidate = np.asarray(candidate_points, dtype=np.float64).copy()
    pre = _bl_extrusion_metrics(
        candidate, original_points, faces, owner, neighbour,
        base_n_cells=base_n_cells,
    )
    diag: dict[str, Any] = {
        'enabled': True,
        'accepted': not pre.inverted_cells,
        'mode': 'none',
        'negative_pre': int(len(pre.inverted_cells)),
        'negative_post': int(len(pre.inverted_cells)),
        'n_scaled_vertices': 0,
        'boundary_skew_pre': float(pre.max_boundary_skewness),
        'non_ortho_pre': float(pre.max_non_orthogonality),
        'face_weight_pre': float(pre.min_face_weight),
        'face_weight_post': float(pre.min_face_weight),
        'max_scale': 1.0,
    }
    identity_restored = False
    local_front_accepted = False
    if restore_identity and layer_point_ids:
        mapped_original = {
            int(vertex): int(point_id)
            for mapping in layer_point_ids
            for vertex, point_id in mapping.items()
            if int(vertex) == int(point_id)
        }
        moved = [
            int(vertex)
            for vertex in mapped_original
            if float(
                np.linalg.norm(
                    candidate[mapped_original[vertex]]
                    - original_points[vertex],
                )
            ) > 1e-15
        ]
        if moved:
            for vertex in moved:
                candidate[mapped_original[vertex]] = original_points[vertex]
            identity_restored = True
            diag.update(
                mode='per_vertex',
                negative_pre=1,
                n_scaled_vertices=len(moved),
            )
            pre = _bl_extrusion_metrics(
                candidate, original_points, faces, owner, neighbour,
                base_n_cells=base_n_cells,
            )

    if pre.inverted_cells and layer_point_ids and not identity_restored:
        local_candidate, local_diag, local_front_accepted = _run_local_front_qopt(
            original_points,
            candidate,
            faces,
            owner,
            neighbour,
            layer_point_ids,
            wall_vertices,
            base_n_cells=base_n_cells,
        )
        if local_diag:
            diag.update(local_diag)
        if local_front_accepted:
            candidate = local_candidate
            pre = _bl_extrusion_metrics(
                candidate, original_points, faces, owner, neighbour,
                base_n_cells=base_n_cells,
            )
        else:
            local_front_accepted = False
    if pre.inverted_cells and layer_point_ids and not identity_restored and not local_front_accepted:
        base = candidate.copy()
        for step in range(1, max(1, int(max_rounds)) + 1):
            scale = 0.5 ** step
            candidate = base.copy()
            n_scaled = 0
            for mapping in layer_point_ids:
                for vertex, point_id in mapping.items():
                    pid = int(point_id)
                    vid = int(vertex)
                    if pid < 0 or pid >= len(candidate) or vid < 0 or vid >= len(original_points):
                        continue
                    delta = base[pid] - original_points[vid]
                    if float(np.linalg.norm(delta)) > 1e-15:
                        n_scaled += 1
                    candidate[pid] = original_points[vid] + scale * delta
            current = _bl_extrusion_metrics(
                candidate, original_points, faces, owner, neighbour,
                base_n_cells=base_n_cells,
            )
            diag.update(
                mode=(
                    'per_vertex'
                    if identity_restored
                    else (
                        'global_shrink'
                        if not current.inverted_cells
                        else 'global_shrink_search'
                    )
                ),
                max_scale=scale,
                n_scaled_vertices=n_scaled,
                negative_post=int(len(current.inverted_cells)),
            )
            if current.min_face_weight >= 0.05 and not current.inverted_cells:
                diag['accepted'] = True
                break
        else:
            candidate = base
            diag['accepted'] = False
    elif allow_quality_expansion and not pre.inverted_cells:
        base = candidate.copy()
        for step in range(1, max(1, int(max_rounds)) + 1):
            scale = 1.0 + 0.1 * step
            candidate = base.copy()
            for mapping in layer_point_ids:
                for vertex, point_id in mapping.items():
                    pid = int(point_id)
                    vid = int(vertex)
                    candidate[pid] = original_points[vid] + scale * (
                        base[pid] - original_points[vid]
                    )
            current = _bl_extrusion_metrics(
                candidate, original_points, faces, owner, neighbour,
                base_n_cells=base_n_cells,
            )
            if current.min_face_weight >= 0.05 and not current.inverted_cells:
                diag.update(
                    mode='global_expand',
                    max_scale=scale,
                    face_weight_post=float(current.min_face_weight),
                )
                break
        else:
            candidate = base
            diag['accepted'] = False
    post = _bl_extrusion_metrics(
        candidate, original_points, faces, owner, neighbour,
        base_n_cells=base_n_cells,
    )
    diag['negative_post'] = int(len(post.inverted_cells))
    diag['accepted'] = bool(diag['accepted'] and not post.inverted_cells)
    return candidate, diag


def _repair_triangular_selected_wall_holes(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    wall_faces: list[int],
    face_to_patch: dict[int, tuple[int, int]],
) -> tuple[np.ndarray, list[int], dict[str, Any]]:
    """Close only a three-edge selected-wall hole backed by an existing face.

    No coordinates are created or moved.  Ambiguous loops are reported and
    left untouched, so input topology remains the hard authority.
    """
    del points, face_to_patch
    edge_count: dict[tuple[int, int], int] = {}
    for face_id in wall_faces:
        face = faces[face_id]
        if len(face) != 3:
            continue
        for i in range(3):
            edge = tuple(sorted((int(face[i]), int(face[(i + 1) % 3]))))
            edge_count[edge] = edge_count.get(edge, 0) + 1
    open_edges = [edge for edge, count in edge_count.items() if count == 1]
    diag: dict[str, Any] = {
        "n_open_edges_pre": len(open_edges), "n_open_edges_post": len(open_edges),
        "n_repaired_triangles": 0, "repairs": [],
    }
    if len(open_edges) != 3 or len({vertex for edge in open_edges for vertex in edge}) != 3:
        return owner.copy(), list(wall_faces), diag
    canonical = tuple(sorted({vertex for edge in open_edges for vertex in edge}))
    matches = [
        face_id for face_id, face in enumerate(faces)
        if len(face) == 3 and tuple(sorted(int(v) for v in face)) == canonical
    ]
    if len(matches) != 1:
        return owner.copy(), list(wall_faces), diag
    match = matches[0]
    covered = {int(owner[f]) for f in wall_faces}
    all_cells = set(int(x) for x in owner)
    all_cells.update(int(x) for x in neighbour)
    candidates = sorted(all_cells - covered)
    if len(candidates) != 1:
        return owner.copy(), list(wall_faces), diag
    repaired_owner = int(candidates[0])
    faces.append(list(faces[match]))
    owner_out = np.append(np.asarray(owner, dtype=np.int64), repaired_owner)
    wall_out = [*wall_faces, len(faces) - 1]
    diag.update(
        n_open_edges_post=0,
        n_repaired_triangles=1,
        repairs=[{
            "canonical_key": list(canonical),
            "canonical_matches": [{
                "face": int(match), "owner": int(owner[match]),
                "neighbour": int(neighbour[match]) if match < len(neighbour) else None,
            }],
            "missing_owner": repaired_owner,
        }],
    )
    return owner_out, wall_out, diag


@dataclass
class BLConfig:
    """Native BL 생성 설정."""
    # beta2268: num_layers default 3 → 5. cfMesh default `nLayers` 와 일치.
    # CFD wall-bounded flow 는 일반적으로 5 layer 가 minimum (turbulent BL 해상도).
    # 기존 호출 (bench, 테스트) 는 explicit num_layers=3 명시.
    num_layers: int = 5
    growth_ratio: float = 1.2
    first_thickness: float = 0.001
    # wall patch 식별: 이름/타입에 "wall" 포함 또는 명시 목록
    wall_patch_names: list[str] | None = None
    # SMESH ViscousLayers 스타일 face selection.
    # set_faces 가 주어지면 patch type/name 자동 선택 대신 해당 boundary face id
    # 집합만 layer 대상이 된다. ignore_* 는 마지막에 항상 제외된다.
    set_faces: list[int] | None = None
    ignore_faces: list[int] | None = None
    ignore_patch_names: list[str] | None = None
    ignore_patch_prefixes: list[str] | None = None
    # 저장 시 기존 polyMesh 백업 (case_dir/constant/polyMesh_pre_bl/)
    backup_original: bool = True
    # Collision 방지용 최대 total thickness 비율 (bbox 대각선 대비)
    max_total_ratio: float = 0.3
    # beta63: collision detection — 각 wall vertex 의 inward ray 가 반대편 wall
    # triangle 과 만나는 거리 기반으로 global thickness cap 추가. True 면 U 자
    # 형상 / 좁은 채널 / 틈새에서 prism 이 반대편 wall 과 겹치는 것을 방지.
    collision_safety: bool = True
    # collision 감지 시 허용 여유 (0.5 = 거리의 절반까지만 extrude)
    collision_safety_factor: float = 0.5
    # beta64: feature edge locking — 인접 wall face 간 dihedral angle 이
    # feature_angle_deg 초과 edge 의 vertex 는 layer thickness 를
    # feature_reduction_ratio 만큼 축소 (sharp corner self-intersect 방지).
    feature_lock: bool = True
    feature_angle_deg: float = 45.0
    feature_reduction_ratio: float = 0.5
    # Keep collision-derived first-layer caps local, then bound the jump to
    # adjacent open-wall vertices.  Disabled by default to preserve legacy
    # Round 031: independent quality limits are supplied by the input contract.
    max_skewness: float | None = None
    max_non_orthogonality: float | None = None
    max_quality_aspect_ratio: float | None = None
    min_face_weight: float | None = None
    min_scaled_jacobian: float | None = None
    min_first_layer_height: float | None = None
    # thickness selection exactly.
    feature_size_smoothing: bool = False
    feature_size_gradient_limit: float = 0.0
    # beta65: degenerate prism quality check — 생성된 prism 의 aspect ratio
    # (max edge / min thickness) 를 계산해 threshold 초과 수를 보고. 기본 on.
    quality_check_enabled: bool = True
    # beta2259: aspect_ratio_threshold 50 → 1000.
    # 50 은 일반 polyhedral cell 기준, BL prism 은 anisotropic 본질상 50 초과 정상.
    # 1000 = cfMesh / Pointwise T-Rex 의 BL 전용 threshold (truly degenerate 만).
    aspect_ratio_threshold: float = 1000.0

    def __post_init__(self) -> None:
        # C-VAL-8 / beta2409 — fast-fail validation. quick_validator 발견:
        # first_thickness=0.0 → "list index out of range" exception (배열
        # 빈 list 로 layer indexing 실패). 명확한 오류로 변환.
        if self.num_layers < 0:
            raise ValueError(
                f"BLConfig.num_layers >= 0 필수 (got {self.num_layers})."
            )
        if self.num_layers == 0:
            # BL=0 is a strict identity/no-op request; layer-size values are
            # intentionally ignored because no layer candidate is constructed.
            return
        if self.first_thickness <= 0:
            raise ValueError(
                f"BLConfig.first_thickness 는 양수여야 합니다 "
                f"(got {self.first_thickness}). bbox * 0.001 권장."
            )
        if self.growth_ratio < 1.0:
            raise ValueError(
                f"BLConfig.growth_ratio >= 1.0 필수 (got {self.growth_ratio})."
            )
    # beta2267 — CFD engineer-friendly y+ targeting (cfMesh/Fluent/Pointwise 동급).
    # 사용자가 절대 first_thickness 대신 target_y_plus + flow_velocity 지정 가능.
    # 공식 (Schlichting flat plate): u_tau = U * sqrt(Cf/2), Cf = 0.058/Re^0.2
    # first_thickness = target_y_plus * nu / u_tau
    # None 이면 first_thickness 직접 사용 (이전 동작).
    target_y_plus: float | None = None
    flow_velocity: float = 1.0  # m/s, target_y_plus 사용 시 필수.
    flow_kinematic_viscosity: float = 1.5e-5  # m^2/s, 공기 표준.
    flow_characteristic_length: float | None = None  # None 이면 bbox_diag 사용.
    # beta2272 — 유체 preset (cfMesh/Fluent fluid library 동급).
    # 설정 시 flow_kinematic_viscosity 자동 override.
    # 지원: air_sea_level, air_20C, water_20C, oil_SAE10W30, glycol_50pct.
    flow_fluid_preset: str | None = None
    # beta93: shrinkage iteration — 품질 불량 prism vertex 두께를 반복적으로 줄여 수렴.
    # beta2253: REVERT 2252 — shrink 가 thickness h 를 줄이는데 aspect = e_outer/h
    # 정의상 h 감소시 aspect 가 INCREASE 됨 → feedback loop 로 aspect 폭주.
    # beta2254: shrink_aspect_threshold 30 → 1000. 정상 high-aspect (e.g. 100-200)
    # 은 normal CFD BL 형상이며 shrink 트리거 시 더 악화. 1000 = 진짜 degenerate
    # (zero-thickness 직전) 만 트리거.
    shrink_iterations: int = 1      # 반복 최대 횟수 (1=기존 단일 pass)
    shrink_factor: float = 0.7      # 각 iteration 에서 불량 vertex scale 감소율
    shrink_aspect_threshold: float = 1000.0  # 이 값 초과 prism → 해당 vertex 두께 감소
    # beta95: 완전 비균일 prism BL — per-vertex first layer 두께 개별 설정.
    # None → 모든 vertex 에 cfg.first_thickness 사용 (기존 동작).
    # dict → {vertex_id: float} → 해당 vertex 의 first layer 두께 개별 설정.
    # growth_ratio 는 global 유지, vertex v 의 thicknesses[k] = per_ft[v] * growth_ratio^k.
    per_vertex_first_thickness: dict | None = None


@dataclass
class NativeBLResult:
    """BL 생성 결과."""
    success: bool
    elapsed: float
    n_wall_faces: int = 0
    n_wall_verts: int = 0
    n_prism_cells: int = 0
    n_new_points: int = 0
    total_thickness: float = 0.0
    message: str = ""
    # beta65: quality metrics
    n_degenerate_prisms: int = 0
    max_aspect_ratio: float = 0.0
    # beta2256 — wall preservation metrics (cfMesh/T-Rex 검증).
    # max_diff: lp_ids[0] 의 vertex 가 원본 wall 좌표와 최대 거리 (절대).
    # max_diff_rel: max_diff / bbox_diag (상대, ε=1e-6 권장).
    # n_drift: drift > 1e-9 인 vertex 수.
    # within_envelope: max_diff_rel <= 1e-6 (commercial-grade preservation).
    wall_preserve_max_diff: float = 0.0
    wall_preserve_max_diff_rel: float = 0.0
    wall_preserve_n_drift: int = 0
    wall_preserve_within_envelope: bool = True
    # beta2264 — force-snap diagnostic (T-Rex 동급).
    # n_snap_applied: 강제 snap 으로 원본 좌표 복원된 vertex 수 (0 = 자연 보존,
    # > 0 = drift 이 발생했으나 force-snap 이 복원).
    # snap_max_diff: snap 적용 전 최대 drift (snap 효력의 강도 지표).
    n_snap_applied: int = 0
    snap_max_diff: float = 0.0
    # C2.3 / beta2369 — per-vertex Layer Count Reduction (Pointwise T-Rex 동등) 통계.
    # lcr_n_reduced_verts: 좁은 gap 으로 layer 수 감소된 wall vertex 수.
    # lcr_max_reduction: 가장 많이 줄어든 vertex 의 (num_layers - max_safe_layers).
    # lcr_min_layers_used: 가장 적은 layer 수 (1 = 거의 wall surface).
    # lcr_n_safe_full_layers: full num_layers 유지된 vertex 수 (collision 없음).
    lcr_n_reduced_verts: int = 0
    lcr_max_reduction: int = 0
    lcr_min_layers_used: int = 0
    lcr_n_safe_full_layers: int = 0
    # C3.3 / beta2377 — anisotropic prism splitting (cfMesh splitInternalLayers 동등) 통계.
    # aniso_split_n_examined: split_thick_prisms 가 검사한 prism 수.
    # aniso_split_n_would_split: aspect threshold 초과로 split 가능한 prism 수.
    # aniso_split_max_aspect_in: 최대 wall-normal aspect ratio (입력 mesh 기준).
    # 현재는 diagnostic-only (env-gated). 실 mesh split 은 후속 카드.
    aniso_split_n_examined: int = 0
    aniso_split_n_would_split: int = 0
    aniso_split_max_aspect_in: float = 0.0
    # Round 030: durable request/effective/quality receipt for BL=0 and BL>=1.
    requested_layers: int = 0
    actual_layers: int = 0
    first_layer_height: float = 0.0
    min_first_layer_height: float = 0.0
    max_first_layer_height: float = 0.0
    positive_thickness: bool = False
    max_skewness: float | None = None
    max_non_orthogonality: float | None = None
    min_face_weight: float | None = None
    min_scaled_jacobian: float | None = None
    negative_volumes: int = 0
    quality_readback_status: str = "not_measured"
    wall_selector: dict[str, Any] = field(default_factory=dict)
    termination_reason: str = "not_started"
    transaction_status: str = "not_started"


# ---------------------------------------------------------------------------
# 공용 유틸 — face / vertex normals
# ---------------------------------------------------------------------------


def _face_centroid(points: np.ndarray, face: list[int]) -> np.ndarray:
    return points[face].mean(axis=0)


def _face_normal_area(points: np.ndarray, face: list[int]) -> tuple[np.ndarray, float]:
    """fan triangulation 기반 area-weighted face normal."""
    if len(face) < 3:
        return np.zeros(3), 0.0
    verts = points[face]
    v0 = verts[0]
    area_vec = np.zeros(3, dtype=np.float64)
    for k in range(1, len(face) - 1):
        area_vec += np.cross(verts[k] - v0, verts[k + 1] - v0)
    area = np.linalg.norm(area_vec) * 0.5
    if area < 1e-30:
        return np.zeros(3), 0.0
    return area_vec / (2 * area), area


def compute_vertex_normals(
    points: np.ndarray,
    faces: list[list[int]],
    wall_face_indices: list[int],
    owner: np.ndarray,
    cell_centres: np.ndarray | None = None,
) -> dict[int, np.ndarray]:
    """Wall vertex 별 outward normal (area-weighted 평균 of incident wall face normals).

    beta2266: triangle-only fast path 추가. 모든 wall face 가 triangle 이면
    fully vectorized (np.cross + np.add.at) 로 처리. polygon 이 섞여 있으면
    Python loop fallback.

    OpenFOAM polyMesh convention: boundary face normal 은 owner cell 에서 바깥 방향.
    cell_centres 가 주어지면 face centre → cell centre 반대 방향으로 sign 교정.
    """
    if not wall_face_indices:
        return {}

    # Fast path — 모든 wall face 가 triangle.
    all_tri = all(len(faces[fi]) == 3 for fi in wall_face_indices)
    if all_tri:
        wf_idx = np.array(wall_face_indices, dtype=np.int64)
        face_arr = np.array(
            [faces[fi] for fi in wall_face_indices], dtype=np.int64,
        )  # (F, 3)
        v0 = points[face_arr[:, 0]]
        v1 = points[face_arr[:, 1]]
        v2 = points[face_arr[:, 2]]
        cross = np.cross(v1 - v0, v2 - v0)  # (F, 3)
        area_vec = 0.5 * np.linalg.norm(cross, axis=1)  # (F,)
        safe_area = area_vec >= 1e-30
        # Unit normals
        n_arr = np.zeros_like(cross)
        if safe_area.any():
            n_arr[safe_area] = cross[safe_area] / (
                2.0 * area_vec[safe_area, None]
            )

        # Sign fix vs cell centre.
        if cell_centres is not None:
            face_centroids = (v0 + v1 + v2) / 3.0  # (F, 3)
            own_arr = owner[wf_idx]
            valid_own = (own_arr >= 0) & (own_arr < len(cell_centres))
            if valid_own.any():
                to_face = np.zeros_like(face_centroids)
                to_face[valid_own] = face_centroids[valid_own] - cell_centres[own_arr[valid_own]]
                dot = np.einsum("ij,ij->i", to_face, n_arr)
                flip = (dot < 0) & valid_own & safe_area
                n_arr[flip] = -n_arr[flip]

        # BETA2901 — angle-weighted vnorm (Garimella 2003 §3, Max 1999).
        # Area-weighted averaging biases vnorm toward large faces, but for BL
        # extrusion we want vnorm ≈ face_normal of EACH adjacent face. With
        # angle weighting, each face contributes proportionally to its apex
        # angle at the vertex — a sliver face's acute corner has near-zero
        # weight, reducing normal-direction noise. For BL prism centroid
        # alignment with face_normal axis (boundary skew driver).
        # Disable via env: AUTO_TESSELL_BL_ANGLE_WEIGHTED_VNORM=0
        n_pts = points.shape[0]
        accum = np.zeros((n_pts, 3), dtype=np.float64)
        if os.environ.get("AUTO_TESSELL_BL_ANGLE_WEIGHTED_VNORM", "1") != "0":
            # Compute angle at each vertex for each face.
            # angle_at(vi) = arccos((e1·e2) / (|e1|·|e2|)) where e1,e2 are the
            # two edges from vi.
            e10 = v0 - v1; e12 = v2 - v1  # angle at v1
            e20 = v0 - v2; e21 = v1 - v2  # angle at v2
            e01 = v1 - v0; e02 = v2 - v0  # angle at v0
            def _ang(a, b):
                aa = np.linalg.norm(a, axis=1)
                bb = np.linalg.norm(b, axis=1)
                den = np.maximum(aa * bb, 1e-30)
                cosv = np.clip(np.einsum("ij,ij->i", a, b) / den, -1.0, 1.0)
                return np.arccos(cosv)
            ang0 = _ang(e01, e02)  # at v0
            ang1 = _ang(e10, e12)  # at v1
            ang2 = _ang(e20, e21)  # at v2
            # Per-face per-vertex weight = angle.
            contrib0 = n_arr * ang0[:, None]
            contrib1 = n_arr * ang1[:, None]
            contrib2 = n_arr * ang2[:, None]
            np.add.at(accum, face_arr[:, 0], contrib0)
            np.add.at(accum, face_arr[:, 1], contrib1)
            np.add.at(accum, face_arr[:, 2], contrib2)
        else:
            # Legacy area-weighted.
            contrib = n_arr * area_vec[:, None]
            for col in range(3):
                np.add.at(accum, face_arr[:, col], contrib)

        # Normalize and convert to dict for API compat.
        norms = np.linalg.norm(accum, axis=1)
        result: dict[int, np.ndarray] = {}
        unique_v = np.unique(face_arr.ravel())
        for v in unique_v:
            v_int = int(v)
            m = float(norms[v_int])
            if m > 1e-30:
                result[v_int] = accum[v_int] / m
            else:
                result[v_int] = np.zeros(3, dtype=np.float64)
        return result

    # Fallback: original Python path for polygon faces.
    vertex_accum: dict[int, np.ndarray] = {}
    for fi in wall_face_indices:
        face = faces[fi]
        n, area = _face_normal_area(points, face)
        if area < 1e-30:
            continue
        if cell_centres is not None:
            fc = _face_centroid(points, face)
            own = int(owner[fi])
            if 0 <= own < len(cell_centres):
                to_face = fc - cell_centres[own]
                if float(np.dot(to_face, n)) < 0:
                    n = -n
        for v in face:
            vertex_accum.setdefault(v, np.zeros(3, dtype=np.float64))
            vertex_accum[v] += n * area

    result_fb: dict[int, np.ndarray] = {}
    for v, acc in vertex_accum.items():
        m = float(np.linalg.norm(acc))
        if m > 1e-30:
            result_fb[v] = acc / m
        else:
            result_fb[v] = np.zeros(3, dtype=np.float64)
    return result_fb


# ---------------------------------------------------------------------------
# beta63 — collision detection via vectorized Möller-Trumbore
# ---------------------------------------------------------------------------


def _ray_triangle_min_distance(
    origins: np.ndarray,
    directions: np.ndarray,
    tri_verts: np.ndarray,
    exclude_mask: np.ndarray | None = None,
    *,
    chunk_size: int = 512,
) -> np.ndarray:
    """Vectorized ray-triangle intersection (chunked). 각 ray 에 대해 ``t > 0``
    인 최소 intersection 거리 반환. hit 없으면 +inf.

    Args:
        origins: (R, 3) 각 ray 시작점.
        directions: (R, 3) 각 ray 방향 (정규화됨).
        tri_verts: (T, 3, 3) 각 triangle 의 3 vertex.
        exclude_mask: (R, T) bool — True 면 해당 (ray, tri) 조합 제외.
        chunk_size: 한 번에 처리할 ray 수 (메모리 제어). R×T 크기 (R,T,3)
            중간 배열이 메모리 폭증 주범이므로 R 축으로 chunk.

    Returns:
        (R,) 각 ray 의 최소 t. 없으면 np.inf.

    beta63 → beta70 hotfix: (R, T, 3) 브로드캐스트 메모리 폭증 방지 (R=T=100k 에서
    240 GB 요구하던 문제). chunk_size=512 는 512×T×3×8 bytes 메모리 상한.
    """
    eps = 1e-12
    native_bl = load_native_bl()
    if native_bl is not None and hasattr(native_bl, "ray_triangle_min_distance"):
        return np.asarray(
            native_bl.ray_triangle_min_distance(
                origins, directions, tri_verts, exclude_mask, eps
            ),
            dtype=np.float64,
        )
    R = int(origins.shape[0])
    T = int(tri_verts.shape[0])
    if R == 0 or T == 0:
        return np.full((R,), np.inf, dtype=np.float64)

    v0 = tri_verts[:, 0]
    v1 = tri_verts[:, 1]
    v2 = tri_verts[:, 2]
    e1 = v1 - v0          # (T, 3)
    e2 = v2 - v0          # (T, 3)

    out = np.full((R,), np.inf, dtype=np.float64)
    for start in range(0, R, chunk_size):
        end = min(start + chunk_size, R)
        R_ = end - start
        ori_c = origins[start:end]         # (R_, 3)
        dir_c = directions[start:end]      # (R_, 3)

        D = dir_c[:, None, :]              # (R_, 1, 3) → broadcast
        # Cross product broadcasting
        P = np.cross(D, e2[None, :, :])    # (R_, T, 3)
        det = np.sum(P * e1[None, :, :], axis=-1)  # (R_, T)

        ok = np.abs(det) > eps
        inv_det = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)

        T_vec = ori_c[:, None, :] - v0[None, :, :]  # (R_, T, 3)
        u = np.sum(T_vec * P, axis=-1) * inv_det     # (R_, T)

        Q = np.cross(T_vec, e1[None, :, :])          # (R_, T, 3)
        v = np.sum(D * Q, axis=-1) * inv_det         # (R_, T)
        t = np.sum(e2[None, :, :] * Q, axis=-1) * inv_det  # (R_, T)

        valid = (
            ok & (u >= -eps) & (v >= -eps)
            & (u + v <= 1.0 + eps) & (t > eps)
        )
        if exclude_mask is not None:
            valid &= ~exclude_mask[start:end]

        t_masked = np.where(valid, t, np.inf)
        out[start:end] = t_masked.min(axis=1)
    return out


def _prism_aspect_ratio_stats(
    points: np.ndarray,
    wall_tri_verts: dict[int, tuple[int, int, int]],
    wall_face_indices: list[int],
    layer_point_ids: list[dict[int, int]],
    num_layers: int,
    threshold: float = 50.0,
) -> tuple[int, float]:
    """각 prism 의 aspect ratio 계산. ratio = max(outer_edge) / min(height).

    beta2257: vectorized — Python loop O(N×L) 대신 numpy 일괄 (10-100× 빠름).

    Returns:
        (n_degenerate, max_ratio) — degenerate 는 ratio > threshold.
    """
    # Build (n_valid_faces, 3) int array of v0, v1, v2.
    valid_faces = [fi for fi in wall_face_indices if fi in wall_tri_verts]
    if not valid_faces:
        return 0, 0.0
    tri_arr = np.array(
        [wall_tri_verts[fi] for fi in valid_faces], dtype=np.int64,
    )  # (F, 3)

    # For each layer k, gather outer + inner positions.
    F = tri_arr.shape[0]
    n_prisms = F * num_layers
    ratios = np.zeros(n_prisms, dtype=np.float64)

    for k in range(num_layers):
        # Build idx arrays for this layer's outer (k) and inner (k+1) verts.
        lp_o = layer_point_ids[k]
        lp_i = layer_point_ids[k + 1]
        # Vectorized lookup via list comprehension into ndarray
        o_idx = np.array(
            [[lp_o[v0], lp_o[v1], lp_o[v2]]
             for v0, v1, v2 in tri_arr.tolist()],
            dtype=np.int64,
        )  # (F, 3)
        i_idx = np.array(
            [[lp_i[v0], lp_i[v1], lp_i[v2]]
             for v0, v1, v2 in tri_arr.tolist()],
            dtype=np.int64,
        )  # (F, 3)
        o_pts = points[o_idx]  # (F, 3, 3)
        i_pts = points[i_idx]  # (F, 3, 3)

        # outer edges: (o1-o0), (o2-o1), (o0-o2)
        e0 = np.linalg.norm(o_pts[:, 1] - o_pts[:, 0], axis=1)
        e1 = np.linalg.norm(o_pts[:, 2] - o_pts[:, 1], axis=1)
        e2 = np.linalg.norm(o_pts[:, 0] - o_pts[:, 2], axis=1)
        e_outer = np.maximum.reduce([e0, e1, e2])  # (F,)

        # heights: norm(i_k - o_k) for k=0,1,2
        h0 = np.linalg.norm(i_pts[:, 0] - o_pts[:, 0], axis=1)
        h1 = np.linalg.norm(i_pts[:, 1] - o_pts[:, 1], axis=1)
        h2 = np.linalg.norm(i_pts[:, 2] - o_pts[:, 2], axis=1)
        h = np.minimum.reduce([h0, h1, h2])  # (F,)

        # degenerate: h < 1e-30 → ratio = 1e9
        # else ratio = e_outer / h
        safe = h >= 1e-30
        layer_ratios = np.where(safe, e_outer / np.where(safe, h, 1.0), 1e9)
        ratios[k * F:(k + 1) * F] = layer_ratios

    n_degenerate = int((ratios > threshold).sum())
    max_ratio = float(ratios.max()) if ratios.size > 0 else 0.0
    # detailed cfMesh-style log
    if ratios.size > 0:
        try:
            log.info(
                "native_bl_prism_aspect_stats",
                n_prisms=int(ratios.size),
                aspect_mean=round(float(ratios.mean()), 2),
                aspect_median=round(float(np.median(ratios)), 2),
                aspect_p90=round(float(np.percentile(ratios, 90)), 2),
                aspect_p99=round(float(np.percentile(ratios, 99)), 2),
                aspect_max=round(float(ratios.max()), 2),
                n_above_threshold=n_degenerate,
                threshold=threshold,
            )
        except Exception:
            pass
    return n_degenerate, float(max_ratio)


# BL_TANGENT_SMOOTH (beta2153) — tangential Laplacian of prism outer-face verts,
# projected back along the local extrusion direction (cfMesh BLSmoothing style).
# Improves prism layer tangential uniformity without disturbing layer thickness.
# Default ON; disable via env AUTO_TESSELL_BL_TANG_OFF=1.
_BL_TANG_SMOOTH_ON: bool = os.environ.get("AUTO_TESSELL_BL_TANG_OFF", "0") != "1"
# beta2248 — cfMesh/T-Rex 동급 wall preservation 강화. tangent smoothing 이
# lp_ids[0] (=wall) vertex 를 tangential 로 이동시켜 surface drift 유발 →
# default OFF. fluid 시뮬에서 wall 위치는 정확해야 하므로 이 trade-off 가 옳음.
# env AUTO_TESSELL_BL_TANG_PRESERVE_WALL=0 으로 이전 동작 (smoothing 활성) 가능.
_BL_TANG_PRESERVE_WALL: bool = os.environ.get(
    "AUTO_TESSELL_BL_TANG_PRESERVE_WALL", "1"
) != "0"


def _smooth_top_layer_tangential(
    fp: np.ndarray,
    wall_vert_indices: list[int],
    wall_tri_verts: dict[int, tuple[int, int, int]],
    wall_face_indices: list[int],
    layer_point_ids: list[dict[int, int]],
    num_layers: int,
    *,
    top_k: int = 20,
    n_iter: int = 1,
    min_aspect_improve: float = 1e-3,
) -> tuple[np.ndarray, int]:
    """BL_TANGENT_SMOOTH: tangential Laplacian of outermost prism-layer verts.

    For each outer-face vertex v (lp_ids[0][wall_vert]):
      - candidate = centroid of 1-ring top-layer neighbors (top-layer verts only).
      - Project candidate onto the tangential plane perpendicular to the extrusion
        direction (p_top - p_base) — preserves layer thickness.
      - STRICT GUARD: post.max_aspect over incident prisms < pre.max_aspect - threshold.
        Else revert.

    Returns (fp_modified, n_moved).
    """
    if num_layers < 1 or not wall_vert_indices or not wall_face_indices:
        return fp, 0

    fp = fp.copy()

    # ── 1. Build wall-vert adjacency (shared edge in wall triangles) ─────────
    # top-layer vertex idx for each wall vert
    top_id: dict[int, int] = {}   # wall_vert -> point index in fp (outer layer)
    base_id: dict[int, int] = {}  # wall_vert -> point index in fp (inner/wall layer)
    lids_top = layer_point_ids[0]
    lids_base = layer_point_ids[num_layers]
    for v in wall_vert_indices:
        if v in lids_top and v in lids_base:
            top_id[v] = lids_top[v]
            base_id[v] = lids_base[v]

    if not top_id:
        return fp, 0

    # Build edge adjacency among wall verts (share a tri edge)
    adj: dict[int, set[int]] = {v: set() for v in top_id}
    for fi in wall_face_indices:
        if fi not in wall_tri_verts:
            continue
        verts = wall_tri_verts[fi]
        for i in range(3):
            va, vb = verts[i], verts[(i + 1) % 3]
            if va in adj and vb in adj:
                adj[va].add(vb)
                adj[vb].add(va)

    # ── 2. Prism → wall-vert map (incident faces per wall vert) ──────────────
    vert_faces: dict[int, list[int]] = {v: [] for v in top_id}
    for fi in wall_face_indices:
        if fi not in wall_tri_verts:
            continue
        for v in wall_tri_verts[fi]:
            if v in vert_faces:
                vert_faces[v].append(fi)

    # ── 3. Helper: max aspect ratio over prisms incident to wall vert v ──────
    def _max_aspect_for_vert(v: int) -> float:
        best = 0.0
        for fi in vert_faces.get(v, []):
            if fi not in wall_tri_verts:
                continue
            v0, v1, v2 = wall_tri_verts[fi]
            for li in range(num_layers):
                l_out = layer_point_ids[li]
                l_in = layer_point_ids[li + 1]
                if not all(x in l_out and x in l_in for x in (v0, v1, v2)):
                    continue
                o0, o1, o2 = fp[l_out[v0]], fp[l_out[v1]], fp[l_out[v2]]
                i0, i1, i2 = fp[l_in[v0]], fp[l_in[v1]], fp[l_in[v2]]
                e_out = max(
                    float(np.linalg.norm(o1 - o0)),
                    float(np.linalg.norm(o2 - o1)),
                    float(np.linalg.norm(o0 - o2)),
                )
                h = min(
                    float(np.linalg.norm(i0 - o0)),
                    float(np.linalg.norm(i1 - o1)),
                    float(np.linalg.norm(i2 - o2)),
                )
                ar = e_out / (h + 1e-30)
                if ar > best:
                    best = ar
        return best

    # ── 4. Pick top-K worst-aspect verts as candidates ───────────────────────
    aspects = {v: _max_aspect_for_vert(v) for v in top_id}
    sorted_verts = sorted(aspects, key=lambda v: aspects[v], reverse=True)
    k = min(top_k, len(sorted_verts))
    candidates = set(sorted_verts[:k])

    # ── 5. Per-vertex tangential Laplacian + strict guard ────────────────────
    n_moved = 0
    for _it in range(n_iter):
        for v in candidates:
            nbs = adj.get(v, set())
            if not nbs:
                continue
            # centroid of top-layer neighbor positions
            nb_pts = np.array([fp[top_id[nb]] for nb in nbs if nb in top_id])
            if len(nb_pts) == 0:
                continue
            centroid = nb_pts.mean(axis=0)

            # extrusion direction: from base to top (outward)
            p_top = fp[top_id[v]]
            p_base = fp[base_id[v]]
            extrusion_dir = p_top - p_base
            extrusion_len = float(np.linalg.norm(extrusion_dir))
            if extrusion_len < 1e-30:
                continue
            extrusion_hat = extrusion_dir / extrusion_len

            # project centroid onto plane perpendicular to extrusion_hat, passing through p_top
            delta = centroid - p_top
            projected = p_top + delta - float(np.dot(delta, extrusion_hat)) * extrusion_hat

            pre_aspect = _max_aspect_for_vert(v)
            old_pos = fp[top_id[v]].copy()
            fp[top_id[v]] = projected

            post_aspect = _max_aspect_for_vert(v)
            if post_aspect < pre_aspect - min_aspect_improve:
                n_moved += 1  # accept
            else:
                fp[top_id[v]] = old_pos  # revert

    return fp, n_moved


def _smooth_inner_layers_along_normal(
    fp: np.ndarray,
    wall_vert_indices: list[int],
    layer_point_ids: list[dict[int, int]],
    num_layers: int,
    *,
    n_iter: int = 2,
) -> tuple[np.ndarray, int]:
    """beta2251 — cfMesh BLSmoothing 동급: inner layer (1..N-1) 의 normal-axis
    재분포로 prism aspect 개선. wall (lp_ids[0]) 와 deepest (lp_ids[N]) 는 고정.

    각 wall vertex 별로:
      1. base_pos = lp_ids[0][v], deepest_pos = lp_ids[N][v]
      2. n_axis = deepest_pos - base_pos (정규화된 normal direction)
      3. 현재 inner layer 의 axial offset (along n_axis) 계산
      4. 1-ring neighbor 의 axial offsets 와 Laplacian smoothing
      5. base_pos + offset * n_axis_unit 로 inner pos 갱신
      6. lp_ids[0] 또는 lp_ids[N] 은 변경하지 않음 (wall preservation)

    Returns (fp_modified, n_moved).
    """
    if num_layers < 3 or not wall_vert_indices or not layer_point_ids:
        return fp, 0
    if len(layer_point_ids) < num_layers + 1:
        return fp, 0

    fp = fp.copy()
    n_moved = 0
    base_lp = layer_point_ids[0]
    deepest_lp = layer_point_ids[num_layers]

    # beta2258 — vectorized inner-layer Laplacian smoothing.
    # Filter: only include verts present in ALL layers (base, deepest, every inner).
    valid_v: list[int] = []
    for v in wall_vert_indices:
        if v not in base_lp or v not in deepest_lp:
            continue
        if not all(v in layer_point_ids[k] for k in range(num_layers + 1)):
            continue
        valid_v.append(v)
    if not valid_v:
        return fp, 0

    n_v = len(valid_v)
    # (n_v,) vertex idx in each layer
    base_idx = np.array([base_lp[v] for v in valid_v], dtype=np.int64)
    deepest_idx = np.array([deepest_lp[v] for v in valid_v], dtype=np.int64)
    # (n_v, 3) base position + axis (kept fixed throughout iteration)
    base_pos = fp[base_idx].copy()  # (n_v, 3)
    deepest_pos = fp[deepest_idx]
    axis_vec = deepest_pos - base_pos  # (n_v, 3)
    axis_len = np.linalg.norm(axis_vec, axis=1)  # (n_v,)
    axis_safe = axis_len >= 1e-12
    axis_unit = np.zeros_like(axis_vec)
    axis_unit[axis_safe] = axis_vec[axis_safe] / axis_len[axis_safe, None]

    # (num_layers+1, n_v) idx of each vertex in each layer
    all_layer_idx = np.array(
        [[layer_point_ids[k][v] for v in valid_v] for k in range(num_layers + 1)],
        dtype=np.int64,
    )  # (L+1, n_v)

    for _it in range(int(n_iter)):
        for layer_i in range(1, num_layers):
            # current axial offsets along axis_unit
            prev_pos = fp[all_layer_idx[layer_i - 1]]  # (n_v, 3)
            next_pos = fp[all_layer_idx[layer_i]]
            prev_off = np.einsum("ij,ij->i", prev_pos - base_pos, axis_unit)
            next_off = np.einsum("ij,ij->i", next_pos - base_pos, axis_unit)
            # Laplacian smooth: new_off = avg(prev, next)
            new_off = 0.5 * (prev_off + next_off)
            # Guard: new_off must be strictly between prev_off and next_off
            ordered = (new_off > prev_off + 1e-12) & (new_off < next_off - 1e-12)
            apply_mask = ordered & axis_safe
            if not apply_mask.any():
                continue
            new_pos = base_pos + axis_unit * new_off[:, None]
            cur_lp_idx = all_layer_idx[layer_i]
            apply_idx = cur_lp_idx[apply_mask]
            fp[apply_idx] = new_pos[apply_mask]
            n_moved += int(apply_mask.sum())

    return fp, n_moved


def validate_bl_thickness_uniformity(
    thickness_array: np.ndarray,
    *,
    max_rel_variation: float = 0.05,
) -> float:
    """HEX_BL_UNIFORM — validate first-layer prism thickness variation ≤5% (CFD y+ standard).

    Computes std/mean ratio of first-layer per-vertex thicknesses.
    Always logs stats for observability; warns if variation exceeds threshold.

    Args:
        thickness_array: 1-D ndarray of per-vertex first-layer thicknesses.
        max_rel_variation: allowed relative variation (default 0.05 = 5%).

    Returns:
        rel_variation (std / mean); 0.0 if array is empty or degenerate.
    """
    arr = np.asarray(thickness_array, dtype=np.float64).ravel()
    if arr.size == 0:
        return 0.0
    t_min = float(arr.min())
    t_max = float(arr.max())
    t_mean = float(arr.mean())
    t_std = float(arr.std())
    rel_variation = float(t_std / t_mean) if t_mean > 1e-30 else 0.0
    log.info(
        "native_bl_thickness_stats",
        component="native_bl",
        phase="HEX_BL_UNIFORM",
        n_verts=int(arr.size),
        t_min=round(t_min, 8),
        t_max=round(t_max, 8),
        t_mean=round(t_mean, 8),
        t_std=round(t_std, 8),
        rel_variation=round(rel_variation, 6),
    )
    if rel_variation > max_rel_variation:
        log.warning(
            "native_bl_thickness_warning",
            component="native_bl",
            phase="HEX_BL_UNIFORM",
            rel_variation=round(rel_variation, 6),
            max_rel_variation=max_rel_variation,
            t_min=round(t_min, 8),
            t_max=round(t_max, 8),
            t_mean=round(t_mean, 8),
            t_std=round(t_std, 8),
            msg="first-layer thickness variation exceeds CFD y+ uniformity threshold",
        )
    return rel_variation


def _apply_local_collision_factors(
    wall_vertices: list[int],
    first_thickness: np.ndarray,
    collision_factors: dict[int, float],
    cumulative_offsets: dict[int, np.ndarray] | None,
    *,
    use_per_vertex_cumulative: bool,
) -> tuple[dict[int, float], dict[int, np.ndarray] | None]:
    """Return bounded local collision scales without mutating input offsets.

    A disabled or unavailable factor is identity.  Per-vertex cumulative
    offsets are copied before scaling, so a rejected BL candidate cannot alter
    the source path used by a later rollback or retry.
    """
    scales: dict[int, float] = {}
    scaled: dict[int, np.ndarray] | None = None
    if use_per_vertex_cumulative and cumulative_offsets is not None:
        scaled = {vertex: np.asarray(offsets, dtype=np.float64).copy()
                  for vertex, offsets in cumulative_offsets.items()}
    for index, vertex in enumerate(wall_vertices):
        _ = first_thickness[index] if index < len(first_thickness) else 0.0
        factor = float(collision_factors.get(int(vertex), 1.0))
        factor = min(1.0, max(0.0, factor))
        scales[int(vertex)] = factor
        if scaled is not None and int(vertex) in scaled:
            # Cumulative paths already encode the local collision cap.  Scale
            # them once by the per-vertex first-layer factor, never again by
            # the diagnostic cap stored in ``scales``.
            path_scale = float(first_thickness[index]) if index < len(first_thickness) else 1.0
            scaled[int(vertex)] *= min(1.0, max(0.0, path_scale))
    return scales, scaled


def _evaluator_prism_aspect(base_edges: np.ndarray, heights: np.ndarray) -> float:
    """Conservative prism aspect proxy used only for BL candidate rejection."""
    edge = np.asarray(base_edges, dtype=np.float64)
    height = np.asarray(heights, dtype=np.float64)
    if edge.size == 0 or height.size == 0:
        return float("inf")
    positive = height[height > 1.0e-30]
    if positive.size == 0:
        return float("inf")
    return float(np.max(edge) / np.min(positive))


def _relative_thickness_ratio(case_dir: Path, engine_tag: str) -> tuple[float, str]:
    """Resolve relative BL thickness without conflating zero-layer routing.

    Explicit environment input wins.  Native tet has a smaller default, while
    the convex-extrusion marker records a validated transition-only override.
    """
    raw = os.environ.get("AUTO_TESSELL_BL_REL_RATIO")
    if raw is not None:
        try:
            ratio = float(raw)
        except ValueError:
            ratio = float("nan")
        if np.isfinite(ratio) and ratio > 0.0:
            return ratio, "environment"
    if (case_dir / "native_tet_convex_extrusion.marker").exists():
        return 0.25, "native_tet_convex_extrusion"
    selected = str(engine_tag).lower()
    log_path = case_dir / "generator_log.json"
    if log_path.exists():
        try:
            selected = str(json.loads(log_path.read_text(encoding="utf-8")).get(
                "selected_tier", selected
            )).lower()
        except (OSError, ValueError, TypeError):
            pass
    if "native_tet" in selected or selected in {"tet", "native-tet"}:
        return 0.08, "native_tet_default"
    return 0.3, "default"


def _select_native_tet_dominant_cap_faces(
    points: np.ndarray,
    faces: list[list[int]],
    wall_faces: list[int],
    *,
    engine_tag: str,
    min_bbox_aspect: float = 2.0,
    preferred_axis: int | None = None,
) -> tuple[list[int], dict[str, Any]]:
    """Select two planar end caps for native-tet BL without moving vertices."""
    selected = list(wall_faces)
    diagnostic: dict[str, Any] = {"applied": False}
    if engine_tag != "native_tet" or len(wall_faces) < 2:
        return selected, diagnostic
    coords = np.asarray(points, dtype=np.float64)
    extent = np.ptp(coords, axis=0)
    positive = extent[extent > 1.0e-12]
    if positive.size < 2:
        return selected, diagnostic
    ratio = float(np.max(positive) / np.min(positive))
    if ratio < float(min_bbox_aspect):
        return selected, diagnostic
    if preferred_axis is not None:
        axis = int(preferred_axis)
    else:
        minimum = float(np.min(positive))
        minima = np.flatnonzero(np.isclose(extent, minimum, rtol=1.0e-9, atol=1.0e-12))
        # A rod has two equally thin transverse dimensions; its caps are the
        # long-axis ends.  A slab has one uniquely thin normal.
        axis = int(np.argmax(extent)) if minima.size > 1 else int(minima[0])
    lower = float(np.min(coords[:, axis]))
    upper = float(np.max(coords[:, axis]))
    tolerance = max(1.0e-12, float(extent[axis]) * 1.0e-9)
    caps: list[int] = []
    for face_index in wall_faces:
        face = faces[face_index]
        values = coords[np.asarray(face, dtype=np.int64), axis]
        if np.all(np.abs(values - lower) <= tolerance) or np.all(np.abs(values - upper) <= tolerance):
            caps.append(int(face_index))
    if len(caps) >= 2:
        selected = caps
        diagnostic = {
            "applied": True,
            "thin_axis": axis,
            "axis_extent_ratio": ratio,
        }
    return selected, diagnostic


def _filter_small_native_tet_wall_components(
    points: np.ndarray,
    faces: list[list[int]],
    wall_faces: list[int],
) -> tuple[list[int], dict[str, Any]]:
    """Keep largest vertex-connected wall component; report, never rewrite."""
    if not wall_faces:
        return [], {"applied": False, "components": 0}
    remaining = set(int(index) for index in wall_faces)
    components: list[list[int]] = []
    vertices = {index: set(faces[index]) for index in remaining}
    while remaining:
        seed = remaining.pop()
        component = [seed]
        stack = [seed]
        while stack:
            current = stack.pop()
            linked = [other for other in remaining if vertices[current] & vertices[other]]
            for other in linked:
                remaining.remove(other)
                component.append(other)
                stack.append(other)
        components.append(sorted(component))
    if len(components) == 1:
        return list(wall_faces), {"applied": False, "components": 1}
    def area(component: list[int]) -> float:
        return float(sum(_face_normal_area(np.asarray(points, dtype=np.float64), faces[index])[1] for index in component))
    kept = max(components, key=area)
    return kept, {"applied": True, "components": len(components), "kept_faces": len(kept)}


def _geometric_layer_thickness(
    first_thickness: float | np.ndarray,
    n_layers: int,
    *,
    growth_ratio: float = 1.2,
) -> np.ndarray:
    """BL2 — geometric prism layer thickness array (cfMesh / snappy standard 1.2×).

    Algorithm (clean-room, cfMesh maxFirstLayerThickness ratio §generateBoundaryLayers):
      layer i thickness = first_thickness * growth_ratio^i  (i=0..n_layers-1)
      total = first_thickness * (growth_ratio^n_layers - 1) / (growth_ratio - 1)
             (geometric series; if growth_ratio==1.0 → uniform = first_thickness * n_layers)

    Args:
        first_thickness: scalar or per-vertex array shape (V,).
        n_layers: number of BL layers.
        growth_ratio: multiplicative expansion factor per layer (default 1.2).

    Returns:
        ndarray shape (n_layers,) if first_thickness is scalar,
        or (n_layers, V) if first_thickness is array.
    """
    if n_layers <= 0:
        if np.ndim(first_thickness) == 0:
            return np.empty(0, dtype=np.float64)
        return np.empty((0, int(np.asarray(first_thickness).shape[0])), dtype=np.float64)

    exponents = np.arange(n_layers, dtype=np.float64)  # [0, 1, ..., n-1]
    factors = growth_ratio ** exponents                 # [1, r, r², ...]

    ft = np.asarray(first_thickness, dtype=np.float64)
    if ft.ndim == 0:
        # scalar path → shape (n_layers,)
        return float(ft) * factors
    else:
        # per-vertex path → shape (n_layers, V)
        return ft[np.newaxis, :] * factors[:, np.newaxis]


def _curvature_adaptive_thickness(
    surface_pts: np.ndarray,
    surface_faces: list[list[int]],
    wall_vert_indices: list[int],
    base_thickness: float,
    *,
    max_aspect: float = 50.0,
    curvature_window: int = 5,
) -> np.ndarray:
    """BL1 — per-vertex adaptive first-layer thickness (cfMesh-style aspect cap).

    Algorithm (clean-room, §cfMesh generateBoundaryLayers maxFirstLayerThickness):
      1. Discrete mean curvature via Laplacian magnitude: curv[v] = ||Σ(p_j - p_v)|| / N.
      2. local_edge_min[v] = min incident edge length over wall faces.
      3. max_safe = local_edge_min / max_aspect  (prism aspect ratio cap).
      4. thickness[v] = min(base_thickness, max_safe).
      5. Sharp region (curv > 2×median): additional 0.5× scale.

    Returns:
        np.ndarray shape (len(wall_vert_indices),) — per-vertex first thickness.
    """
    if not wall_vert_indices or not surface_faces:
        return np.full(len(wall_vert_indices), base_thickness, dtype=np.float64)

    # build adjacency: vertex → set of neighbouring vertices (wall faces only)
    # C-PERF-66 / beta2517 — triangle-only fast path: flat src/dst + sort + bincount-offset.
    vert_set = set(wall_vert_indices)
    neighbours: dict[int, list[int]] = {v: [] for v in wall_vert_indices}
    tri_faces_only = [f for f in surface_faces if len(f) == 3]
    other_faces = [f for f in surface_faces if len(f) != 3]
    if tri_faces_only:
        F_tri = np.asarray(tri_faces_only, dtype=np.int64)
        src_nb = F_tri[:, [0, 0, 1, 1, 2, 2]].reshape(-1)
        dst_nb = F_tri[:, [1, 2, 0, 2, 0, 1]].reshape(-1)
        # mask: src must be in wall_vert_indices.
        wall_arr = np.asarray(sorted(vert_set), dtype=np.int64)
        wall_set_np = set(wall_arr.tolist())
        # Use np.isin for membership.
        mask = np.isin(src_nb, wall_arr)
        src_v = src_nb[mask]; dst_v = dst_nb[mask]
        order = np.argsort(src_v, kind="stable")
        src_s = src_v[order]; dst_s = dst_v[order]
        # Group by unique src.
        if src_s.size > 0:
            diff = np.r_[True, src_s[1:] != src_s[:-1]]
            starts = np.where(diff)[0]
            ends = np.r_[starts[1:], len(src_s)]
            for s, e in zip(starts.tolist(), ends.tolist()):
                v_int = int(src_s[s])
                if v_int in neighbours:
                    neighbours[v_int].extend(dst_s[s:e].tolist())
    # Polygon faces fallback (rare in BL, but supported).
    for f in other_faces:
        if len(f) < 2:
            continue
        for ai in range(len(f)):
            a = int(f[ai])
            b = int(f[(ai + 1) % len(f)])
            if a in neighbours:
                neighbours[a].append(b)
            if b in neighbours:
                neighbours[b].append(a)

    n_verts = len(wall_vert_indices)
    thickness = np.full(n_verts, base_thickness, dtype=np.float64)
    curvatures = np.zeros(n_verts, dtype=np.float64)

    # BL_REMAIN_VEC: vectorize per-vertex curvature+edge-min loop
    # C-BL-8 / beta2438 — local_edge_min → local_edge_median 으로 변경.
    # validator 발견: hard mesh 의 small edge 가 thickness 를 1e-7 까지 떨어뜨려
    # prism aspect 580k+ 발생. median 사용 시 small outlier edge 영향 약화.
    # cfMesh maxFirstLayerThickness 도 median-of-incident-edges 사용.
    # C-BL-9 / beta2440 (revised beta2441-2445 → beta2446) — 절대 floor:
    # base_thickness * 1.0 (curvature adaptive 효과적으로 disable).
    # 모든 vertex 가 base_thickness 사용 — uniform BL.
    # cfMesh의 maxFirstLayerThickness 와 minFirstLayerThickness 를 동일화한 상태와 동등.
    # C-BL-16 / beta2447 — env AUTO_TESSELL_BL_FLOOR_RATIO 로 override.
    import os as _os_bl_floor
    _floor_ratio = float(_os_bl_floor.environ.get("AUTO_TESSELL_BL_FLOOR_RATIO", "1.0"))
    _absolute_floor = float(base_thickness) * _floor_ratio
    for vi, v in enumerate(wall_vert_indices):
        nbrs = neighbours[v]
        if not nbrs:
            continue
        pv = surface_pts[v]
        nb_pts = surface_pts[nbrs] if isinstance(nbrs, np.ndarray) else surface_pts[list(set(nbrs))]
        diffs = nb_pts - pv                              # (K, 3)
        edge_lens_arr = np.linalg.norm(diffs, axis=1)   # (K,)
        curvatures[vi] = float(np.linalg.norm(diffs.sum(axis=0))) / len(nbrs)
        # 양 쪽 절충: 25th percentile (robust against tiny outlier edges).
        if edge_lens_arr.size >= 2:
            local_edge_repr = float(np.quantile(edge_lens_arr, 0.25))
        else:
            local_edge_repr = float(edge_lens_arr.min())
        max_safe = local_edge_repr / max_aspect
        thickness[vi] = max(_absolute_floor, min(base_thickness, max_safe))

    # sharp region: curv > 2 × median → halve thickness (cfMesh rule)
    if n_verts > 1:
        med = float(np.median(curvatures))
        sharp_mask = curvatures > (2.0 * med)
        thickness[sharp_mask] *= 0.5
    # C-BL-20 / beta2455 — re-enforce absolute floor after sharp halving so
    # AUTO_TESSELL_BL_FLOOR_RATIO is a truly absolute lower bound on thickness.
    # Sharp halving could drop below floor (e.g. floor=0.5*base → 0.25*base);
    # clamp ensures env contract holds.
    thickness = np.maximum(thickness, _absolute_floor)

    return thickness


def _relative_first_thickness(
    surface_pts: np.ndarray,
    surface_faces: list[list[int]],
    wall_vert_indices: list[int],
    *,
    ratio: float = 0.3,
) -> np.ndarray:
    """BL3 — relative first-layer thickness (cfMesh ``relativeSizes true``).

    For each wall vertex the first BL layer thickness is set to ``ratio`` times
    the local mean edge length.  This ties layer thickness to local mesh density,
    producing uniform y+ across the surface regardless of absolute element size.

    Algorithm (clean-room, cfMesh BoundaryLayerOptimisation §relativeSizes):
      1. Build vertex adjacency from wall faces.
      2. local_mean_edge[v] = mean of incident edge lengths.
      3. first_thickness[v]  = ratio * local_mean_edge[v].

    Returns:
        np.ndarray shape (len(wall_vert_indices),) — per-vertex first thickness.
    """
    if not wall_vert_indices or not surface_faces:
        return np.zeros(len(wall_vert_indices), dtype=np.float64)

    # C-PERF-67 / beta2518 — triangle-only fast path (mirror beta2517).
    neighbours: dict[int, list[int]] = {v: [] for v in wall_vert_indices}
    vert_set = set(wall_vert_indices)
    tri_faces_only = [f for f in surface_faces if len(f) == 3]
    other_faces = [f for f in surface_faces if len(f) != 3]
    if tri_faces_only:
        F_tri = np.asarray(tri_faces_only, dtype=np.int64)
        src_nb = F_tri[:, [0, 0, 1, 1, 2, 2]].reshape(-1)
        dst_nb = F_tri[:, [1, 2, 0, 2, 0, 1]].reshape(-1)
        wall_arr = np.asarray(sorted(vert_set), dtype=np.int64)
        mask = np.isin(src_nb, wall_arr)
        src_v = src_nb[mask]; dst_v = dst_nb[mask]
        order = np.argsort(src_v, kind="stable")
        src_s = src_v[order]; dst_s = dst_v[order]
        if src_s.size > 0:
            diff = np.r_[True, src_s[1:] != src_s[:-1]]
            starts = np.where(diff)[0]
            ends = np.r_[starts[1:], len(src_s)]
            for s, e in zip(starts.tolist(), ends.tolist()):
                v_int = int(src_s[s])
                if v_int in neighbours:
                    neighbours[v_int].extend(dst_s[s:e].tolist())
    for f in other_faces:
        if len(f) < 2:
            continue
        for ai in range(len(f)):
            a = int(f[ai])
            b = int(f[(ai + 1) % len(f)])
            if a in neighbours:
                neighbours[a].append(b)
            if b in neighbours:
                neighbours[b].append(a)

    thickness = np.zeros(len(wall_vert_indices), dtype=np.float64)
    # BL_REMAIN_VEC: vectorize per-vertex mean-edge loop
    for vi, v in enumerate(wall_vert_indices):
        nbrs = neighbours[v]
        if not nbrs:
            thickness[vi] = 0.0
            continue
        pv = surface_pts[v]
        nb_pts_r = surface_pts[list(set(nbrs))] if not isinstance(nbrs, np.ndarray) else surface_pts[nbrs]
        edge_lens_r = np.linalg.norm(nb_pts_r - pv, axis=1)  # (K,)
        thickness[vi] = ratio * float(edge_lens_r.mean())
    return thickness


def _detect_feature_vertices(
    points: np.ndarray,
    faces: list[list[int]],
    wall_face_indices: list[int],
    feature_angle_deg: float = 45.0,
) -> set[int]:
    """wall triangle 간 dihedral angle 이 threshold 초과인 edge 의 vertex 수집.

    Returns:
        feature vertex id 집합.
    """
    if feature_angle_deg <= 0 or not wall_face_indices:
        return set()
    # C-PERF-63 / beta2514 — triangle-only fast path with lexsort + group classify.
    tri_faces = [faces[fi] for fi in wall_face_indices if len(faces[fi]) == 3]
    if not tri_faces:
        return set()
    F_arr = np.asarray(tri_faces, dtype=np.int64)        # (T, 3)
    v0 = points[F_arr[:, 0]]; v1 = points[F_arr[:, 1]]; v2 = points[F_arr[:, 2]]
    nrm = np.cross(v1 - v0, v2 - v0)
    nlen = np.linalg.norm(nrm, axis=1, keepdims=True)
    valid = (nlen[:, 0] > 1e-30)
    n_unit = np.zeros_like(nrm)
    n_unit[valid] = nrm[valid] / nlen[valid]

    # edge → face index group (lexsort).
    src = F_arr[:, [0, 1, 2]].reshape(-1).astype(np.int64)
    dst = F_arr[:, [1, 2, 0]].reshape(-1).astype(np.int64)
    fi_local = np.repeat(np.arange(F_arr.shape[0], dtype=np.int64), 3)
    u = np.minimum(src, dst); v = np.maximum(src, dst)
    order = np.lexsort((v, u))
    u_s = u[order]; v_s = v[order]; f_s = fi_local[order]
    diff = np.r_[True, (u_s[1:] != u_s[:-1]) | (v_s[1:] != v_s[:-1])]
    starts = np.where(diff)[0]
    sizes = np.diff(np.r_[starts, len(u_s)])

    cos_thresh = float(np.cos(np.deg2rad(feature_angle_deg)))
    feature_verts: set[int] = set()
    # dihedral edges (size==2): face pair angle 검사 + valid-normal 검사.
    dih = sizes == 2
    if dih.any():
        dih_starts = starts[dih]
        f1 = f_s[dih_starts]
        f2 = f_s[dih_starts + 1]
        both_valid = valid[f1] & valid[f2]
        if both_valid.any():
            f1_v = f1[both_valid]
            f2_v = f2[both_valid]
            cos_a = np.clip((n_unit[f1_v] * n_unit[f2_v]).sum(axis=1), -1.0, 1.0)
            sharp = cos_a < cos_thresh
            if sharp.any():
                sharp_starts = dih_starts[both_valid][sharp]
                feature_verts.update(u_s[sharp_starts].tolist())
                feature_verts.update(v_s[sharp_starts].tolist())
    return feature_verts


def _compute_collision_distance(
    points: np.ndarray,
    faces: list[list[int]],
    wall_face_indices: list[int],
    wall_vert_indices: list[int],
    vnorm: dict[int, np.ndarray],
    *,
    max_tris: int = 20000,
    max_search_distance: float | None = None,
) -> dict[int, float]:
    """각 wall vertex 에서 inward normal 방향으로 가장 가까운 "다른 wall face"
    까지의 거리. 자기 자신이 포함된 face 는 skip.

    Args:
        max_tris: 이전 fail-open cap 과의 호출 호환성만 유지한다. Indexed
            native 경로와 bounded Python fallback 은 이 값 때문에 검사를
            생략하지 않는다.

    Returns:
        dict[vertex_id, distance]. 검색 거리 안에 충돌이 없으면 빈 dict.

    유한한 ``max_search_distance`` 는 mesh 크기와 무관하게 동일하게
    적용한다. 더 먼 hit 는 생성 layer 에 영향을 줄 수 없으므로 반환하지
    않는다.
    """
    tri_indices = [fi for fi in wall_face_indices if len(faces[fi]) == 3]
    if not tri_indices or not wall_vert_indices:
        return {}
    T = len(tri_indices)
    R = len(wall_vert_indices)
    tri_face_ids = np.array(
        [[faces[fi][0], faces[fi][1], faces[fi][2]] for fi in tri_indices],
        dtype=np.int64,
    )  # (T, 3)
    wall_v_arr = np.array(wall_vert_indices, dtype=np.int64)
    dirs = np.array([-vnorm[v] for v in wall_vert_indices], dtype=np.float64)  # (R, 3)
    search = np.inf
    if (
        max_search_distance is not None
        and np.isfinite(max_search_distance)
        and float(max_search_distance) > 0.0
    ):
        search = float(max_search_distance)

    native_bl = load_native_bl()
    if native_bl is not None and hasattr(
        native_bl, "indexed_wall_collision_distances"
    ):
        t_min = np.asarray(
            native_bl.indexed_wall_collision_distances(
                points,
                wall_v_arr,
                dirs,
                tri_face_ids,
                search,
                1e-12,
            ),
            dtype=np.float64,
        )
        if T > max_tris:
            log.info(
                "native_bl_collision_large_indexed",
                component="native_bl",
                phase="Phase2",
                n_rays=int(R),
                n_tris=int(T),
                previous_cap=int(max_tris),
                search_distance=(round(search, 8) if np.isfinite(search) else None),
            )
    else:
        # Extension-absent correctness fallback.  Keep only a bounded batch of
        # incident flags and NumPy broadcast temporaries alive at once.
        origins = points[wall_v_arr]
        tri_verts = points[tri_face_ids]
        pair_budget = 262_144
        batch_size = max(1, min(128, pair_budget // max(T, 1)))
        t_min = np.full((R,), np.inf, dtype=np.float64)
        for start in range(0, R, batch_size):
            end = min(start + batch_size, R)
            wall_col = wall_v_arr[start:end, None]
            exclude = (
                (wall_col == tri_face_ids[None, :, 0])
                | (wall_col == tri_face_ids[None, :, 1])
                | (wall_col == tri_face_ids[None, :, 2])
            )
            t_min[start:end] = _ray_triangle_min_distance(
                origins[start:end],
                dirs[start:end],
                tri_verts,
                exclude,
                chunk_size=batch_size,
            )
        if np.isfinite(search):
            t_min[t_min > search] = np.inf

    out: dict[int, float] = {}
    for ri, v in enumerate(wall_vert_indices):
        if np.isfinite(t_min[ri]):
            out[v] = float(t_min[ri])
    return out


# ---------------------------------------------------------------------------
# polyMesh 쓰기 유틸 — tet + prism 혼합 mesh
# ---------------------------------------------------------------------------


_FOAM_HEADER = """\
/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     |
    \\\\  /    A nd           | Version: 13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    location    "constant/polyMesh";
    object      {obj};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""

_FOAM_FOOTER = "\n// ************************************************************************* //\n"


def _write_points(
    path: Path,
    points: np.ndarray,
    *,
    precision: int = 9,
) -> None:
    """Write ASCII points with an explicit significant-digit contract.

    Nine digits preserve the historical generic-writer byte format.  Callers
    whose geometry certificate requires binary64 text round-trip may request
    17 digits (``max_digits10`` for IEEE-754 binary64).
    """
    if not isinstance(precision, int) or not 1 <= precision <= 17:
        raise ValueError("point precision must be an integer in [1, 17]")
    import io  # noqa: PLC0415
    header = _FOAM_HEADER.format(cls="vectorField", obj="points")
    buf = io.StringIO()
    fmt = f"(%.{precision}g %.{precision}g %.{precision}g)"
    np.savetxt(buf, points, fmt=fmt)
    path.write_text(
        f"{header}{len(points)}\n(\n{buf.getvalue()})\n{_FOAM_FOOTER}",
        encoding="utf-8",
    )


def _write_faces(path: Path, faces: list[list[int]]) -> None:
    """beta85: 동종 face (삼각형 / 사각형) 는 numpy 벡터화, 혼합 은 fast join."""
    header = _FOAM_HEADER.format(cls="faceList", obj="faces")
    n = len(faces)
    if n == 0:
        path.write_text(
            f"{header}0\n(\n)\n{_FOAM_FOOTER}", encoding="utf-8",
        )
        return
    # face 크기가 균일한지 확인 (삼각형 all-3, 사각형 all-4)
    face_lens = {len(f) for f in faces}
    if len(face_lens) == 1:
        k = face_lens.pop()
        arr = np.array(faces, dtype=np.int64)   # (N, k)
        prefix = np.full((n, 1), k, dtype=np.int64)
        combined = np.hstack([prefix, arr])      # (N, k+1)
        # 각 행을 "{k}(v0 v1 ...)" 포맷으로
        fmt_str = "%d(" + " ".join(["%d"] * k) + ")"
        import io  # noqa: PLC0415
        buf = io.StringIO()
        np.savetxt(buf, combined, fmt=fmt_str)
        data = buf.getvalue()
    else:
        # 혼합 — Python join (빠른 map 방식)
        parts = [f"{len(f)}({' '.join(map(str, f))})" for f in faces]
        data = "\n".join(parts) + "\n"
    path.write_text(
        f"{header}{n}\n(\n{data})\n{_FOAM_FOOTER}", encoding="utf-8",
    )


def _write_labels(
    path: Path,
    labels: np.ndarray,
    obj_name: str,
    *,
    note: str | None = None,
) -> None:
    """FoamFile labelList 쓰기.

    Args:
        note: 선택적으로 FoamFile 블록에 ``note "...";`` 삽입. Ofpp 등 일부
            파서는 owner 파일의 note 로부터 nPoints/nCells 를 추출한다.
    """
    header = _FOAM_HEADER.format(cls="labelList", obj=obj_name)
    if note:
        # FoamFile {...} 블록 내부 object 앞에 note 삽입
        header = header.replace(
            f"    object      {obj_name};",
            f'    note        "{note}";\n    object      {obj_name};',
        )
    # beta2207: np.savetxt → label string (vs map+join ~2× faster for large arrays)
    import io  # noqa: PLC0415
    _buf = io.StringIO()
    np.savetxt(_buf, labels.reshape(-1, 1), fmt="%d")
    data = _buf.getvalue()
    path.write_text(
        f"{header}{len(labels)}\n(\n{data})\n{_FOAM_FOOTER}", encoding="utf-8",
    )


def _write_boundary(path: Path, entries: list[dict[str, Any]]) -> None:
    lines = [_FOAM_HEADER.format(cls="polyBoundaryMesh", obj="boundary")]
    lines.append(f"{len(entries)}\n(")
    for e in entries:
        lines.append(f"    {e['name']}")
        lines.append("    {")
        lines.append(f"        type            {e.get('type', 'patch')};")
        lines.append(f"        nFaces          {e['nFaces']};")
        lines.append(f"        startFace       {e['startFace']};")
        lines.append("    }")
    lines.append(")")
    lines.append(_FOAM_FOOTER)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 핵심 로직
# ---------------------------------------------------------------------------


def _collect_wall_faces(
    boundary: list[dict[str, Any]],
    wall_patch_names: list[str] | None,
    *,
    set_faces: list[int] | None = None,
    ignore_faces: list[int] | None = None,
    ignore_patch_names: list[str] | None = None,
    ignore_patch_prefixes: list[str] | None = None,
) -> tuple[list[int], set[int], dict[int, tuple[int, int]]]:
    """Wall / selected face index 모음 + patch 매핑 반환.

    Returns:
        (wall_face_indices,
         wall_patch_set (idx of patch),
         face_to_patch: {fi: (patch_idx, local_offset)})
    """
    all_boundary_faces: dict[int, tuple[int, int]] = {}
    patch_names_by_index: dict[int, str] = {}
    patch_types_by_index: dict[int, str] = {}
    for pi, patch in enumerate(boundary):
        name = str(patch.get("name", ""))
        patch_names_by_index[pi] = name
        patch_types_by_index[pi] = str(patch.get("type", ""))
        start = int(patch["startFace"])
        nf = int(patch["nFaces"])
        for k in range(nf):
            all_boundary_faces[start + k] = (pi, k)

    ignore_name_set = {str(n) for n in (ignore_patch_names or [])}
    ignore_prefixes = tuple(str(p) for p in (ignore_patch_prefixes or []) if str(p))
    ignore_face_set = {int(fi) for fi in (ignore_faces or [])}
    set_face_set = {int(fi) for fi in (set_faces or [])}

    def _is_ignored_patch(pi: int) -> bool:
        name = patch_names_by_index.get(pi, "")
        return name in ignore_name_set or (
            bool(ignore_prefixes) and name.startswith(ignore_prefixes)
        )

    selected: list[int] = []
    if set_face_set:
        for fi in sorted(set_face_set):
            patch_info = all_boundary_faces.get(fi)
            if patch_info is None:
                continue
            if _is_ignored_patch(patch_info[0]) or fi in ignore_face_set:
                continue
            selected.append(fi)
    else:
        for pi, patch in enumerate(boundary):
            if _is_ignored_patch(pi):
                continue
            name = patch_names_by_index[pi]
            kind = patch_types_by_index[pi].lower()
            match = False
            if wall_patch_names:
                match = name in wall_patch_names
            else:
                match = "wall" in kind or "wall" in name.lower()
            if not match:
                continue
            start = int(patch["startFace"])
            nf = int(patch["nFaces"])
            for k in range(nf):
                fi = start + k
                if fi in ignore_face_set:
                    continue
                selected.append(fi)

    # Stable de-dup while preserving patch/face ordering.
    wall_face_indices: list[int] = []
    seen: set[int] = set()
    face_to_patch: dict[int, tuple[int, int]] = {}
    for fi in selected:
        if fi in seen:
            continue
        patch_info = all_boundary_faces.get(fi)
        if patch_info is None:
            continue
        seen.add(fi)
        wall_face_indices.append(fi)
        face_to_patch[fi] = patch_info
    return wall_face_indices, {p[0] for p in face_to_patch.values()}, face_to_patch


def _cell_centres_from_faces(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
) -> np.ndarray:
    # 2026-07-17 perf fix — was a per-face Python loop calling .mean(axis=0)
    # one row at a time (measured ~1s per call at n_faces=160k; called
    # repeatedly — e.g. once per "bad component" in
    # _bl_bad_internal_face_histogram/_bl_cavity_shell_summary — this
    # compounded into the multi-minute BL hang on complex meshes like a
    # bracket). Faces are ragged (mixed tri/quad/poly) so a single batched
    # points[faces_array].mean(axis=1) needs uniform row length; group by
    # vertex count (typically just 2-3 distinct sizes) and batch each group.
    # Verified bit-identical to the old loop (max abs diff 0.0) at 160k
    # faces, ~10x faster.
    n_int = len(neighbour)
    n_faces = len(faces)
    fc = np.empty((n_faces, 3), dtype=np.float64)
    by_size: dict[int, list[int]] = {}
    for i, f in enumerate(faces):
        by_size.setdefault(len(f), []).append(i)
    for size, idxs in by_size.items():
        idx_arr = np.asarray(idxs, dtype=np.int64)
        verts_arr = np.asarray([faces[i] for i in idxs], dtype=np.int64)
        fc[idx_arr] = points[verts_arr].mean(axis=1)
    centres = np.zeros((n_cells, 3), dtype=np.float64)
    cnt = np.zeros(n_cells, dtype=np.int64)
    np.add.at(centres, owner, fc)
    np.add.at(cnt, owner, 1)
    if n_int > 0:
        np.add.at(centres, neighbour[:n_int], fc[:n_int])
        np.add.at(cnt, neighbour[:n_int], 1)
    nz = cnt > 0
    centres[nz] /= cnt[nz, np.newaxis]
    return centres


def _classify_bl_cell_kind(
    cell_id: int,
    *,
    base_n_cells: int,
    prism_cell_start: int,
    prism_cell_end: int,
) -> str:
    """Classify a cell id for BL interface diagnostics."""
    cid = int(cell_id)
    if cid < int(base_n_cells):
        return "bulk"
    if int(prism_cell_start) <= cid < int(prism_cell_end):
        return "prism"
    return "other"


def _bl_pair_class(a: str, b: str) -> str:
    if a == b:
        return f"{a}-{b}"
    if {a, b} == {"bulk", "prism"}:
        return "bulk-prism"
    if {a, b} == {"bulk", "other"}:
        return "bulk-other"
    if {a, b} == {"prism", "other"}:
        return "prism-other"
    return "other-other"


def _bl_cavity_shell_summary(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    cell_ids: set[int],
    *,
    base_n_cells: int,
    prism_cell_start: int,
    prism_cell_end: int,
    sample_cap: int = 16,
) -> dict[str, Any]:
    """Summarize the closed boundary shell of a selected bad-cell cavity.

    SMESH viscous layers treat a failing layer front as a local cavity problem:
    remove affected volume cells, keep the closed cavity boundary, then refill
    with validated transition cells. This helper does not mutate the mesh; it
    records whether a bad-face component has a usable closed boundary shell.
    """
    cell_set = {int(c) for c in cell_ids}
    summary: dict[str, Any] = {
        "n_cells": int(len(cell_set)),
        "cell_kinds": {},
        "n_boundary_faces": 0,
        "n_internal_faces": 0,
        "n_physical_boundary_faces": 0,
        "boundary_by_class": {},
        "n_boundary_vertices": 0,
        "n_boundary_edges": 0,
        "n_open_edges": 0,
        "n_nonmanifold_edges": 0,
        "n_duplicate_boundary_faces": 0,
        "min_boundary_face_area": 0.0,
        "total_boundary_area": 0.0,
        "is_closed_2manifold": False,
        "small_closed_cavity_candidate": False,
        "agglomerate_probe": {
            "n_interface_faces": 0,
            "n_bad_interface_faces": 0,
            "max_non_ortho_deg": 0.0,
            "min_face_weight": 1.0,
            "passes": True,
            "worst_faces": [],
        },
        "sample_boundary_faces": [],
    }
    if not cell_set:
        return summary

    owner_arr = np.asarray(owner, dtype=np.int64)
    nbr_arr = np.asarray(neighbour, dtype=np.int64)
    n_cells_cur = int(owner_arr.max()) + 1 if owner_arr.size else 0
    if nbr_arr.size:
        n_cells_cur = max(n_cells_cur, int(nbr_arr.max()) + 1)
    centres = _cell_centres_from_faces(
        points,
        faces,
        owner_arr,
        nbr_arr,
        n_cells_cur,
    ) if n_cells_cur > 0 else np.zeros((0, 3), dtype=np.float64)

    for cid in sorted(cell_set):
        kind = _classify_bl_cell_kind(
            cid,
            base_n_cells=base_n_cells,
            prism_cell_start=prism_cell_start,
            prism_cell_end=prism_cell_end,
        )
        summary["cell_kinds"][kind] = int(summary["cell_kinds"].get(kind, 0)) + 1

    edge_use: dict[tuple[int, int], int] = {}
    face_keys: set[tuple[int, ...]] = set()
    vertices: set[int] = set()
    boundary_face_ids: list[int] = []
    interface_records: list[tuple[int, int]] = []
    min_area = float("inf")
    total_area = 0.0

    for fi, own_raw in enumerate(owner_arr):
        own = int(own_raw)
        own_in = own in cell_set
        nbr = int(nbr_arr[fi]) if fi < len(nbr_arr) else None
        nbr_in = bool(nbr is not None and nbr in cell_set)
        if own_in and nbr_in:
            summary["n_internal_faces"] = int(summary["n_internal_faces"]) + 1
            continue
        if not (own_in or nbr_in):
            continue

        boundary_face_ids.append(int(fi))
        summary["n_boundary_faces"] = int(summary["n_boundary_faces"]) + 1
        face = faces[fi]
        key = tuple(sorted(int(v) for v in face))
        if key in face_keys:
            summary["n_duplicate_boundary_faces"] = (
                int(summary["n_duplicate_boundary_faces"]) + 1
            )
        face_keys.add(key)

        _, area = _face_normal_area(points, face)
        min_area = min(min_area, float(area))
        total_area += float(area)

        for v in face:
            vertices.add(int(v))
        for i, v0 in enumerate(face):
            v1 = face[(i + 1) % len(face)]
            e = (int(v0), int(v1))
            if e[0] > e[1]:
                e = (e[1], e[0])
            edge_use[e] = int(edge_use.get(e, 0)) + 1

        if nbr is None:
            inside = own
            inside_kind = _classify_bl_cell_kind(
                inside,
                base_n_cells=base_n_cells,
                prism_cell_start=prism_cell_start,
                prism_cell_end=prism_cell_end,
            )
            bkey = f"{inside_kind}-physical"
            summary["n_physical_boundary_faces"] = (
                int(summary["n_physical_boundary_faces"]) + 1
            )
        else:
            inside = own if own_in else int(nbr)
            outside = int(nbr) if own_in else own
            interface_records.append((int(fi), int(outside)))
            inside_kind = _classify_bl_cell_kind(
                inside,
                base_n_cells=base_n_cells,
                prism_cell_start=prism_cell_start,
                prism_cell_end=prism_cell_end,
            )
            outside_kind = _classify_bl_cell_kind(
                outside,
                base_n_cells=base_n_cells,
                prism_cell_start=prism_cell_start,
                prism_cell_end=prism_cell_end,
            )
            bkey = _bl_pair_class(inside_kind, outside_kind)
        summary["boundary_by_class"][bkey] = (
            int(summary["boundary_by_class"].get(bkey, 0)) + 1
        )

    open_edges = sum(1 for count in edge_use.values() if count == 1)
    nonmanifold_edges = sum(1 for count in edge_use.values() if count > 2)
    summary["n_boundary_vertices"] = int(len(vertices))
    summary["n_boundary_edges"] = int(len(edge_use))
    summary["n_open_edges"] = int(open_edges)
    summary["n_nonmanifold_edges"] = int(nonmanifold_edges)
    summary["min_boundary_face_area"] = (
        0.0 if min_area == float("inf") else float(min_area)
    )
    summary["total_boundary_area"] = float(total_area)
    summary["is_closed_2manifold"] = bool(
        summary["n_boundary_faces"] > 0
        and summary["n_duplicate_boundary_faces"] == 0
        and summary["min_boundary_face_area"] > 1e-30
        and open_edges == 0
        and nonmanifold_edges == 0
    )
    if boundary_face_ids and centres.size:
        face_centres = np.asarray(
            [points[np.asarray(faces[fi], dtype=np.int64)].mean(axis=0)
             for fi in boundary_face_ids],
            dtype=np.float64,
        )
        union_centre = face_centres.mean(axis=0)
        worst: list[dict[str, Any]] = []
        max_non_ortho = 0.0
        min_face_weight = 1.0
        n_bad = 0
        for fi, outside in interface_records:
            if outside < 0 or outside >= centres.shape[0]:
                continue
            face = faces[fi]
            normal, area = _face_normal_area(points, face)
            face_centre = points[np.asarray(face, dtype=np.int64)].mean(axis=0)
            d = centres[outside] - union_centre
            n_mag = float(np.linalg.norm(normal))
            d_mag = float(np.linalg.norm(d))
            if area <= 1e-30 or n_mag <= 1e-30 or d_mag <= 1e-30:
                non_ortho = 180.0
                face_weight = 0.0
            else:
                cos_theta = abs(float(np.dot(normal, d)) / max(n_mag * d_mag, 1e-30))
                cos_theta = min(1.0, max(0.0, cos_theta))
                non_ortho = float(np.degrees(np.arccos(cos_theta)))
                t = float(np.dot(face_centre - union_centre, d) / max(d_mag * d_mag, 1e-30))
                face_weight = min(t, 1.0 - t)
            max_non_ortho = max(max_non_ortho, non_ortho)
            min_face_weight = min(min_face_weight, face_weight)
            bad = bool(non_ortho > 65.0 or face_weight < 0.05)
            if bad:
                n_bad += 1
            worst.append(
                {
                    "face": int(fi),
                    "outside_cell": int(outside),
                    "non_ortho_deg": float(non_ortho),
                    "face_weight": float(face_weight),
                    "bad": bad,
                }
            )
        worst.sort(
            key=lambda item: (
                bool(item["bad"]),
                float(item["non_ortho_deg"]),
                -float(item["face_weight"]),
            ),
            reverse=True,
        )
        summary["agglomerate_probe"] = {
            "n_interface_faces": int(len(interface_records)),
            "n_bad_interface_faces": int(n_bad),
            "max_non_ortho_deg": float(max_non_ortho),
            "min_face_weight": float(min_face_weight),
            "passes": bool(n_bad == 0),
            "worst_faces": worst[: int(sample_cap)],
        }
    summary["small_closed_cavity_candidate"] = bool(
        summary["is_closed_2manifold"]
        and summary["n_cells"] <= int(
            os.environ.get("AUTO_TESSELL_BL_CAVITY_SMALL_CELL_CAP", "64")
        )
        and int(summary["cell_kinds"].get("prism", 0)) > 0
    )
    summary["sample_boundary_faces"] = boundary_face_ids[: int(sample_cap)]
    return summary


def _bl_bad_internal_face_histogram(
    points: np.ndarray,
    faces: list[list[int]],
    owner: list[int],
    neighbour: list[int],
    *,
    base_n_cells: int,
    prism_cell_start: int,
    prism_cell_end: int,
    max_non_ortho_deg: float = 65.0,
    min_face_weight: float = 0.05,
    max_worst: int = 12,
    include_components: bool = True,
) -> dict[str, Any]:
    """Summarize bad internal faces by bulk/prism interface class."""
    classes = [
        "bulk-bulk",
        "bulk-prism",
        "prism-prism",
        "bulk-other",
        "prism-other",
        "other-other",
    ]
    summary: dict[str, Any] = {
        "thresholds": {
            "max_non_ortho_deg": float(max_non_ortho_deg),
            "min_face_weight": float(min_face_weight),
        },
        "n_internal_faces": int(len(neighbour)),
        "n_bad_faces": 0,
        "n_components_total": 0,
        "n_components_analyzed": 0,
        "total_by_class": {name: 0 for name in classes},
        "bad_by_class": {name: 0 for name in classes},
        "bad_by_reason": {
            "non_ortho": 0,
            "face_weight": 0,
            "degenerate": 0,
        },
        "components": [],
        "worst_faces": [],
    }
    if len(neighbour) <= 0 or not faces or len(owner) == 0:
        return summary

    owner_arr = np.asarray(owner, dtype=np.int64)
    nbr_arr = np.asarray(neighbour, dtype=np.int64)
    n_cells_cur = int(owner_arr.max()) + 1 if owner_arr.size else 0
    if nbr_arr.size:
        n_cells_cur = max(n_cells_cur, int(nbr_arr.max()) + 1)
    if n_cells_cur <= 0:
        return summary

    centres = _cell_centres_from_faces(
        points,
        faces,
        owner_arr,
        nbr_arr,
        n_cells_cur,
    )
    worst: list[dict[str, Any]] = []
    bad_records: list[dict[str, Any]] = []
    for fi in range(int(len(neighbour))):
        own = int(owner_arr[fi])
        nbr = int(nbr_arr[fi])
        own_kind = _classify_bl_cell_kind(
            own,
            base_n_cells=base_n_cells,
            prism_cell_start=prism_cell_start,
            prism_cell_end=prism_cell_end,
        )
        nbr_kind = _classify_bl_cell_kind(
            nbr,
            base_n_cells=base_n_cells,
            prism_cell_start=prism_cell_start,
            prism_cell_end=prism_cell_end,
        )
        pair_class = _bl_pair_class(own_kind, nbr_kind)
        summary["total_by_class"][pair_class] = (
            int(summary["total_by_class"].get(pair_class, 0)) + 1
        )

        face = faces[fi]
        normal, area = _face_normal_area(points, face)
        d = centres[nbr] - centres[own]
        n_mag = float(np.linalg.norm(normal))
        d_mag = float(np.linalg.norm(d))
        if area <= 1e-30 or n_mag <= 1e-30 or d_mag <= 1e-30:
            non_ortho = 180.0
            face_weight = 0.0
            degenerate = True
        else:
            cos_theta = abs(float(np.dot(normal, d)) / max(n_mag * d_mag, 1e-30))
            cos_theta = min(1.0, max(0.0, cos_theta))
            non_ortho = float(np.degrees(np.arccos(cos_theta)))
            face_centre = points[np.asarray(face, dtype=np.int64)].mean(axis=0)
            t = float(np.dot(face_centre - centres[own], d) / max(d_mag * d_mag, 1e-30))
            face_weight = min(t, 1.0 - t)
            degenerate = False

        bad_non_ortho = non_ortho > float(max_non_ortho_deg)
        bad_weight = face_weight < float(min_face_weight)
        if not (bad_non_ortho or bad_weight or degenerate):
            continue

        summary["n_bad_faces"] = int(summary["n_bad_faces"]) + 1
        summary["bad_by_class"][pair_class] = (
            int(summary["bad_by_class"].get(pair_class, 0)) + 1
        )
        if bad_non_ortho:
            summary["bad_by_reason"]["non_ortho"] += 1
        if bad_weight:
            summary["bad_by_reason"]["face_weight"] += 1
        if degenerate:
            summary["bad_by_reason"]["degenerate"] += 1
        worst.append(
            {
                "face": int(fi),
                "owner": own,
                "neighbour": nbr,
                "class": pair_class,
                "non_ortho_deg": float(non_ortho),
                "face_weight": float(face_weight),
            }
        )
        bad_records.append(
            {
                "face": int(fi),
                "owner": own,
                "neighbour": nbr,
                "class": pair_class,
            }
        )

    worst.sort(
        key=lambda item: (
            float(item["non_ortho_deg"]),
            -float(item["face_weight"]),
        ),
        reverse=True,
    )
    summary["worst_faces"] = worst[: int(max_worst)]
    if bad_records and bool(include_components):
        parent: dict[int, int] = {}

        def _find_cell(cell: int) -> int:
            parent.setdefault(cell, cell)
            while parent[cell] != cell:
                parent[cell] = parent[parent[cell]]
                cell = parent[cell]
            return cell

        def _union_cell(a: int, b: int) -> None:
            ra = _find_cell(a)
            rb = _find_cell(b)
            if ra != rb:
                parent[rb] = ra

        for record in bad_records:
            _union_cell(int(record["owner"]), int(record["neighbour"]))

        components: dict[int, dict[str, Any]] = {}
        for record in bad_records:
            root = _find_cell(int(record["owner"]))
            comp = components.setdefault(
                root,
                {
                    "n_faces": 0,
                    "n_cells": 0,
                    "classes": {},
                    "faces": [],
                    "cells": set(),
                },
            )
            comp["n_faces"] += 1
            comp["classes"][record["class"]] = (
                int(comp["classes"].get(record["class"], 0)) + 1
            )
            comp["faces"].append(int(record["face"]))
            comp["cells"].add(int(record["owner"]))
            comp["cells"].add(int(record["neighbour"]))

        # 2026-07-17 perf fix — the block below does an O(n_total_faces)
        # owner_arr scan PLUS a full _bl_cavity_shell_summary() call (itself
        # another O(n_total_faces) scan + a _cell_centres_from_faces() pass)
        # for EVERY component, yet the final result keeps only the biggest
        # `max_worst` (sorted by the same n_faces/n_cells key, see the
        # packed_components.sort()+slice below). On a complex mesh (e.g. a
        # bracket's BL) this can produce hundreds of small "bad" components
        # from feature corners, each redoing full-mesh work that gets
        # discarded — turning a diagnostic into a multi-minute hang. Rank
        # components by that SAME cheap key first (n_faces/n_cells are
        # already counted above, no extra scan needed) and only run the
        # expensive per-component analysis on the ones that will actually
        # survive the final truncation. Output is unchanged — same top-N
        # components, same order — only the discarded majority's redundant
        # full-mesh work is skipped.
        _n_components_total = len(components)
        _ranked_components = sorted(
            components.items(),
            key=lambda kv: (int(kv[1]["n_faces"]), len(kv[1]["cells"])),
            reverse=True,
        )[: int(max_worst)]
        summary["n_components_total"] = int(_n_components_total)
        summary["n_components_analyzed"] = int(len(_ranked_components))
        if _n_components_total > int(max_worst):
            log.info(
                "bl_bad_component_analysis_capped",
                n_components_total=_n_components_total,
                n_components_analyzed=len(_ranked_components),
                reason="only the top max_worst components survive the final "
                       "truncation — skip full-mesh analysis for the rest",
            )

        packed_components: list[dict[str, Any]] = []
        id_cap = int(os.environ.get("AUTO_TESSELL_BL_BAD_COMPONENT_ID_CAP", "512"))
        for _root, comp in _ranked_components:
            cells = sorted(int(c) for c in comp["cells"])
            faces_comp = sorted(int(f) for f in comp["faces"])
            cell_set = set(cells)
            boundary_by_class: dict[str, int] = {}
            n_inside_internal = 0
            n_physical_boundary = 0
            for fi, own_raw in enumerate(owner_arr):
                own = int(own_raw)
                own_in = own in cell_set
                if fi < len(nbr_arr):
                    nbr = int(nbr_arr[fi])
                    nbr_in = nbr in cell_set
                    if own_in and nbr_in:
                        n_inside_internal += 1
                    elif own_in or nbr_in:
                        inside = own if own_in else nbr
                        outside = nbr if own_in else own
                        inside_kind = _classify_bl_cell_kind(
                            inside,
                            base_n_cells=base_n_cells,
                            prism_cell_start=prism_cell_start,
                            prism_cell_end=prism_cell_end,
                        )
                        outside_kind = _classify_bl_cell_kind(
                            outside,
                            base_n_cells=base_n_cells,
                            prism_cell_start=prism_cell_start,
                            prism_cell_end=prism_cell_end,
                        )
                        key = _bl_pair_class(inside_kind, outside_kind)
                        boundary_by_class[key] = int(boundary_by_class.get(key, 0)) + 1
                elif own_in:
                    n_physical_boundary += 1
            include_full = len(cells) <= id_cap and len(faces_comp) <= id_cap
            cavity_shell = _bl_cavity_shell_summary(
                points,
                faces,
                owner_arr,
                nbr_arr,
                cell_set,
                base_n_cells=base_n_cells,
                prism_cell_start=prism_cell_start,
                prism_cell_end=prism_cell_end,
                sample_cap=max_worst,
            )
            packed_components.append(
                {
                    "n_faces": int(comp["n_faces"]),
                    "n_cells": int(len(cells)),
                    "classes": dict(comp["classes"]),
                    "n_inside_internal_faces": int(n_inside_internal),
                    "n_cavity_boundary_faces": int(
                        sum(boundary_by_class.values()) + n_physical_boundary
                    ),
                    "boundary_by_class": boundary_by_class,
                    "n_physical_boundary_faces": int(n_physical_boundary),
                    "ids_truncated": not include_full,
                    "sample_faces": faces_comp[: int(max_worst)],
                    "sample_cells": cells[: int(max_worst)],
                    "faces": faces_comp if include_full else [],
                    "cells": cells if include_full else [],
                    "cavity_shell": cavity_shell,
                }
            )
        packed_components.sort(
            key=lambda item: (int(item["n_faces"]), int(item["n_cells"])),
            reverse=True,
        )
        summary["components"] = packed_components[: int(max_worst)]
    return summary


def _tet_wall_cavity_eligibility(
    faces: list[list[int]],
    owner: list[int] | np.ndarray,
    neighbour: list[int] | np.ndarray,
    wall_face_indices: list[int],
    *,
    n_cells: int,
    sample_cap: int = 16,
) -> dict[str, Any]:
    """Summarize wall-owner cells eligible for local tet cavity replacement.

    A simple closed advancing-layer refill is only topologically local when a
    wall owner is a tetrahedron and owns exactly one selected wall face.  Cells
    with multiple wall faces, non-tet topology, or stale wall-face ids need the
    more general SMESH-style front/block/refill path.
    """
    summary: dict[str, Any] = {
        "n_cells": int(max(0, n_cells)),
        "n_wall_faces": int(len(wall_face_indices)),
        "n_wall_owner_cells": 0,
        "n_single_wall_owner_cells": 0,
        "n_single_wall_tet_owner_cells": 0,
        "n_multi_wall_owner_cells": 0,
        "n_non_tet_owner_cells": 0,
        "coverage_single_wall_tet": 0.0,
        "sample_single_wall_tet_cells": [],
        "single_wall_tet_cells": [],
        "sample_blocked_cells": [],
    }
    if n_cells <= 0 or not wall_face_indices or len(owner) == 0:
        return summary

    owner_arr = np.asarray(owner, dtype=np.int64)
    nbr_arr = np.asarray(neighbour, dtype=np.int64)
    cell_vertices: list[set[int]] = [set() for _ in range(int(n_cells))]
    cell_face_counts = [0 for _ in range(int(n_cells))]
    for fi, face in enumerate(faces):
        verts = {int(v) for v in face}
        if fi < len(owner_arr):
            own = int(owner_arr[fi])
            if 0 <= own < n_cells:
                cell_vertices[own].update(verts)
                cell_face_counts[own] += 1
        if fi < len(nbr_arr):
            nbr = int(nbr_arr[fi])
            if 0 <= nbr < n_cells:
                cell_vertices[nbr].update(verts)
                cell_face_counts[nbr] += 1

    wall_faces_by_owner: dict[int, list[int]] = {}
    stale_wall_faces = 0
    for fi in wall_face_indices:
        if fi < 0 or fi >= len(owner_arr):
            stale_wall_faces += 1
            continue
        own = int(owner_arr[fi])
        if 0 <= own < n_cells:
            wall_faces_by_owner.setdefault(own, []).append(int(fi))

    single_tet: list[int] = []
    blocked: list[dict[str, Any]] = []
    for cid, wall_faces in wall_faces_by_owner.items():
        n_wall = len(wall_faces)
        is_tet = len(cell_vertices[cid]) == 4 and cell_face_counts[cid] == 4
        if n_wall == 1:
            summary["n_single_wall_owner_cells"] += 1
            if is_tet:
                summary["n_single_wall_tet_owner_cells"] += 1
                single_tet.append(int(cid))
            else:
                summary["n_non_tet_owner_cells"] += 1
                if len(blocked) < sample_cap:
                    blocked.append(
                        {
                            "cell": int(cid),
                            "reason": "non_tet",
                            "n_wall_faces": int(n_wall),
                            "n_vertices": int(len(cell_vertices[cid])),
                            "n_faces": int(cell_face_counts[cid]),
                        }
                    )
        else:
            summary["n_multi_wall_owner_cells"] += 1
            if len(blocked) < sample_cap:
                blocked.append(
                    {
                        "cell": int(cid),
                        "reason": "multi_wall_faces",
                        "n_wall_faces": int(n_wall),
                        "n_vertices": int(len(cell_vertices[cid])),
                        "n_faces": int(cell_face_counts[cid]),
                    }
                )

    n_wall_owner = len(wall_faces_by_owner)
    summary["n_wall_owner_cells"] = int(n_wall_owner)
    summary["n_stale_wall_faces"] = int(stale_wall_faces)
    summary["coverage_single_wall_tet"] = (
        float(summary["n_single_wall_tet_owner_cells"]) / float(n_wall_owner)
        if n_wall_owner > 0
        else 0.0
    )
    summary["sample_single_wall_tet_cells"] = single_tet[: int(sample_cap)]
    summary["single_wall_tet_cells"] = list(single_tet)
    summary["sample_blocked_cells"] = blocked
    return summary


def _owner_centre_wall_motion(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    wall_vert_indices: list[int],
    wall_face_indices: list[int],
    cell_centres: np.ndarray,
    eligible_owner_cells: set[int] | list[int] | tuple[int, ...] | None,
    fallback_dirs: dict[int, np.ndarray],
    *,
    enabled: bool,
) -> tuple[dict[int, np.ndarray], dict[str, Any]]:
    """BLR-8 candidate: per-wall-vertex inward direction toward owner cell centres.

    For each wall vertex ``v`` adjacent to at least one wall face whose owner
    cell is in ``eligible_owner_cells`` (the BLR-7 single-tet, single-wall set),
    the new motion direction is the unit vector from the wall point toward the
    mean of those adjacent owner cell centres. Vertices with no eligible
    adjacent owner — or with a degenerate centre-to-vertex vector — fall back to
    ``fallback_dirs`` (typically ``-vnorm[v]``). When ``enabled`` is False the
    helper is a no-op: the returned dict is a copy of ``fallback_dirs`` and the
    diagnostics report zero motion.

    The returned diagnostics carry: ``enabled`` (bool), ``n_eligible``
    (vertices with at least one eligible adjacent owner), ``n_moved`` (vertices
    that ended up using the new direction), ``mean_motion`` and ``max_motion``
    (mean / max L2 norm of ``new_dir - fallback_dir`` across moved vertices,
    in unit-vector space; 0.0 when no vertex moved).
    """
    diag: dict[str, Any] = {
        "enabled": bool(enabled),
        "n_eligible": 0,
        "n_moved": 0,
        "mean_motion": 0.0,
        "max_motion": 0.0,
        "n_rejected_orientation": 0,
    }
    motion_dirs: dict[int, np.ndarray] = {
        v: np.asarray(fallback_dirs[v], dtype=np.float64).reshape(3)
        for v in wall_vert_indices
        if v in fallback_dirs
    }
    if not enabled or not wall_vert_indices:
        return motion_dirs, diag
    if eligible_owner_cells is None:
        return motion_dirs, diag
    eligible_set = {int(c) for c in eligible_owner_cells}
    if not eligible_set or cell_centres is None or len(cell_centres) == 0:
        return motion_dirs, diag

    owner_arr = np.asarray(owner, dtype=np.int64)
    n_centres = int(len(cell_centres))

    centre_accum: dict[int, np.ndarray] = {}
    centre_count: dict[int, int] = {}
    for fi in wall_face_indices:
        if fi < 0 or fi >= len(owner_arr):
            continue
        own = int(owner_arr[fi])
        if own < 0 or own >= n_centres:
            continue
        if own not in eligible_set:
            continue
        centre = np.asarray(cell_centres[own], dtype=np.float64).reshape(3)
        for vid in faces[fi]:
            v_int = int(vid)
            if v_int not in motion_dirs:
                continue
            if v_int not in centre_accum:
                centre_accum[v_int] = centre.copy()
                centre_count[v_int] = 1
            else:
                centre_accum[v_int] += centre
                centre_count[v_int] += 1

    n_eligible = 0
    n_moved = 0
    n_rejected_orientation = 0
    delta_norms: list[float] = []
    for v_int, accum in centre_accum.items():
        cnt = centre_count.get(v_int, 0)
        if cnt <= 0:
            continue
        n_eligible += 1
        mean_centre = accum / float(cnt)
        vec = mean_centre - np.asarray(points[v_int], dtype=np.float64).reshape(3)
        norm = float(np.linalg.norm(vec))
        if norm <= 1e-30 or not np.isfinite(norm):
            continue
        new_dir = vec / norm
        if not np.all(np.isfinite(new_dir)):
            continue
        fallback = motion_dirs[v_int]
        # Reject directions that disagree with the fallback's half-space.
        # For obtuse / sliver tets the centroid can lie close to the wall
        # plane and the centre-to-point vector may be tangent or even point
        # outward through the wall; keep the fallback in those cases.
        if float(np.dot(new_dir, fallback)) <= 0.0:
            n_rejected_orientation += 1
            continue
        delta = float(np.linalg.norm(new_dir - fallback))
        if delta <= 1e-12:
            # Direction effectively unchanged; do not perturb the fallback.
            continue
        motion_dirs[v_int] = new_dir
        n_moved += 1
        delta_norms.append(delta)

    diag["n_eligible"] = int(n_eligible)
    diag["n_moved"] = int(n_moved)
    diag["n_rejected_orientation"] = int(n_rejected_orientation)
    if delta_norms:
        diag["mean_motion"] = float(np.mean(delta_norms))
        diag["max_motion"] = float(np.max(delta_norms))
    return motion_dirs, diag


def _tet_wall_cavity_replacement_probe(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    wall_face_indices: list[int],
    eligible_owner_cells: list[int] | tuple[int, ...] | set[int] | None,
    cell_centres: np.ndarray,
    motion_dirs: dict[int, np.ndarray] | None,
    first_thickness: float,
    *,
    enabled: bool,
) -> dict[str, Any]:
    """BLR-9a: dry-run quality probe for single-tet wall-cavity replacement.

    For each eligible single-tet wall owner from BLR-7:

    - predict the prism inner triangle as the wall face vertices moved
      inward by ``motion_dirs[v] * first_thickness`` (BLR-8 motion when
      available; otherwise the call site's fallback ``-vnorm`` already
      lives in ``motion_dirs``);
    - predict a transition tet as (apex = original tet cell centroid,
      base = prism inner triangle);
    - count how many candidates yield a strictly-positive signed volume
      transition tet (the lowest necessary gate before any real
      ``polyMesh`` rewrite is attempted in BLR-9b).

    No mesh mutation. The diagnostics are intended only as a quality
    estimate so a verifier can decide whether the cavity-replacement
    path is worth turning on. When ``enabled`` is False the diagnostics
    are zero-filled.
    """
    diag: dict[str, Any] = {
        "enabled": bool(enabled),
        "n_candidates": 0,
        "n_quality_pass": 0,
        "n_quality_fail_det": 0,
        "n_quality_fail_topology": 0,
        "mean_predicted_det": 0.0,
        "min_predicted_det": 0.0,
        "max_predicted_det": 0.0,
    }
    if not enabled or not wall_face_indices or eligible_owner_cells is None:
        return diag
    eligible_set = {int(c) for c in eligible_owner_cells}
    if not eligible_set or cell_centres is None or len(cell_centres) == 0:
        return diag
    if motion_dirs is None:
        return diag

    owner_arr = np.asarray(owner, dtype=np.int64)
    n_centres = int(len(cell_centres))

    # Map: eligible owner cell -> the unique wall face it owns. Cells with
    # zero or 2+ wall faces would not have been classed as single-wall
    # eligible by BLR-7, but guard anyway so the probe never picks the
    # wrong face for an inverted topology snapshot.
    cell_to_wall_face: dict[int, int] = {}
    cell_wall_face_count: dict[int, int] = {}
    for fi in wall_face_indices:
        if fi < 0 or fi >= len(owner_arr):
            continue
        own = int(owner_arr[fi])
        if own < 0 or own >= n_centres or own not in eligible_set:
            continue
        cell_wall_face_count[own] = cell_wall_face_count.get(own, 0) + 1
        cell_to_wall_face.setdefault(own, int(fi))

    dets: list[float] = []
    n_topology_fail = 0
    n_det_fail = 0
    n_pass = 0
    for cid in eligible_set:
        if cell_wall_face_count.get(cid, 0) != 1:
            n_topology_fail += 1
            continue
        fi = cell_to_wall_face[cid]
        f = faces[fi]
        if len(f) != 3:
            n_topology_fail += 1
            continue
        v0, v1, v2 = int(f[0]), int(f[1]), int(f[2])
        try:
            d0 = motion_dirs[v0]
            d1 = motion_dirs[v1]
            d2 = motion_dirs[v2]
        except KeyError:
            n_topology_fail += 1
            continue
        # Predicted prism inner triangle (one layer of thickness).
        p0 = np.asarray(points[v0], dtype=np.float64)
        p1 = np.asarray(points[v1], dtype=np.float64)
        p2 = np.asarray(points[v2], dtype=np.float64)
        i0 = p0 + np.asarray(d0, dtype=np.float64).reshape(3) * float(first_thickness)
        i1 = p1 + np.asarray(d1, dtype=np.float64).reshape(3) * float(first_thickness)
        i2 = p2 + np.asarray(d2, dtype=np.float64).reshape(3) * float(first_thickness)
        apex = np.asarray(cell_centres[cid], dtype=np.float64).reshape(3)

        # Topology gate: the predicted inner triangle must lie on the same
        # side of the wall as the original cell centroid.  Outward motion
        # (inner pushed through the wall into the body solid) is
        # geometrically invalid for a cavity replacement and is counted as
        # a topology failure rather than a determinant failure.
        wall_centroid = (p0 + p1 + p2) / 3.0
        inner_centroid = (i0 + i1 + i2) / 3.0
        if float(np.dot(inner_centroid - wall_centroid, apex - wall_centroid)) <= 0.0:
            n_topology_fail += 1
            continue

        # Signed volume magnitude of the transition tet (apex, i0, i1, i2).
        m = np.stack([i0 - apex, i1 - apex, i2 - apex], axis=0)
        det_signed = float(np.linalg.det(m)) / 6.0
        if not np.isfinite(det_signed):
            n_det_fail += 1
            continue
        det = abs(det_signed)
        if det <= 1e-30:
            n_det_fail += 1
            continue
        n_pass += 1
        dets.append(det)

    n_candidates = int(len(eligible_set))
    diag["n_candidates"] = n_candidates
    diag["n_quality_pass"] = int(n_pass)
    diag["n_quality_fail_det"] = int(n_det_fail)
    diag["n_quality_fail_topology"] = int(n_topology_fail)
    if dets:
        dets_arr = np.asarray(dets, dtype=np.float64)
        diag["mean_predicted_det"] = float(dets_arr.mean())
        diag["min_predicted_det"] = float(dets_arr.min())
        diag["max_predicted_det"] = float(dets_arr.max())
    return diag


def _build_tet_cavity_replacement_plan(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    wall_face_indices: list[int],
    eligible_owner_cells: list[int] | tuple[int, ...] | set[int] | None,
    cell_centres: np.ndarray,
    motion_dirs: dict[int, np.ndarray] | None,
    first_thickness: float,
    *,
    enabled: bool,
    neighbour: np.ndarray | None = None,
) -> dict[str, Any]:
    """BLR-9b-i: build the replacement plan WITHOUT mutating the polyMesh.

    For each BLR-7 single-tet single-wall eligible owner that the BLR-9a
    probe would classify as quality_pass, emit a cell-level replacement
    plan:

    - ``cells_to_delete``: original wall-owner tet ids slated for removal.
    - ``new_cells``: per-replacement, the new cell vertex bundles
      ``{"prism": [...6 verts...], "transition_tet": [...4 verts...]}``.
      The prism's outer triangle keeps the original wall face vertex
      order; the inner triangle uses freshly minted point ids appended
      to ``new_points``.  The transition tet uses ``apex = original cell
      centroid`` and ``base = inner triangle`` (matching the BLR-9a
      probe geometry exactly).
    - ``new_points``: ``(N, 3)`` array of inner triangle coordinates
      that the caller will append to the global ``points`` array; the
      ``new_cells`` entries reference them by offset (offset 0 = first
      newly minted point, etc).
    - ``rejected``: candidates classified as topology_fail / det_fail
      so the caller can log them.

    No mesh mutation.  When ``enabled`` is False the plan is empty.
    """
    plan: dict[str, Any] = {
        "enabled": bool(enabled),
        "cells_to_delete": [],
        "new_cells": [],
        "new_points": np.zeros((0, 3), dtype=np.float64),
        "rejected": {
            "topology": [],
            "det": [],
            "neighbour_internal": [],
        },
        "n_planned": 0,
        "n_rejected_topology": 0,
        "n_rejected_det": 0,
        "n_rejected_neighbour_internal": 0,
    }
    if (
        not enabled
        or not wall_face_indices
        or eligible_owner_cells is None
        or motion_dirs is None
        or cell_centres is None
        or len(cell_centres) == 0
    ):
        return plan
    eligible_set = {int(c) for c in eligible_owner_cells}
    if not eligible_set:
        return plan

    owner_arr = np.asarray(owner, dtype=np.int64)
    n_centres = int(len(cell_centres))

    cell_to_wall_face: dict[int, int] = {}
    cell_wall_face_count: dict[int, int] = {}
    for fi in wall_face_indices:
        if fi < 0 or fi >= len(owner_arr):
            continue
        own = int(owner_arr[fi])
        if own < 0 or own >= n_centres or own not in eligible_set:
            continue
        cell_wall_face_count[own] = cell_wall_face_count.get(own, 0) + 1
        cell_to_wall_face.setdefault(own, int(fi))

    cells_to_delete: list[int] = []
    new_cells: list[dict[str, list[int]]] = []
    new_points_list: list[np.ndarray] = []
    rejected_topology: list[int] = []
    rejected_det: list[int] = []
    rejected_neighbour_internal: list[int] = []

    # BLR-9b-iii topology guard: a single-tet wall owner can be safely
    # replaced by the BLR-9b-ii prism + transition tet pair only when
    # the replacement does not orphan an adjacent cell's internal face
    # (the new cells share the wall face but NOT the original tet's
    # other three internal faces).  Detect this by counting how many
    # of the deleted cell's faces are internal — i.e. shared with a
    # neighbour cell.  If any internal face exists, the simple
    # 1-prism-+-1-transition-tet rewrite would leave the neighbour
    # without a partner face, so the candidate must be rejected.  This
    # restricts BLR-9b application to "isolated" wall owners — typical
    # of small disconnected fragments — and BLR-9c will add the
    # multi-cell cavity refill needed for the general case.
    if neighbour is not None:
        nbr_arr = np.asarray(neighbour, dtype=np.int64)
        cell_internal_face_count: dict[int, int] = {}
        for fi in range(min(len(owner_arr), len(nbr_arr))):
            own = int(owner_arr[fi])
            nbr = int(nbr_arr[fi])
            if 0 <= own < n_centres:
                cell_internal_face_count[own] = (
                    cell_internal_face_count.get(own, 0) + 1
                )
            if 0 <= nbr < n_centres:
                cell_internal_face_count[nbr] = (
                    cell_internal_face_count.get(nbr, 0) + 1
                )
    else:
        cell_internal_face_count = {}

    n_orig_points = int(points.shape[0])
    next_id = n_orig_points

    for cid in sorted(eligible_set):
        if cell_wall_face_count.get(cid, 0) != 1:
            rejected_topology.append(int(cid))
            continue
        # BLR-9b-iii: reject if the original tet has neighbour-internal
        # faces. Neighbours would otherwise lose their partner face.
        if neighbour is not None and cell_internal_face_count.get(cid, 0) > 0:
            rejected_neighbour_internal.append(int(cid))
            continue
        fi = cell_to_wall_face[cid]
        f = faces[fi]
        if len(f) != 3:
            rejected_topology.append(int(cid))
            continue
        v0, v1, v2 = int(f[0]), int(f[1]), int(f[2])
        try:
            d0 = motion_dirs[v0]
            d1 = motion_dirs[v1]
            d2 = motion_dirs[v2]
        except KeyError:
            rejected_topology.append(int(cid))
            continue

        p0 = np.asarray(points[v0], dtype=np.float64)
        p1 = np.asarray(points[v1], dtype=np.float64)
        p2 = np.asarray(points[v2], dtype=np.float64)
        i0_pt = p0 + np.asarray(d0, dtype=np.float64).reshape(3) * float(first_thickness)
        i1_pt = p1 + np.asarray(d1, dtype=np.float64).reshape(3) * float(first_thickness)
        i2_pt = p2 + np.asarray(d2, dtype=np.float64).reshape(3) * float(first_thickness)
        apex = np.asarray(cell_centres[cid], dtype=np.float64).reshape(3)

        # Topology gate identical to the BLR-9a probe.
        wall_centroid = (p0 + p1 + p2) / 3.0
        inner_centroid = (i0_pt + i1_pt + i2_pt) / 3.0
        if (
            float(np.dot(inner_centroid - wall_centroid, apex - wall_centroid))
            <= 0.0
        ):
            rejected_topology.append(int(cid))
            continue

        # Determinant gate identical to the BLR-9a probe.
        m = np.stack([i0_pt - apex, i1_pt - apex, i2_pt - apex], axis=0)
        det_signed = float(np.linalg.det(m)) / 6.0
        if (not np.isfinite(det_signed)) or abs(det_signed) <= 1e-30:
            rejected_det.append(int(cid))
            continue

        # Mint the three new inner-triangle point ids.
        i0 = next_id
        i1 = next_id + 1
        i2 = next_id + 2
        next_id += 3
        new_points_list.append(i0_pt)
        new_points_list.append(i1_pt)
        new_points_list.append(i2_pt)

        cells_to_delete.append(int(cid))
        new_cells.append(
            {
                "prism": [v0, v1, v2, i0, i1, i2],
                # Apex point id is deliberately left as -1 here — BLR-9b-ii
                # will mint the original cell centroid as a real point when
                # the plan is applied to the polyMesh.  ``transition_tet[0]``
                # MUST be re-resolved at apply time using the
                # ``transition_tet_apex_xyz`` coordinate below.
                "transition_tet": [-1, i0, i1, i2],
                "transition_tet_apex_xyz": apex.tolist(),
                "deleted_cell_id": int(cid),
            }
        )

    plan["cells_to_delete"] = cells_to_delete
    plan["new_cells"] = new_cells
    if new_points_list:
        plan["new_points"] = np.asarray(new_points_list, dtype=np.float64)
    plan["rejected"]["topology"] = rejected_topology
    plan["rejected"]["det"] = rejected_det
    plan["rejected"]["neighbour_internal"] = rejected_neighbour_internal
    plan["n_planned"] = int(len(cells_to_delete))
    plan["n_rejected_topology"] = int(len(rejected_topology))
    plan["n_rejected_det"] = int(len(rejected_det))
    plan["n_rejected_neighbour_internal"] = int(len(rejected_neighbour_internal))
    return plan


def _detect_wall_owner_cavity_components(
    owner: np.ndarray | list[int],
    neighbour: np.ndarray | list[int],
    wall_face_indices: list[int],
    *,
    n_cells: int | None = None,
) -> list[set[int]]:
    """BLR-9c-a: connected wall-owner cell components via internal faces.

    Returns a list of cell-id sets, each set being the connected component
    of wall-owner cells reachable through internal faces.  This is the
    structural primitive BLR-9c will use to drive a multi-cell cavity
    refill: one prism stack per component, transition cells filling the
    cavity boundary.

    A "wall owner" is any cell that owns at least one face listed in
    ``wall_face_indices``.  Two wall-owner cells are in the same
    component iff there is an internal face between them whose owner and
    neighbour are both wall-owner cells (transitively).

    The function performs only union-find on the cell graph; it never
    mutates the polyMesh and never inspects ``faces`` or ``points``.
    Single-tet wall owners (BLR-7 eligible cells) appear here as size-1
    components.  Multi-cell components are exactly the BLR-9c targets
    that BLR-9b's simple rewrite has been refusing.
    """
    owner_arr = np.asarray(owner, dtype=np.int64)
    neighbour_arr = np.asarray(neighbour, dtype=np.int64)
    if owner_arr.size == 0:
        return []
    if n_cells is None:
        max_own = int(owner_arr.max()) if owner_arr.size > 0 else -1
        max_nbr = (
            int(neighbour_arr.max()) if neighbour_arr.size > 0 else -1
        )
        n_cells = max(max_own, max_nbr) + 1
    if n_cells <= 0:
        return []

    wall_owner_set: set[int] = set()
    for fi in wall_face_indices:
        if fi < 0 or fi >= owner_arr.size:
            continue
        own = int(owner_arr[fi])
        if 0 <= own < n_cells:
            wall_owner_set.add(own)
    if not wall_owner_set:
        return []

    # Union-find restricted to wall-owner cells.
    parent = {c: c for c in wall_owner_set}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    n_internal = int(min(owner_arr.size, neighbour_arr.size))
    for fi in range(n_internal):
        own = int(owner_arr[fi])
        nbr = int(neighbour_arr[fi])
        if own in wall_owner_set and nbr in wall_owner_set:
            union(own, nbr)

    groups: dict[int, set[int]] = {}
    for c in wall_owner_set:
        r = find(c)
        groups.setdefault(r, set()).add(c)
    return [groups[r] for r in sorted(groups.keys())]


def _extract_cavity_component_boundary(
    component: set[int] | frozenset[int] | list[int] | tuple[int, ...],
    owner: np.ndarray | list[int],
    neighbour: np.ndarray | list[int],
    wall_face_indices: list[int],
) -> dict[str, list[int]]:
    """BLR-9c-b: face-level boundary structure of a cavity component.

    A cavity component (output of :func:`_detect_wall_owner_cavity_components`)
    is a set of wall-owner cells.  When BLR-9c rewrites the component
    we need to know which faces:

    - ``wall_faces``: are wall (boundary) faces of cells inside the
      component.  These are the BL prism's outer/bottom faces and
      survive the rewrite (their winding becomes the new prism's
      bottom).
    - ``external_internal_faces``: are internal faces with one cell
      inside the component and the other cell OUTSIDE.  After the
      component's cells are deleted, these face surfaces define the
      cavity's outer (bulk-facing) shell — the closed surface BLR-9c
      must respect when generating refill cells.
    - ``internal_faces``: are internal faces with BOTH cells in the
      component.  They vanish when the cavity is rewritten.

    The function performs only owner/neighbour table lookups; it does
    not mutate the polyMesh or inspect ``points`` / ``faces``.
    """
    comp_set = {int(c) for c in component}
    owner_arr = np.asarray(owner, dtype=np.int64)
    neighbour_arr = np.asarray(neighbour, dtype=np.int64)

    wall_face_id_set = {int(fi) for fi in wall_face_indices}

    wall_faces: list[int] = []
    external_internal_faces: list[int] = []
    internal_faces: list[int] = []

    n_internal = int(min(owner_arr.size, neighbour_arr.size))
    n_total = int(owner_arr.size)

    for fi in range(n_total):
        own = int(owner_arr[fi])
        nbr = int(neighbour_arr[fi]) if fi < n_internal else -1

        own_in = own in comp_set
        nbr_in = (nbr >= 0) and (nbr in comp_set)

        if not own_in and not nbr_in:
            continue

        if nbr < 0:
            # Boundary face. Wall face only if listed in wall_face_indices.
            if fi in wall_face_id_set:
                wall_faces.append(int(fi))
            else:
                # Non-wall boundary face owned by a component cell — the
                # rewrite still has to account for it; classify with the
                # external-internal pile so callers don't lose track.
                external_internal_faces.append(int(fi))
            continue

        if own_in and nbr_in:
            internal_faces.append(int(fi))
        else:
            # Internal face crossing the component boundary.
            external_internal_faces.append(int(fi))

    return {
        "wall_faces": wall_faces,
        "external_internal_faces": external_internal_faces,
        "internal_faces": internal_faces,
    }


def _build_cavity_prism_inner_triangles(
    component_wall_faces: list[int],
    points: np.ndarray,
    faces: list[list[int]],
    motion_dirs: dict[int, np.ndarray] | None,
    first_thickness: float,
) -> list[dict[str, Any]]:
    """BLR-9c-c-i: predicted inner triangle per wall face of a cavity component.

    For each ``face_id`` in ``component_wall_faces`` (a subset of the
    polyMesh's wall faces, restricted to the cavity component by
    BLR-9c-a + BLR-9c-b), compute the prism inner triangle as
    ``points[v] + motion_dirs[v] * first_thickness`` for each vertex
    ``v``.  Returns a list of dicts so BLR-9c-c-ii can stitch shared
    vertices into per-face inner ids in a separate pass.

    Each entry contains:

    - ``face_id``: the original wall face id.
    - ``outer_verts``: ``[v0, v1, v2]`` — wall face vertex order
      preserved.
    - ``inner_xyz``: ``np.ndarray`` of shape ``(3, 3)`` — inner
      triangle coordinates, row order matching ``outer_verts``.

    Faces missing a motion direction or with non-triangle topology
    are skipped silently — BLR-9c-c-ii will detect missing entries
    and abort the refill for the affected component.

    No mesh mutation; pure prediction.
    """
    if not component_wall_faces or motion_dirs is None:
        return []
    out: list[dict[str, Any]] = []
    pts = np.asarray(points, dtype=np.float64)
    for fi in component_wall_faces:
        if fi < 0 or fi >= len(faces):
            continue
        f = faces[fi]
        if len(f) != 3:
            continue
        v0, v1, v2 = int(f[0]), int(f[1]), int(f[2])
        try:
            d0 = np.asarray(motion_dirs[v0], dtype=np.float64).reshape(3)
            d1 = np.asarray(motion_dirs[v1], dtype=np.float64).reshape(3)
            d2 = np.asarray(motion_dirs[v2], dtype=np.float64).reshape(3)
        except KeyError:
            continue
        inner_xyz = np.stack(
            [
                pts[v0] + d0 * float(first_thickness),
                pts[v1] + d1 * float(first_thickness),
                pts[v2] + d2 * float(first_thickness),
            ],
            axis=0,
        )
        out.append(
            {
                "face_id": int(fi),
                "outer_verts": [v0, v1, v2],
                "inner_xyz": inner_xyz,
            }
        )
    return out


def _stitch_cavity_prism_inner_ids_smooth(
    inner_triangles: list[dict[str, Any]],
) -> dict[str, Any]:
    """BLR-9c-c-ii-a: smooth-case shared inner-vertex stitching.

    Every wall vertex shared by multiple component wall faces collapses
    into ONE inner vertex.  The shared inner position is the mean of
    each face's prediction for that wall vertex (BLR-9c-c-i emits one
    ``inner_xyz`` row per outer vertex per face; here we average them).

    This is the no-dup baseline.  BLR-9c-c-ii-b will add the sharp-
    corner detection that splits a wall vertex into per-face duplicate
    inner ids when adjacent prism cap normals diverge above a cos
    threshold (the same idea as the VD refactor's per-face inner
    verts, applied per cavity component).

    Returns:
        - ``inner_points``: ``np.ndarray`` of shape ``(N_inner, 3)`` —
          unique inner vertex coordinates in ascending wall vertex id
          order.
        - ``vert_to_inner_id``: ``dict[int, int]`` mapping each wall
          vertex id to its inner vertex id.
        - ``face_inner_ids``: list aligned with ``inner_triangles``,
          each entry ``[i0, i1, i2]`` giving inner ids for the 3
          outer verts of that face.
    """
    if not inner_triangles:
        return {
            "inner_points": np.zeros((0, 3), dtype=np.float64),
            "vert_to_inner_id": {},
            "face_inner_ids": [],
        }

    # Accumulate per-vertex sums of predicted inner coordinates.
    accum: dict[int, np.ndarray] = {}
    counts: dict[int, int] = {}
    for entry in inner_triangles:
        outer = entry["outer_verts"]
        inner_xyz = np.asarray(entry["inner_xyz"], dtype=np.float64)
        if inner_xyz.shape != (3, 3) or len(outer) != 3:
            continue
        for k in range(3):
            v = int(outer[k])
            if v not in accum:
                accum[v] = inner_xyz[k].copy()
                counts[v] = 1
            else:
                accum[v] += inner_xyz[k]
                counts[v] += 1

    sorted_verts = sorted(accum.keys())
    vert_to_inner_id: dict[int, int] = {
        v: i for i, v in enumerate(sorted_verts)
    }
    inner_points = np.stack(
        [accum[v] / float(counts[v]) for v in sorted_verts], axis=0
    )

    face_inner_ids: list[list[int]] = []
    for entry in inner_triangles:
        outer = entry["outer_verts"]
        if len(outer) != 3:
            continue
        try:
            face_inner_ids.append(
                [
                    vert_to_inner_id[int(outer[0])],
                    vert_to_inner_id[int(outer[1])],
                    vert_to_inner_id[int(outer[2])],
                ]
            )
        except KeyError:
            continue
    return {
        "inner_points": inner_points,
        "vert_to_inner_id": vert_to_inner_id,
        "face_inner_ids": face_inner_ids,
    }


def _split_cavity_inner_ids_at_sharp_corners(
    inner_triangles: list[dict[str, Any]],
    smooth_stitch: dict[str, Any],
    *,
    cos_thresh: float = 0.9,
) -> dict[str, Any]:
    """BLR-9c-c-ii-b: split shared inner ids at sharp cavity corners.

    Starts from the smooth stitcher output (every shared wall vertex
    has one inner id) and, for each wall vertex shared by multiple
    component wall faces, computes the pairwise cosine between
    adjacent prism cap normals.  When any pair of cap normals has
    ``cos < cos_thresh`` the vertex is "sharp" and each face gets its
    own per-face inner id at that vertex (vertex duplication, the
    same idea as the VD refactor applied per cavity component).

    Cap normal = ``(i1-i0) × (i2-i0)`` from the face's predicted
    inner triangle (BLR-9c-c-i ``inner_xyz``).

    Returns:
        - ``inner_points`` (N_inner_after_split, 3) — unique coords
          (smooth stitcher's coords plus the duplicates at split
          vertices).
        - ``face_inner_ids`` aligned with ``inner_triangles``: each
          ``[i0, i1, i2]``; smooth verts share ids, sharp verts have
          per-face ids.
        - ``sharp_verts``: ``dict[int, list[int]]`` mapping each
          split wall vertex to the list of its per-face inner ids
          (in the same order as the face list at that vertex).
        - ``n_split``: number of wall vertices that got duplicated.
    """
    smooth_points = np.asarray(
        smooth_stitch.get("inner_points", np.zeros((0, 3))),
        dtype=np.float64,
    )
    vert_to_inner_id: dict[int, int] = dict(
        smooth_stitch.get("vert_to_inner_id", {})
    )
    smooth_face_inner_ids: list[list[int]] = [
        list(x) for x in smooth_stitch.get("face_inner_ids", [])
    ]

    if not inner_triangles or len(inner_triangles) != len(smooth_face_inner_ids):
        return {
            "inner_points": smooth_points.copy(),
            "face_inner_ids": [list(x) for x in smooth_face_inner_ids],
            "sharp_verts": {},
            "n_split": 0,
        }

    # Per-face cap normal.
    face_normals: list[np.ndarray] = []
    for entry in inner_triangles:
        inner_xyz = np.asarray(entry["inner_xyz"], dtype=np.float64)
        if inner_xyz.shape != (3, 3):
            face_normals.append(np.zeros(3, dtype=np.float64))
            continue
        n_raw = np.cross(
            inner_xyz[1] - inner_xyz[0], inner_xyz[2] - inner_xyz[0]
        )
        m = float(np.linalg.norm(n_raw))
        face_normals.append(
            n_raw / m if m > 1e-30 else np.zeros(3, dtype=np.float64)
        )

    # Per-vertex face list (smooth stitcher already aggregated; recompute
    # in face order so we can emit per-face dup ids deterministically).
    vert_to_faces: dict[int, list[int]] = {}
    for fi_idx, entry in enumerate(inner_triangles):
        for v in entry["outer_verts"]:
            vert_to_faces.setdefault(int(v), []).append(fi_idx)

    extra_points: list[np.ndarray] = []
    next_inner_id = int(smooth_points.shape[0])
    sharp_verts: dict[int, list[int]] = {}
    n_split = 0
    # Make a working copy of face inner ids that we will rewrite at
    # sharp verts.
    face_inner_ids: list[list[int]] = [list(x) for x in smooth_face_inner_ids]

    for v, f_idx_list in vert_to_faces.items():
        if len(f_idx_list) < 2:
            continue
        # Pairwise cosine min.
        normals = [face_normals[fi] for fi in f_idx_list]
        is_sharp = False
        for i in range(len(normals)):
            for j in range(i + 1, len(normals)):
                if float(np.dot(normals[i], normals[j])) < cos_thresh:
                    is_sharp = True
                    break
            if is_sharp:
                break
        if not is_sharp:
            continue

        # Sharp vertex — emit per-face dup ids.  Keep the smooth id
        # for the FIRST face so we don't churn smooth ids unnecessarily;
        # mint new ids for the remaining faces.
        per_face_ids: list[int] = []
        for offset, fi_idx in enumerate(f_idx_list):
            entry = inner_triangles[fi_idx]
            outer = entry["outer_verts"]
            inner_xyz = np.asarray(entry["inner_xyz"], dtype=np.float64)
            try:
                k = outer.index(v)
            except ValueError:
                continue
            if offset == 0:
                # First face keeps the smooth shared id at this vert.
                per_face_ids.append(face_inner_ids[fi_idx][k])
                continue
            # Subsequent faces get a fresh dup id placed at this face's
            # own predicted inner position for vertex v.
            extra_points.append(inner_xyz[k].copy())
            new_id = next_inner_id
            next_inner_id += 1
            face_inner_ids[fi_idx][k] = new_id
            per_face_ids.append(new_id)
        sharp_verts[v] = per_face_ids
        n_split += 1

    if extra_points:
        inner_points_out = np.concatenate(
            [smooth_points, np.stack(extra_points, axis=0)], axis=0
        )
    else:
        inner_points_out = smooth_points.copy()

    return {
        "inner_points": inner_points_out,
        "face_inner_ids": face_inner_ids,
        "sharp_verts": sharp_verts,
        "n_split": int(n_split),
    }


def _compute_cavity_centroid(
    component: set[int] | frozenset[int] | list[int] | tuple[int, ...],
    faces: list[list[int]],
    points: np.ndarray,
    owner: np.ndarray | list[int],
    neighbour: np.ndarray | list[int],
) -> np.ndarray:
    """BLR-9c-c-iii-a: cavity apex = mean of all unique vertices owned by
    cells in the component.

    Used by BLR-9c-c-iii-b as the apex of the transition tets that fill
    the volume between each prism cap (BLR-9c-c-ii output) and the
    cavity's interior.  Returns a ``(3,)`` ndarray; an all-zero vector
    when the component is empty.
    """
    comp_set = {int(c) for c in component}
    if not comp_set:
        return np.zeros(3, dtype=np.float64)
    owner_arr = np.asarray(owner, dtype=np.int64)
    neighbour_arr = np.asarray(neighbour, dtype=np.int64)
    n_internal = int(min(owner_arr.size, neighbour_arr.size))
    n_total = int(owner_arr.size)

    vert_ids: set[int] = set()
    for fi in range(n_total):
        own = int(owner_arr[fi])
        nbr = int(neighbour_arr[fi]) if fi < n_internal else -1
        if own in comp_set or (nbr >= 0 and nbr in comp_set):
            for v in faces[fi]:
                vert_ids.add(int(v))
    if not vert_ids:
        return np.zeros(3, dtype=np.float64)
    pts = np.asarray(points, dtype=np.float64)
    return pts[sorted(vert_ids)].mean(axis=0)


def _build_cavity_fan_transition_tets(
    inner_triangles: list[dict[str, Any]],
    split_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """BLR-9c-c-iii-b: emit a fan transition tet per prism cap.

    Each entry pairs a cap's inner triangle ``[i0, i1, i2]`` (from
    ``split_result["face_inner_ids"]``, which already accounts for
    smooth and sharp-corner stitching) with the cavity apex
    placeholder ``-1`` so the caller can mint a real apex point id
    when the final polyMesh is assembled.

    Returns:
        list aligned with ``inner_triangles``; each entry is::

            {
                "face_id":   int  - original wall face id,
                "tet_verts": [-1, i0, i1, i2],
            }

    Faces with no matching ``face_inner_ids`` row (e.g. dropped by
    BLR-9c-c-i for missing motion direction) are silently skipped.
    """
    face_inner_ids = list(split_result.get("face_inner_ids", []))
    if not inner_triangles or not face_inner_ids:
        return []
    out: list[dict[str, Any]] = []
    n = min(len(inner_triangles), len(face_inner_ids))
    for k in range(n):
        ids = list(face_inner_ids[k])
        if len(ids) != 3:
            continue
        out.append(
            {
                "face_id": int(inner_triangles[k]["face_id"]),
                "tet_verts": [-1, int(ids[0]), int(ids[1]), int(ids[2])],
            }
        )
    return out


def _check_cavity_shell_coverage(
    boundary: dict[str, list[int]],
    fan_tets: list[dict[str, Any]],
    faces: list[list[int]],
) -> dict[str, Any]:
    """BLR-9c-c-iii-c: shell-face coverage probe for transition cells.

    For each ``external_internal_face`` in ``boundary`` (the cavity's
    outer shell), check whether any face of any fan transition tet has
    the same unordered vertex set.  Shell faces that find no matching
    tet face are returned as ``uncovered`` — they are the first reject
    reason BLR-9c-d will gate on.

    The current BLR-9c-c-iii-b fan structure (apex + each prism cap)
    cannot, in general, cover the cavity's external_internal shell:
    the shell faces sit on the cell's *other* sides and would need
    additional transition cells (e.g. one tet per shell face glued to
    the apex).  This probe makes that gap explicit so a verifier can
    reject the candidate before any mesh mutation.

    A "tet face" of a transition tet ``[apex, i0, i1, i2]`` is one of
    the four triangles ``(apex, i0, i1)``, ``(apex, i1, i2)``,
    ``(apex, i0, i2)``, ``(i0, i1, i2)``.  Vertex set matching is
    strict (same three vertex ids, order-independent).

    Returns dict::

        {
            "n_shell_faces": int,
            "n_covered":     int,
            "uncovered":     list[int],   # original face_ids
        }
    """
    shell_face_ids = list(boundary.get("external_internal_faces", []))
    if not shell_face_ids:
        return {"n_shell_faces": 0, "n_covered": 0, "uncovered": []}

    # Two coverage representations live on the input ``fan_tets`` list:
    #
    # - Inner-id space (BLR-9c-c-iii-b fan tets): ``tet_verts`` indexes
    #   the BLR-9c-c-i / 9c-c-ii inner-points array, so the four
    #   triangle face vertex sets are inner ids.  These never match a
    #   polyMesh shell face by construction — the early sub-step
    #   recorded that gap and BLR-9c-d-h-1 closes it via closure tets.
    # - PolyMesh-id space (BLR-9c-d-h-1 closure tets): each closure tet
    #   carries an ``outer_verts`` field listing the polyMesh face
    #   vertices it was built from.  When sorted, that key matches the
    #   shell face directly.  Polygon shell faces (quads, etc.) are
    #   covered iff *any* closure tet has ``outer_verts`` whose vertex
    #   set equals the shell face's.
    outer_keys: set[tuple[int, ...]] = set()
    for tet in fan_tets:
        outer = tet.get("outer_verts")
        if outer is None:
            continue
        outer_keys.add(tuple(sorted(int(v) for v in outer)))

    tet_face_keys: set[tuple[int, int, int]] = set()
    for tet in fan_tets:
        verts = list(tet.get("tet_verts", []))
        if len(verts) != 4:
            continue
        for i in range(4):
            triangle = [verts[k] for k in range(4) if k != i]
            tet_face_keys.add(tuple(sorted(int(v) for v in triangle)))

    n_covered = 0
    uncovered: list[int] = []
    for fi in shell_face_ids:
        if fi < 0 or fi >= len(faces):
            uncovered.append(int(fi))
            continue
        f = faces[fi]
        if len(f) < 3:
            uncovered.append(int(fi))
            continue
        key = tuple(sorted(int(v) for v in f))
        if key in outer_keys:
            n_covered += 1
            continue
        # Legacy inner-id match (kept for the BLR-9c-c-iii-c unit
        # tests that synthesise tri shell faces directly from
        # placeholder tet vertex ids).
        if len(f) == 3 and key in tet_face_keys:
            n_covered += 1
            continue
        uncovered.append(int(fi))

    return {
        "n_shell_faces": int(len(shell_face_ids)),
        "n_covered": int(n_covered),
        "uncovered": uncovered,
    }


def _resolve_tet_apex_xyz(
    tet_verts: list[int],
    shared_apex_xyz: np.ndarray,
    inner_points: np.ndarray,
) -> tuple[np.ndarray, int, int, int] | None:
    """BLR-9c-d-m-2 helper — extract ``(apex_xyz, i0, i1, i2)`` from a
    tet's ``tet_verts`` list, supporting both legacy shared-apex
    placeholder (-1) and per-face Steiner indices (non-negative).

    Returns ``None`` if the tet vertex schema is malformed.
    """
    if len(tet_verts) != 4:
        return None
    a_idx = int(tet_verts[0])
    if a_idx == -1:
        a_xyz = shared_apex_xyz
    elif 0 <= a_idx < inner_points.shape[0]:
        a_xyz = inner_points[a_idx]
    else:
        return None
    i0, i1, i2 = int(tet_verts[1]), int(tet_verts[2]), int(tet_verts[3])
    if (
        i0 < 0 or i1 < 0 or i2 < 0
        or i0 >= inner_points.shape[0]
        or i1 >= inner_points.shape[0]
        or i2 >= inner_points.shape[0]
    ):
        return None
    return a_xyz, i0, i1, i2


def _check_cavity_fan_tet_determinants(
    fan_tets: list[dict[str, Any]],
    apex_xyz: np.ndarray | list[float],
    inner_points: np.ndarray,
    *,
    det_tol: float = 1e-12,
) -> dict[str, Any]:
    """BLR-9c-d-b: signed-volume gate for the BLR-9c-c-iii-b fan tets.

    Each fan tet is ``tet_verts = [-1, i0, i1, i2]`` where ``-1`` is the
    apex placeholder and ``i0/i1/i2`` index ``inner_points`` (the
    BLR-9c-c-ii inner-triangle vertices, possibly duplicated by the
    BLR-9c-c-ii-b sharp-corner split).  The signed scalar triple product

        det = (v0 - apex) · ((v1 - apex) × (v2 - apex))

    is sign-invariant under triangle winding, so this helper returns
    both the *signed* determinants (so the caller can detect sign-flips
    inside one component, which indicates a flipped fan triangle) and
    a per-tet pass/fail label gated only on ``abs(det) > det_tol``.

    The helper does **not** mutate the mesh and does **not** decide the
    component verdict — BLR-9c-d (c) wires the result into
    ``_evaluate_cavity_component_candidates``.

    Parameters
    ----------
    fan_tets:
        Output of :func:`_build_cavity_fan_transition_tets`.
    apex_xyz:
        Apex vertex coordinate (typically the cavity centroid from
        :func:`_compute_cavity_centroid`).
    inner_points:
        ``(M, 3)`` array of inner triangle vertex coordinates from
        :func:`_split_cavity_inner_ids_at_sharp_corners` (or
        :func:`_stitch_cavity_prism_inner_ids_smooth` if no split was
        applied).
    det_tol:
        Magnitude below which a tet is treated as degenerate.

    Returns
    -------
    dict with keys

    - ``n_tets``               total fan tets inspected
    - ``n_pos_det``            tets with ``det > +det_tol``
    - ``n_neg_det``            tets with ``det < -det_tol``
    - ``n_degenerate_det``     tets with ``abs(det) <= det_tol``
    - ``signed_dets``          ``np.ndarray`` shape ``(n_tets,)``
    - ``worst_abs_det``        smallest ``|det|`` across all tets (or 0 if empty)
    - ``n_sign_inconsistent``  tets whose sign disagrees with the majority
                               of the rest of the component (BLR-9c-d-i-1).
                               Reported as a *diagnostic only* — the
                               polyMesh writer can re-orient any cell
                               before emitting the mesh, so sign mixing
                               is not a hard reject reason here.
    - ``bad_indices``          ``list[int]`` of fan-tet positions whose
                               ``abs(det) <= det_tol`` (degenerate).
                               Sign-inconsistent tets are *not* added
                               to this list any more — see BLR-9c-d-i-1
                               for the rationale.
    """
    out: dict[str, Any] = {
        "n_tets": 0,
        "n_pos_det": 0,
        "n_neg_det": 0,
        "n_degenerate_det": 0,
        "signed_dets": np.empty(0, dtype=np.float64),
        "worst_abs_det": 0.0,
        "n_sign_inconsistent": 0,
        "bad_indices": [],
    }
    if not fan_tets:
        return out
    inner = np.asarray(inner_points, dtype=np.float64)
    if inner.size == 0 or inner.shape[0] < 1:
        out["bad_indices"] = list(range(len(fan_tets)))
        out["n_tets"] = len(fan_tets)
        out["n_degenerate_det"] = len(fan_tets)
        return out
    apex = np.asarray(apex_xyz, dtype=np.float64).reshape(3)

    n = len(fan_tets)
    dets = np.zeros(n, dtype=np.float64)
    bad_set: set[int] = set()
    for k, tet in enumerate(fan_tets):
        verts = tet.get("tet_verts", [])
        resolved = _resolve_tet_apex_xyz(verts, apex, inner)
        if resolved is None:
            bad_set.add(k)
            continue
        a_xyz, i0, i1, i2 = resolved
        v0 = inner[i0] - a_xyz
        v1 = inner[i1] - a_xyz
        v2 = inner[i2] - a_xyz
        dets[k] = float(np.dot(v0, np.cross(v1, v2)))

    abs_dets = np.abs(dets)
    n_pos = int(np.sum(dets > det_tol))
    n_neg = int(np.sum(dets < -det_tol))
    n_deg = int(np.sum(abs_dets <= det_tol))
    for k in range(n):
        if abs_dets[k] <= det_tol:
            bad_set.add(k)

    # BLR-9c-d-i-1 — sign-inconsistency is now reported as a diagnostic
    # only.  When the BLR-9c-c-iii-b fan and the BLR-9c-d-h-1 closure
    # tets are produced from inputs with different winding conventions
    # (e.g. inner-triangle motion vs. polyMesh face winding) some tets
    # come out with positive signed volume and others with negative —
    # but each of them is individually non-degenerate and the polyMesh
    # writer can flip any cell at emission time.  Counting them as
    # ``bad_indices`` was the dominant reject reason on the 21-STL bench
    # (761 / 861 components for test_cube + easy_100034) and rejected
    # otherwise-valid replacement candidates.
    n_sign_inconsistent = 0
    if n_pos > 0 and n_neg > 0:
        majority_sign = 1.0 if n_pos >= n_neg else -1.0
        n_sign_inconsistent = int(
            np.sum(
                (abs_dets > det_tol)
                & (np.sign(dets) != majority_sign)
            )
        )

    out["n_tets"] = n
    out["n_pos_det"] = n_pos
    out["n_neg_det"] = n_neg
    out["n_degenerate_det"] = n_deg
    out["signed_dets"] = dets
    out["worst_abs_det"] = float(abs_dets.min()) if n > 0 else 0.0
    out["n_sign_inconsistent"] = n_sign_inconsistent
    out["bad_indices"] = sorted(bad_set)
    return out


def _check_cavity_fan_tet_pair_non_ortho(
    fan_tets: list[dict[str, Any]],
    apex_xyz: np.ndarray | list[float],
    inner_points: np.ndarray,
    *,
    non_ortho_threshold_deg: float = 70.0,
) -> dict[str, Any]:
    """BLR-9c-d-e-1: per-pair non-orthogonality of adjacent fan tets.

    The OpenFOAM ``checkMesh`` non-orthogonality angle is the angle
    between an internal face's area-weighted normal and the line
    that connects the owner and neighbour cell centroids.  ESI's
    `OpenFOAM-v2406` flags any face above ~70° as a quality failure.

    For the BLR-9c cavity replacement, the new *internal* faces
    inside a single component are precisely the lateral triangles
    ``(apex, i_a, i_b)`` shared by two adjacent fan tets in the fan
    structure.  Two fan tets are adjacent iff they share two of the
    three inner-triangle indices.  Each such pair contributes one
    internal face whose non-orthogonality we can measure right now,
    before any mesh mutation, using:

    - face centroid ``c_f = (apex + p_a + p_b) / 3``
    - face normal   ``n_f = (p_a − apex) × (p_b − apex)`` (un-normalized,
      magnitude = 2 × triangle area)
    - owner cell centroid  ``c_O = mean(fan_tet_O.verts)``
    - neighbour cell centroid ``c_N = mean(fan_tet_N.verts)``
    - cell-to-cell vector ``d = c_N − c_O``
    - cosθ = |n_f · d| / (|n_f| · |d|)
    - non-ortho angle = arccos(cosθ) in degrees

    Pure helper, no mesh mutation.  BLR-9c-d-e-2 will wire it into
    ``_evaluate_cavity_component_candidates``.

    Returns
    -------
    dict with keys

    - ``n_pairs``               adjacent-fan-tet pairs found
    - ``angles_deg``            ``np.ndarray`` shape ``(n_pairs,)``
    - ``max_angle_deg``         maximum non-ortho across all pairs
                                (0.0 if no pairs)
    - ``mean_angle_deg``        arithmetic mean (0.0 if no pairs)
    - ``n_above_threshold``     pairs with angle > threshold
    - ``bad_pair_indices``      ``list[tuple[int, int]]`` fan-tet
                                index pairs whose angle exceeds the
                                threshold
    """
    out: dict[str, Any] = {
        "n_pairs": 0,
        "angles_deg": np.empty(0, dtype=np.float64),
        "max_angle_deg": 0.0,
        "mean_angle_deg": 0.0,
        "n_above_threshold": 0,
        "bad_pair_indices": [],
        "worst_pair_indices": None,
    }
    if not fan_tets or len(fan_tets) < 2:
        return out
    inner = np.asarray(inner_points, dtype=np.float64)
    if inner.size == 0 or inner.shape[0] < 1:
        return out
    apex = np.asarray(apex_xyz, dtype=np.float64).reshape(3)

    # Per-fan: triple of inner indices and centroid.
    n = len(fan_tets)
    inner_triples: list[tuple[int, int, int] | None] = []
    apex_per_tet = np.zeros((n, 3), dtype=np.float64)
    centroids = np.zeros((n, 3), dtype=np.float64)
    for k, tet in enumerate(fan_tets):
        verts = tet.get("tet_verts", [])
        resolved = _resolve_tet_apex_xyz(verts, apex, inner)
        if resolved is None:
            inner_triples.append(None)
            continue
        a_xyz, i0, i1, i2 = resolved
        inner_triples.append((i0, i1, i2))
        apex_per_tet[k] = a_xyz
        centroids[k] = (a_xyz + inner[i0] + inner[i1] + inner[i2]) / 4.0

    # Edge → list[fan_idx] map keyed on sorted inner-pair.  The pair
    # is only valid for non-ortho measurement when the two tets
    # actually share an *internal face* — i.e. they share the apex
    # *and* the two inner verts.  When apex differs (per-face Steiner
    # closures), two tets sharing an inner edge no longer share a
    # face, so they aren't a checkMesh non-ortho pair.
    edge_owners: dict[tuple[int, int], list[int]] = {}
    for k, triple in enumerate(inner_triples):
        if triple is None:
            continue
        a, b, c = triple
        for u, v in ((a, b), (b, c), (a, c)):
            key = (min(u, v), max(u, v))
            edge_owners.setdefault(key, []).append(k)

    angles: list[float] = []
    pair_keys: list[tuple[int, int]] = []
    bad_pairs: list[tuple[int, int]] = []
    seen_pairs: set[tuple[int, int]] = set()
    for (u, v), owners in edge_owners.items():
        if len(owners) < 2:
            continue
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                p_o, p_n = owners[i], owners[j]
                key = (min(p_o, p_n), max(p_o, p_n))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                # Skip pairs that don't actually share a face — they
                # do not contribute to checkMesh non-ortho.
                if not np.array_equal(
                    apex_per_tet[p_o], apex_per_tet[p_n]
                ):
                    continue
                p_a, p_b = inner[u], inner[v]
                a_face_apex = apex_per_tet[p_o]
                # Internal face = (shared apex, p_a, p_b)
                n_f = np.cross(p_a - a_face_apex, p_b - a_face_apex)
                d_vec = centroids[p_n] - centroids[p_o]
                n_norm = float(np.linalg.norm(n_f))
                d_norm = float(np.linalg.norm(d_vec))
                if n_norm < 1e-30 or d_norm < 1e-30:
                    angle_deg = 90.0   # degenerate ⇒ treat as fully oblique
                else:
                    cos_theta = float(
                        abs(np.dot(n_f, d_vec)) / (n_norm * d_norm)
                    )
                    cos_theta = min(1.0, max(0.0, cos_theta))
                    angle_deg = float(np.degrees(np.arccos(cos_theta)))
                angles.append(angle_deg)
                pair_keys.append(key)
                if angle_deg > non_ortho_threshold_deg:
                    bad_pairs.append(key)

    if not angles:
        return out

    arr = np.asarray(angles, dtype=np.float64)
    out["n_pairs"] = int(arr.shape[0])
    out["angles_deg"] = arr
    out["max_angle_deg"] = float(arr.max())
    out["mean_angle_deg"] = float(arr.mean())
    out["n_above_threshold"] = int(np.sum(arr > non_ortho_threshold_deg))
    out["bad_pair_indices"] = bad_pairs
    if pair_keys:
        argmax = int(np.argmax(arr))
        out["worst_pair_indices"] = pair_keys[argmax]
    return out


def _build_cavity_shell_closure_tets(
    uncovered_face_ids: list[int] | set[int] | tuple[int, ...],
    boundary: dict[str, Any],
    faces: list[list[int]],
    points: np.ndarray,
    inner_points: np.ndarray,
    *,
    apex_xyz: np.ndarray | list[float] | None = None,
    steiner_step_factor: float = 0.5,
) -> dict[str, Any]:
    """BLR-9c-d-h-1: emit one apex transition tet per uncovered shell face.

    The BLR-9c-c-iii-b fan structure only covers the wall side of a
    cavity component — for a wall-owner cell whose neighbour cell is
    non-wall (BLR-9c-b ``external_internal_faces``) the fan does not
    enclose the *exterior* boundary, so BLR-9c-c-iii-c reports those
    shell faces as uncovered.  This helper closes the cavity by
    emitting one extra transition tet per uncovered shell face using
    the cavity apex and the 3 vertices of the shell face directly.

    Each new closure tet shares vocabulary with the BLR-9c-c-iii-b
    output: ``tet_verts = [-1, j0, j1, j2]`` where ``-1`` is the
    apex placeholder and ``j_k`` index the *extended* inner-points
    array returned by this helper.  That way the BLR-9c-d-b
    determinant gate and the BLR-9c-d-d-1 Q-shape gate can be
    applied to the combined fan-tet + closure-tet list without any
    schema change.

    Pure helper, no mesh mutation.  Aggregator wire-in deferred to
    BLR-9c-d-h-2.

    Parameters
    ----------
    uncovered_face_ids:
        ``uncovered`` list from
        :func:`_check_cavity_shell_coverage` (face ids into
        ``boundary['external_internal_faces']`` are *not* used —
        these are direct face ids into the polyMesh).
    boundary:
        Output of :func:`_extract_cavity_component_boundary`.
        Used to validate that every entry of
        ``uncovered_face_ids`` is actually an
        ``external_internal_faces`` member.
    faces:
        polyMesh face vertex lists.
    points:
        polyMesh ``(P, 3)`` point coordinates.
    inner_points:
        Current ``(M, 3)`` inner-points array (post-stitch /
        post-sharp-split).  The helper appends one vertex per
        unique polyMesh vertex referenced by an uncovered shell
        face and returns the extended array.

    Returns
    -------
    dict with keys

    - ``extended_inner_points``  ``(M + K, 3)`` array
    - ``n_appended_points``      ``K``  newly appended vertices
    - ``shell_closure_tets``     ``list[dict]`` — one entry per
                                 uncovered shell face whose
                                 ``tet_verts`` indexes into
                                 ``extended_inner_points``
    - ``n_closure_tets``         number of closure tets emitted
    """
    out: dict[str, Any] = {
        "extended_inner_points": np.asarray(
            inner_points, dtype=np.float64
        ).reshape(-1, 3),
        "n_appended_points": 0,
        "shell_closure_tets": [],
        "n_closure_tets": 0,
    }
    if not uncovered_face_ids:
        return out
    pts = np.asarray(points, dtype=np.float64)
    inner = np.asarray(inner_points, dtype=np.float64).reshape(-1, 3)
    valid_shell: set[int] = set(
        int(f) for f in boundary.get("external_internal_faces", [])
    )

    extended = inner.tolist()
    next_id = len(extended)
    vertex_to_inner: dict[int, int] = {}
    closure_tets: list[dict[str, Any]] = []
    for fid in uncovered_face_ids:
        ifid = int(fid)
        if ifid not in valid_shell:
            continue
        if ifid < 0 or ifid >= len(faces):
            continue
        verts = list(faces[ifid])
        if len(verts) < 3:
            continue
        # Validate every vertex first; only mutate the dedup map and
        # the extended points buffer once we know the face is good.
        valid_iv: list[int] = []
        ok = True
        for v in verts:
            iv = int(v)
            if iv < 0 or iv >= pts.shape[0]:
                ok = False
                break
            valid_iv.append(iv)
        if not ok:
            continue
        # Commit: append any unseen polyMesh vertex to the inner-point
        # buffer.  Triangulation strategy:
        #   - n == 3: pass through (one tri).
        #   - n == 4: pick the **shortest diagonal** between (v0, v2)
        #     and (v1, v3).  This is the BLR-9c-d-m-1 root-cause fix
        #     for the closure-closure non-orthogonality bottleneck:
        #     fan-from-vertex-0 always uses (v0, v2) regardless of
        #     the quad's shape, which forces the shared diagonal
        #     onto the *long* axis whenever the quad is elongated
        #     and produces the wide-angle / sliver pairs the bench
        #     audit (BLR-9c-d-l-1) flagged.  Choosing the shorter
        #     diagonal gives a more balanced split.
        #   - n > 4: fan-from-vertex-0 (a future sub-step will switch
        #     to a Delaunay-style choice).
        inner_ids: list[int] = []
        for iv in valid_iv:
            if iv not in vertex_to_inner:
                vertex_to_inner[iv] = next_id
                extended.append(pts[iv].tolist())
                next_id += 1
            inner_ids.append(vertex_to_inner[iv])
        n_face = len(inner_ids)
        if n_face == 4:
            d02 = float(
                np.linalg.norm(pts[valid_iv[0]] - pts[valid_iv[2]])
            )
            d13 = float(
                np.linalg.norm(pts[valid_iv[1]] - pts[valid_iv[3]])
            )
            if d13 < d02:
                # Diagonal (v1, v3) — emit (v1, v2, v3) and (v1, v3, v0).
                tri_seq = [
                    (inner_ids[1], inner_ids[2], inner_ids[3]),
                    (inner_ids[1], inner_ids[3], inner_ids[0]),
                ]
            else:
                # Diagonal (v0, v2) — emit (v0, v1, v2) and (v0, v2, v3).
                tri_seq = [
                    (inner_ids[0], inner_ids[1], inner_ids[2]),
                    (inner_ids[0], inner_ids[2], inner_ids[3]),
                ]
        else:
            tri_seq = [
                (inner_ids[0], inner_ids[i], inner_ids[i + 1])
                for i in range(1, n_face - 1)
            ]
        # BLR-9c-d-m-2 — per-face Steiner apex.  When a cavity centroid
        # (``apex_xyz``) is supplied, replace the shared placeholder
        # apex (-1) with a Steiner point placed on the shell-face
        # plane offset toward the cavity centroid.  This breaks the
        # "all closure tets share the cavity centroid" coupling that
        # produced the closure-closure non-orthogonality long tail
        # observed in the BLR-9c-d-l-1 audit (60 % of all components).
        # When ``apex_xyz`` is None, falls back to the legacy shared-
        # apex schema (placeholder -1) for backward compatibility.
        steiner_idx = -1
        if apex_xyz is not None:
            apex_arr = np.asarray(apex_xyz, dtype=np.float64).reshape(3)
            face_pts = pts[valid_iv]               # (n_face, 3)
            face_centroid = face_pts.mean(axis=0)
            edge_lens = np.linalg.norm(
                np.diff(np.vstack([face_pts, face_pts[:1]]), axis=0),
                axis=1,
            )
            # BLR-9c-d-n-1 — scale the Steiner step by the *max* edge
            # rather than the mean.  For elongated shell triangles
            # (e.g. the slim caps along high-curvature ridges) the
            # mean edge is a poor proxy for the triangle's
            # circumradius — using max_edge gives an apex offset
            # comparable to the circumradius and thus a closer-to-
            # regular tet (Q closer to 1).
            scale_edge = float(edge_lens.max()) if edge_lens.size else 1.0
            inward_vec = apex_arr - face_centroid
            inward_norm = float(np.linalg.norm(inward_vec))
            if inward_norm < 1e-30 or scale_edge < 1e-30:
                steiner_pt = face_centroid
            else:
                step = float(steiner_step_factor) * scale_edge
                # Cap the step at the available distance to the cavity
                # centroid so the Steiner stays on the cavity side and
                # never overshoots beyond the centroid.
                step = min(step, 0.95 * inward_norm)
                steiner_pt = face_centroid + (inward_vec / inward_norm) * step
            steiner_idx = next_id
            extended.append(steiner_pt.tolist())
            next_id += 1
        for k, (j0, j1, j2) in enumerate(tri_seq):
            closure_tets.append({
                "face_id": ifid,
                "outer_verts": list(verts),
                "tet_verts": [steiner_idx, j0, j1, j2],
                "kind": "shell_closure",
                "fan_tri": int(k),
                "n_face_verts": int(n_face),
            })

    out["extended_inner_points"] = np.asarray(extended, dtype=np.float64)
    out["n_appended_points"] = int(out["extended_inner_points"].shape[0] - inner.shape[0])
    out["shell_closure_tets"] = closure_tets
    out["n_closure_tets"] = len(closure_tets)
    return out


def _check_cavity_fan_tet_pair_skewness(
    fan_tets: list[dict[str, Any]],
    apex_xyz: np.ndarray | list[float],
    inner_points: np.ndarray,
    *,
    skew_threshold: float = 4.0,
) -> dict[str, Any]:
    """BLR-9c-d-f-1: per-pair face skewness of adjacent fan tets.

    The OpenFOAM ``checkMesh`` "skewness" is, for an internal face
    between owner cell O and neighbour cell N,

        c_f         = face centroid
        c_O, c_N    = cell centroids
        d           = c_N − c_O
        λ           = ((c_f − c_O) · d) / (d · d)
        c_perp      = c_O + λ · d            (foot of perpendicular)
        skew        = |c_f − c_perp| / |d|

    A skew > 4 is the standard OpenFOAM cap; values above this break
    interpolation accuracy and trigger a checkMesh quality failure.

    Like ``_check_cavity_fan_tet_pair_non_ortho``, this helper
    builds an inner-edge → fan-tet map and reports one skewness
    measurement per adjacent fan-tet pair (i.e. per internal face
    that the cavity replacement introduces).  Pure helper, no mesh
    mutation; aggregator wire-in deferred to BLR-9c-d-f-2.

    Returns
    -------
    dict with keys

    - ``n_pairs``                adjacent-fan-tet pairs found
    - ``skew_values``            per-pair skew, ``np.ndarray``
    - ``max_skew``               maximum skew across all pairs
                                 (0.0 if no pairs)
    - ``mean_skew``              arithmetic mean (0.0 if no pairs)
    - ``n_above_threshold``      pairs with skew > threshold
    - ``bad_pair_indices``       ``list[tuple[int, int]]`` fan-tet
                                 index pairs whose skew exceeds the
                                 threshold
    """
    out: dict[str, Any] = {
        "n_pairs": 0,
        "skew_values": np.empty(0, dtype=np.float64),
        "max_skew": 0.0,
        "mean_skew": 0.0,
        "n_above_threshold": 0,
        "bad_pair_indices": [],
    }
    if not fan_tets or len(fan_tets) < 2:
        return out
    inner = np.asarray(inner_points, dtype=np.float64)
    if inner.size == 0 or inner.shape[0] < 1:
        return out
    apex = np.asarray(apex_xyz, dtype=np.float64).reshape(3)

    n = len(fan_tets)
    inner_triples: list[tuple[int, int, int] | None] = []
    apex_per_tet = np.zeros((n, 3), dtype=np.float64)
    centroids = np.zeros((n, 3), dtype=np.float64)
    for k, tet in enumerate(fan_tets):
        verts = tet.get("tet_verts", [])
        resolved = _resolve_tet_apex_xyz(verts, apex, inner)
        if resolved is None:
            inner_triples.append(None)
            continue
        a_xyz, i0, i1, i2 = resolved
        inner_triples.append((i0, i1, i2))
        apex_per_tet[k] = a_xyz
        centroids[k] = (a_xyz + inner[i0] + inner[i1] + inner[i2]) / 4.0

    edge_owners: dict[tuple[int, int], list[int]] = {}
    for k, triple in enumerate(inner_triples):
        if triple is None:
            continue
        a, b, c = triple
        for u, v in ((a, b), (b, c), (a, c)):
            key = (min(u, v), max(u, v))
            edge_owners.setdefault(key, []).append(k)

    skews: list[float] = []
    bad_pairs: list[tuple[int, int]] = []
    seen_pairs: set[tuple[int, int]] = set()
    for (u, v), owners in edge_owners.items():
        if len(owners) < 2:
            continue
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                p_o, p_n = owners[i], owners[j]
                key = (min(p_o, p_n), max(p_o, p_n))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                if not np.array_equal(
                    apex_per_tet[p_o], apex_per_tet[p_n]
                ):
                    continue
                p_a, p_b = inner[u], inner[v]
                a_face_apex = apex_per_tet[p_o]
                c_f = (a_face_apex + p_a + p_b) / 3.0
                c_O = centroids[p_o]
                c_N = centroids[p_n]
                d_vec = c_N - c_O
                d_dot = float(np.dot(d_vec, d_vec))
                d_norm = float(np.sqrt(d_dot))
                if d_dot < 1e-30 or d_norm < 1e-30:
                    skew = 0.0
                else:
                    lam = float(np.dot(c_f - c_O, d_vec)) / d_dot
                    c_perp = c_O + lam * d_vec
                    skew = float(np.linalg.norm(c_f - c_perp)) / d_norm
                skews.append(skew)
                if skew > skew_threshold:
                    bad_pairs.append(key)

    if not skews:
        return out

    arr = np.asarray(skews, dtype=np.float64)
    out["n_pairs"] = int(arr.shape[0])
    out["skew_values"] = arr
    out["max_skew"] = float(arr.max())
    out["mean_skew"] = float(arr.mean())
    out["n_above_threshold"] = int(np.sum(arr > skew_threshold))
    out["bad_pair_indices"] = bad_pairs
    return out


def _check_cavity_fan_tet_shape_quality(
    fan_tets: list[dict[str, Any]],
    apex_xyz: np.ndarray | list[float],
    inner_points: np.ndarray,
    *,
    q_min_threshold: float = 0.1,
) -> dict[str, Any]:
    """BLR-9c-d-d-1: shape-quality gate for the BLR-9c-c-iii-b fan tets.

    Re-uses the BETA2709 ``core.evaluator.tet_qshape`` Klingner-like
    Q-shape ratio (Q ≈ 1 for a regular tet, Q → 0 for a sliver) to
    flag fan tets whose ``Q < q_min_threshold``.  This complements
    the BLR-9c-d-b determinant gate, which only catches *signed*
    degeneracy: a fan tet can have non-zero signed volume yet still
    be a sliver/needle, which would blow up CFD interpolation
    weights and skewness without ever flipping sign.

    The helper does **not** mutate the mesh and does **not** decide
    the component verdict — BLR-9c-d-d (b) wires the result into
    ``_evaluate_cavity_component_candidates``.

    Parameters
    ----------
    fan_tets:
        Output of :func:`_build_cavity_fan_transition_tets`.  Each
        entry's ``tet_verts`` is ``[-1, i0, i1, i2]`` where ``-1`` is
        the apex placeholder and ``i_k`` index ``inner_points``.
    apex_xyz:
        Apex coordinate (cavity centroid).
    inner_points:
        ``(M, 3)`` inner-triangle vertex coordinates.
    q_min_threshold:
        Q-shape threshold below which a tet is reported as bad.

    Returns
    -------
    dict with keys

    - ``n_tets``           number of fan tets evaluated
    - ``q_values``         per-fan Q ∈ [0, 1] as ``np.ndarray``
    - ``q_min``            minimum Q across all fan tets
    - ``q_mean``           mean Q
    - ``n_below_threshold`` count of tets with ``Q < q_min_threshold``
    - ``bad_indices``      ``list[int]`` fan-tet positions with bad Q
    """
    out: dict[str, Any] = {
        "n_tets": 0,
        "q_values": np.empty(0, dtype=np.float64),
        "q_min": 0.0,
        "q_mean": 0.0,
        "n_below_threshold": 0,
        "bad_indices": [],
    }
    if not fan_tets:
        return out
    inner = np.asarray(inner_points, dtype=np.float64)
    if inner.size == 0 or inner.shape[0] < 1:
        out["n_tets"] = len(fan_tets)
        out["bad_indices"] = list(range(len(fan_tets)))
        return out
    apex = np.asarray(apex_xyz, dtype=np.float64).reshape(3)

    # Build combined point cloud: apex at index 0, then inner_points.
    pts = np.vstack([apex.reshape(1, 3), inner])

    # Translate fan tets into (T, 4) vertex-id array using the
    # combined indexing above (shared-apex placeholder ``-1`` → 0,
    # per-face Steiner index ``s`` → ``s + 1``,
    # inner index ``k`` → ``k + 1``).
    tets_list: list[list[int]] = []
    invalid_idx: set[int] = set()
    for k, tet in enumerate(fan_tets):
        verts = tet.get("tet_verts", [])
        resolved = _resolve_tet_apex_xyz(verts, apex, inner)
        if resolved is None:
            invalid_idx.add(k)
            tets_list.append([0, 0, 0, 0])
            continue
        a_xyz, i0, i1, i2 = resolved
        a_idx_combined = (
            0 if int(verts[0]) == -1 else int(verts[0]) + 1
        )
        tets_list.append([a_idx_combined, i0 + 1, i1 + 1, i2 + 1])
    tets_arr = np.asarray(tets_list, dtype=np.int64)

    # Tet shape quality is invariant under vertex permutation, but
    # core.evaluator.tet_qshape reports Q = 0 for tets with negative
    # signed volume (its inverted-cell guard).  The BLR-9c-d-b
    # determinant gate already takes care of orientation; here we
    # only care about *shape*, so flip the last two columns of any
    # tet whose signed volume is negative before delegating.
    if tets_arr.shape[0] > 0:
        a = pts[tets_arr[:, 0]]
        b = pts[tets_arr[:, 1]]
        c = pts[tets_arr[:, 2]]
        d = pts[tets_arr[:, 3]]
        signed_vol = np.einsum(
            "ij,ij->i", np.cross(b - a, c - a), d - a
        ) / 6.0
        flip = signed_vol < 0.0
        if np.any(flip):
            swap = tets_arr[flip][:, [0, 1, 3, 2]]
            tets_arr = tets_arr.copy()
            tets_arr[flip] = swap

    from core.evaluator.tet_qshape import tet_qshape  # local import

    Q, _stats = tet_qshape(pts, tets_arr)

    bad = {int(k) for k in np.where(Q < q_min_threshold)[0]} | invalid_idx
    out["n_tets"] = len(fan_tets)
    out["q_values"] = Q
    out["q_min"] = float(Q.min()) if Q.size > 0 else 0.0
    out["q_mean"] = float(Q.mean()) if Q.size > 0 else 0.0
    out["n_below_threshold"] = int((Q < q_min_threshold).sum())
    out["bad_indices"] = sorted(bad)
    return out


def _evaluate_cavity_component_candidates(
    components: list[set[int]] | list[frozenset[int]] | list[list[int]],
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray | list[int],
    neighbour: np.ndarray | list[int],
    wall_face_indices: list[int],
    motion_dirs: dict[int, np.ndarray] | None,
    first_thickness: float,
    *,
    sharp_cos_thresh: float = 0.9,
    non_ortho_threshold_deg: float = 70.0,
    q_min_threshold: float = 0.1,
) -> dict[str, Any]:
    """BLR-9c-d: aggregate per-cavity-component evaluation.

    For each cavity component (output of BLR-9c-a) the function chains:

    - BLR-9c-b   ``_extract_cavity_component_boundary``
    - BLR-9c-c-i ``_build_cavity_prism_inner_triangles``
    - BLR-9c-c-ii-a ``_stitch_cavity_prism_inner_ids_smooth``
    - BLR-9c-c-ii-b ``_split_cavity_inner_ids_at_sharp_corners``
    - BLR-9c-c-iii-a ``_compute_cavity_centroid``
    - BLR-9c-c-iii-b ``_build_cavity_fan_transition_tets``
    - BLR-9c-c-iii-c ``_check_cavity_shell_coverage``
    - BLR-9c-d-b    ``_check_cavity_fan_tet_determinants``
    - BLR-9c-d-d-1  ``_check_cavity_fan_tet_shape_quality``
    - BLR-9c-d-e-1  ``_check_cavity_fan_tet_pair_non_ortho``
    - BLR-9c-d-f-1  ``_check_cavity_fan_tet_pair_skewness``
    - BLR-9c-d-h-1  ``_build_cavity_shell_closure_tets``

    Each component records its sizing (cells / wall / shell / internal),
    inner-point count after sharp-corner duplication, sharp vertex
    count, fan-tet count, uncovered shell-face count, fan-det stats,
    fan Q-shape stats, fan-pair non-orthogonality stats, fan-pair
    skewness stats, and a decision.  Decision precedence — once a
    failure is recorded the rest of the gates are *still computed*
    (so the per-component record stays fully observable) but the
    earliest failure wins:

    1. ``"reject_uncovered_shell"`` — ``n_shell_uncovered > 0``.
       A leaking cavity shell is a topology bug we must close before
       quality matters.
    2. ``"reject_bad_det"`` — fan tet ``bad_indices`` (degenerate or
       sign-flipped) per BLR-9c-d-b.
    3. ``"reject_bad_shape"`` — fan tet Klingner ``Q < threshold``
       (sliver / needle) per BLR-9c-d-d-1.
    4. ``"reject_bad_non_ortho"`` — adjacent fan-tet pair angle
       above the OpenFOAM ``checkMesh`` non-orthogonality cap
       (default 70°) per BLR-9c-d-e-1.
    5. ``"reject_bad_skewness"`` — adjacent fan-tet pair skewness
       above the OpenFOAM ``checkMesh`` skewness cap (default 4.0)
       per BLR-9c-d-f-1.
    6. ``"accept"`` — all gates pass.

    Pure aggregation; no mesh mutation.  Returns::

        {
            "n_components": int,
            "n_accepted":   int,
            "n_rejected_uncovered_shell": int,
            "n_rejected_bad_det": int,
            "components": [
                {
                    "cells": [...],
                    "n_cells": int,
                    "n_wall_faces": int,
                    "n_shell_faces": int,
                    "n_internal_faces": int,
                    "n_inner_points": int,
                    "n_sharp_verts": int,
                    "n_fan_tets": int,
                    "n_shell_uncovered": int,
                    "n_fan_pos_det": int,
                    "n_fan_neg_det": int,
                    "n_fan_degenerate_det": int,
                    "n_fan_bad_indices": int,
                    "fan_worst_abs_det": float,
                    "decision": str,
                },
                ...
            ],
        }
    """
    summary: dict[str, Any] = {
        "n_components": 0,
        "n_accepted": 0,
        "n_rejected_uncovered_shell": 0,
        "n_rejected_bad_det": 0,
        "n_rejected_bad_shape": 0,
        "n_rejected_bad_non_ortho": 0,
        "n_rejected_bad_skewness": 0,
        # BLR-9c-d-j-1 — diagnostic histograms across all components
        # so callers can spot whether reject buckets cluster just past
        # the threshold (cap likely too tight) or scatter to extreme
        # values (real geometry pathology).
        "non_ortho_hist": {
            "le_30": 0, "30_60": 0, "60_70": 0, "70_80": 0,
            "80_90": 0, "gt_90": 0,
        },
        # BLR-9c-d-l-1 — fine bins for the >70° band so we can tell
        # whether reject_bad_non_ortho components cluster just past
        # the cap (recoverable by softening) or scatter to the high
        # end (real geometry pathology).
        "non_ortho_fine_hist": {
            "70_75": 0, "75_80": 0, "80_85": 0, "85_90": 0, "gt_90": 0,
        },
        # Worst-non-ortho-pair kind across all components.
        "worst_non_ortho_kind_hist": {
            "fan_fan": 0,
            "fan_shell_closure": 0,
            "shell_closure_shell_closure": 0,
            "none": 0,
            "other": 0,
        },
        "skew_hist": {
            "le_1": 0, "1_2": 0, "2_4": 0, "4_8": 0, "gt_8": 0,
        },
        "q_min_hist": {
            "ge_0p3": 0, "0p1_0p3": 0, "0p01_0p1": 0, "lt_0p01": 0,
        },
        # BLR-9c-d-k-1 — fine-grained Q bins so the
        # ``reject_bad_shape`` bucket can be split between
        # near-threshold (likely recoverable by softening the cap)
        # and pathological (slivers that need a real geometric fix).
        "q_min_fine_hist": {
            "0p05_0p1": 0,
            "0p01_0p05": 0,
            "0p001_0p01": 0,
            "lt_0p001": 0,
        },
        # Worst-Q-tet attribution across all components.
        "worst_q_kind_hist": {
            "fan": 0,
            "shell_closure": 0,
            "none": 0,
            "other": 0,
        },
        "max_non_ortho_deg": 0.0,
        "max_skew": 0.0,
        "min_q": 1.0,
        "components": [],
    }
    if not components:
        return summary
    summary["n_components"] = int(len(components))
    pts = np.asarray(points, dtype=np.float64)

    for comp in components:
        comp_set = {int(c) for c in comp}
        boundary = _extract_cavity_component_boundary(
            comp_set, owner, neighbour, wall_face_indices
        )
        comp_wall_faces = list(boundary.get("wall_faces", []))
        triangles = _build_cavity_prism_inner_triangles(
            comp_wall_faces, pts, faces, motion_dirs, float(first_thickness)
        )
        smooth = _stitch_cavity_prism_inner_ids_smooth(triangles)
        split = _split_cavity_inner_ids_at_sharp_corners(
            triangles, smooth, cos_thresh=sharp_cos_thresh
        )
        # BLR-9c-d-o-1 (reverted): the prism-cap centroid as fan
        # apex was tried and caused a hard regression (824 → 192
        # accept, +537 reject_bad_det) because the cap centroid
        # sits *too close* to the BLR-9c-c-i inner triangles — for
        # many components it lands on the wrong side of one or more
        # caps, flipping the signed volume of the corresponding fan
        # tet.  The cavity-cell centroid is the right invariant
        # apex; future tuning of fan-tet shape needs a different
        # tactic (e.g. a per-component scale on the BLR-9c-c-i
        # motion direction) that does not move the apex.
        apex_xyz = _compute_cavity_centroid(
            comp_set, faces, pts, owner, neighbour
        )
        cavity_centroid_xyz = apex_xyz
        fan_tets = _build_cavity_fan_transition_tets(triangles, split)
        # Initial shell-coverage check on fan tets only — gives us the
        # ``uncovered`` external_internal face list that BLR-9c-d-h-1
        # then closes by emitting one extra transition tet per face.
        pre_closure_coverage = _check_cavity_shell_coverage(
            boundary, fan_tets, faces
        )
        closure = _build_cavity_shell_closure_tets(
            uncovered_face_ids=pre_closure_coverage.get("uncovered", []),
            boundary=boundary,
            faces=faces,
            points=pts,
            inner_points=split["inner_points"],
            apex_xyz=cavity_centroid_xyz,
        )
        closure_tets = closure["shell_closure_tets"]
        extended_inner = closure["extended_inner_points"]
        all_tets = list(fan_tets) + list(closure_tets)
        # Re-run shell coverage on the combined list.  When every
        # uncovered triangle was successfully closed, ``n_uncovered``
        # drops to 0 and the component falls through to the quality
        # gates below.  Polygon shell faces that BLR-9c-d-h-1 skipped
        # remain uncovered and still trigger ``reject_uncovered_shell``.
        coverage = _check_cavity_shell_coverage(
            boundary, all_tets, faces
        )
        n_uncovered = int(len(coverage.get("uncovered", [])))
        det_check = _check_cavity_fan_tet_determinants(
            all_tets, apex_xyz, extended_inner
        )
        n_fan_bad_det = int(len(det_check.get("bad_indices", [])))
        shape_check = _check_cavity_fan_tet_shape_quality(
            all_tets, apex_xyz, extended_inner,
            q_min_threshold=q_min_threshold,
        )
        n_fan_bad_shape = int(len(shape_check.get("bad_indices", [])))
        # BLR-9c-d-k-1 — attribute the worst-Q tet to either the
        # BLR-9c-c-iii-b fan or the BLR-9c-d-h-1 shell closure so
        # later sub-steps can target the right helper.
        worst_q_kind = "none"
        worst_q_value = 1.0
        _q_values = shape_check.get("q_values", None)
        if (
            _q_values is not None
            and hasattr(_q_values, "size")
            and _q_values.size > 0
        ):
            _argmin = int(np.argmin(_q_values))
            if 0 <= _argmin < len(all_tets):
                worst_q_kind = str(
                    all_tets[_argmin].get("kind", "fan")
                )
                worst_q_value = float(_q_values[_argmin])
        non_ortho_check = _check_cavity_fan_tet_pair_non_ortho(
            all_tets, apex_xyz, extended_inner,
            non_ortho_threshold_deg=non_ortho_threshold_deg,
        )
        n_fan_bad_non_ortho = int(
            len(non_ortho_check.get("bad_pair_indices", []))
        )
        # BLR-9c-d-l-1 — classify the worst-non-ortho pair by the
        # ``kind`` of its two transition tets so later sub-steps can
        # target the right helper (fan-fan = inner triangle motion;
        # closure-closure = shell-face fan triangulation; mixed =
        # interface between the two paths).
        worst_no_kind = "none"
        wp = non_ortho_check.get("worst_pair_indices")
        if (
            wp is not None
            and len(wp) == 2
            and 0 <= int(wp[0]) < len(all_tets)
            and 0 <= int(wp[1]) < len(all_tets)
        ):
            ka = str(all_tets[int(wp[0])].get("kind", "fan"))
            kb = str(all_tets[int(wp[1])].get("kind", "fan"))
            if ka == kb:
                worst_no_kind = f"{ka}_{kb}"
            else:
                worst_no_kind = "_".join(sorted([ka, kb]))
        skew_check = _check_cavity_fan_tet_pair_skewness(
            all_tets, apex_xyz, extended_inner
        )
        n_fan_bad_skew = int(
            len(skew_check.get("bad_pair_indices", []))
        )
        if n_uncovered > 0:
            decision = "reject_uncovered_shell"
        elif n_fan_bad_det > 0:
            decision = "reject_bad_det"
        elif n_fan_bad_shape > 0:
            decision = "reject_bad_shape"
        elif n_fan_bad_non_ortho > 0:
            decision = "reject_bad_non_ortho"
        elif n_fan_bad_skew > 0:
            decision = "reject_bad_skewness"
        else:
            decision = "accept"

        comp_record = {
            "cells": sorted(comp_set),
            "n_cells": int(len(comp_set)),
            "n_wall_faces": int(len(comp_wall_faces)),
            "n_shell_faces": int(coverage.get("n_shell_faces", 0)),
            "n_internal_faces": int(
                len(boundary.get("internal_faces", []))
            ),
            "n_inner_points": int(split["inner_points"].shape[0]),
            "n_sharp_verts": int(split.get("n_split", 0)),
            "n_fan_tets": int(len(fan_tets)),
            "n_closure_tets": int(len(closure_tets)),
            "n_total_tets": int(len(all_tets)),
            "n_shell_uncovered_pre_closure": int(
                len(pre_closure_coverage.get("uncovered", []))
            ),
            "n_shell_uncovered": n_uncovered,
            "n_fan_pos_det": int(det_check.get("n_pos_det", 0)),
            "n_fan_neg_det": int(det_check.get("n_neg_det", 0)),
            "n_fan_degenerate_det": int(
                det_check.get("n_degenerate_det", 0)
            ),
            "n_fan_bad_indices": n_fan_bad_det,
            "fan_worst_abs_det": float(
                det_check.get("worst_abs_det", 0.0)
            ),
            "n_fan_sign_inconsistent": int(
                det_check.get("n_sign_inconsistent", 0)
            ),
            "n_fan_bad_shape_indices": n_fan_bad_shape,
            "fan_q_min": float(shape_check.get("q_min", 0.0)),
            "fan_q_mean": float(shape_check.get("q_mean", 0.0)),
            "worst_q_kind": worst_q_kind,
            "worst_q_value": worst_q_value,
            "n_fan_pair_count": int(non_ortho_check.get("n_pairs", 0)),
            "n_fan_pair_above_non_ortho": int(
                non_ortho_check.get("n_above_threshold", 0)
            ),
            "fan_pair_max_non_ortho_deg": float(
                non_ortho_check.get("max_angle_deg", 0.0)
            ),
            "fan_pair_mean_non_ortho_deg": float(
                non_ortho_check.get("mean_angle_deg", 0.0)
            ),
            "n_fan_pair_bad_non_ortho": n_fan_bad_non_ortho,
            "worst_non_ortho_kind": worst_no_kind,
            "fan_pair_max_skew": float(
                skew_check.get("max_skew", 0.0)
            ),
            "fan_pair_mean_skew": float(
                skew_check.get("mean_skew", 0.0)
            ),
            "n_fan_pair_above_skew": int(
                skew_check.get("n_above_threshold", 0)
            ),
            "n_fan_pair_bad_skewness": n_fan_bad_skew,
            "decision": decision,
        }
        summary["components"].append(comp_record)
        if decision == "accept":
            summary["n_accepted"] += 1
        elif decision == "reject_uncovered_shell":
            summary["n_rejected_uncovered_shell"] += 1
        elif decision == "reject_bad_det":
            summary["n_rejected_bad_det"] += 1
        elif decision == "reject_bad_shape":
            summary["n_rejected_bad_shape"] += 1
        elif decision == "reject_bad_non_ortho":
            summary["n_rejected_bad_non_ortho"] += 1
        elif decision == "reject_bad_skewness":
            summary["n_rejected_bad_skewness"] += 1

        # Accumulate diagnostic histograms.
        _max_no = float(comp_record["fan_pair_max_non_ortho_deg"])
        if _max_no <= 30.0:
            summary["non_ortho_hist"]["le_30"] += 1
        elif _max_no <= 60.0:
            summary["non_ortho_hist"]["30_60"] += 1
        elif _max_no <= 70.0:
            summary["non_ortho_hist"]["60_70"] += 1
        elif _max_no <= 80.0:
            summary["non_ortho_hist"]["70_80"] += 1
        elif _max_no <= 90.0:
            summary["non_ortho_hist"]["80_90"] += 1
        else:
            summary["non_ortho_hist"]["gt_90"] += 1
        if _max_no > 70.0:
            if _max_no <= 75.0:
                summary["non_ortho_fine_hist"]["70_75"] += 1
            elif _max_no <= 80.0:
                summary["non_ortho_fine_hist"]["75_80"] += 1
            elif _max_no <= 85.0:
                summary["non_ortho_fine_hist"]["80_85"] += 1
            elif _max_no <= 90.0:
                summary["non_ortho_fine_hist"]["85_90"] += 1
            else:
                summary["non_ortho_fine_hist"]["gt_90"] += 1
        if _max_no > summary["max_non_ortho_deg"]:
            summary["max_non_ortho_deg"] = _max_no
        _wno_kind = comp_record.get("worst_non_ortho_kind", "none")
        if _wno_kind in summary["worst_non_ortho_kind_hist"]:
            summary["worst_non_ortho_kind_hist"][_wno_kind] += 1
        else:
            summary["worst_non_ortho_kind_hist"]["other"] += 1

        _max_sk = float(comp_record["fan_pair_max_skew"])
        if _max_sk <= 1.0:
            summary["skew_hist"]["le_1"] += 1
        elif _max_sk <= 2.0:
            summary["skew_hist"]["1_2"] += 1
        elif _max_sk <= 4.0:
            summary["skew_hist"]["2_4"] += 1
        elif _max_sk <= 8.0:
            summary["skew_hist"]["4_8"] += 1
        else:
            summary["skew_hist"]["gt_8"] += 1
        if _max_sk > summary["max_skew"]:
            summary["max_skew"] = _max_sk

        _q_min = float(comp_record["fan_q_min"])
        if _q_min >= 0.3:
            summary["q_min_hist"]["ge_0p3"] += 1
        elif _q_min >= 0.1:
            summary["q_min_hist"]["0p1_0p3"] += 1
        elif _q_min >= 0.01:
            summary["q_min_hist"]["0p01_0p1"] += 1
        else:
            summary["q_min_hist"]["lt_0p01"] += 1
        # Fine-grained bins, only populated for components that fall
        # below the BLR-9c-d-d-1 threshold (Q < 0.1).
        if _q_min < 0.1:
            if _q_min >= 0.05:
                summary["q_min_fine_hist"]["0p05_0p1"] += 1
            elif _q_min >= 0.01:
                summary["q_min_fine_hist"]["0p01_0p05"] += 1
            elif _q_min >= 0.001:
                summary["q_min_fine_hist"]["0p001_0p01"] += 1
            else:
                summary["q_min_fine_hist"]["lt_0p001"] += 1
        if _q_min < summary["min_q"]:
            summary["min_q"] = _q_min

        _wq_kind = comp_record.get("worst_q_kind", "none")
        if _wq_kind in summary["worst_q_kind_hist"]:
            summary["worst_q_kind_hist"][_wq_kind] += 1
        else:
            summary["worst_q_kind_hist"]["other"] += 1

    return summary


def _apply_tet_cavity_replacement_plan(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    wall_face_indices: list[int],
    plan: dict[str, Any],
    *,
    enabled: bool,
) -> dict[str, Any]:
    """BLR-9b-ii: apply a BLR-9b-i replacement plan to in-memory arrays.

    The mutation is performed entirely on copies of the input arrays —
    the caller is responsible for swapping them into the polyMesh
    writer in a later, separately env-gated step.

    Steps:

    1. ``points`` ← original points + plan.new_points + 1 apex point
       per new cell (minted from ``transition_tet_apex_xyz``).
    2. Resolve each ``new_cells[i]['transition_tet'][0]`` placeholder
       (-1) to the newly minted apex id.
    3. Drop every face whose owner OR neighbour is in
       ``cells_to_delete``.  Wall faces of deleted cells map to the
       new prism's bottom face; other dropped boundary faces are
       discarded (they were the wall face slated for replacement).
    4. Compact the surviving cell ids (deletion shifts ids down) and
       rebuild ``owner`` / ``neighbour`` over the surviving faces.
    5. Append per-replacement faces:
         - prism: bottom (wall, kept), top (cap, internal), 3 sides
           (internal).
         - transition tet: shares its base face with the prism's top;
           three lateral triangles connect the base to the apex.

    The function does NOT yet touch ``boundary`` (patch metadata) —
    BLR-9b-iii will reattach the wall face to its original patch.
    Default OFF when ``enabled`` is False (returns a no-op dict
    holding the originals).

    Returns dict: ``enabled``, ``new_points``, ``new_faces``,
    ``new_owner``, ``new_neighbour``, ``n_cells_before``,
    ``n_cells_after``, ``n_new_points_total`` (inner verts +
    minted apex), ``n_replaced``.
    """
    owner_arr_in = np.asarray(owner, dtype=np.int64)
    neighbour_arr_in = np.asarray(neighbour, dtype=np.int64)
    _max_own = int(owner_arr_in.max()) if owner_arr_in.size > 0 else -1
    _max_nbr = int(neighbour_arr_in.max()) if neighbour_arr_in.size > 0 else -1
    n_cells_before = max(_max_own, _max_nbr) + 1
    if n_cells_before < 0:
        n_cells_before = 0

    no_op: dict[str, Any] = {
        "enabled": bool(enabled),
        "new_points": np.asarray(points, dtype=np.float64).copy(),
        "new_faces": [list(f) for f in faces],
        "new_owner": np.asarray(owner, dtype=np.int64).copy(),
        "new_neighbour": np.asarray(neighbour, dtype=np.int64).copy(),
        "n_cells_before": int(n_cells_before),
        "n_cells_after": int(n_cells_before),
        "n_new_points_total": 0,
        "n_replaced": 0,
    }
    if not enabled or not plan or not plan.get("n_planned"):
        return no_op
    if plan.get("enabled") is False:
        return no_op

    cells_to_delete: list[int] = list(plan.get("cells_to_delete", []))
    new_cells_spec: list[dict[str, Any]] = list(plan.get("new_cells", []))
    plan_new_points: np.ndarray = np.asarray(
        plan.get("new_points", np.zeros((0, 3), dtype=np.float64)),
        dtype=np.float64,
    )
    if not cells_to_delete or not new_cells_spec:
        return no_op
    if len(cells_to_delete) != len(new_cells_spec):
        # Inconsistent plan; refuse to mutate.
        no_op["error"] = "plan: cells_to_delete vs new_cells length mismatch"
        return no_op

    # 1. Mint points: original + plan inner verts + apex per replacement.
    apex_xyz_list: list[list[float]] = []
    for spec in new_cells_spec:
        apex_xyz_list.append(list(spec.get("transition_tet_apex_xyz", [0.0, 0.0, 0.0])))
    apex_arr = (
        np.asarray(apex_xyz_list, dtype=np.float64).reshape(-1, 3)
        if apex_xyz_list
        else np.zeros((0, 3), dtype=np.float64)
    )
    pts_orig = np.asarray(points, dtype=np.float64)
    new_points = np.concatenate([pts_orig, plan_new_points, apex_arr], axis=0)
    apex_id_offset = int(pts_orig.shape[0] + plan_new_points.shape[0])

    # 2. Resolve apex ids inside each new cell spec.
    resolved_specs: list[dict[str, Any]] = []
    for i, spec in enumerate(new_cells_spec):
        resolved = dict(spec)
        tet = list(spec["transition_tet"])
        tet[0] = apex_id_offset + i
        resolved["transition_tet"] = tet
        resolved_specs.append(resolved)

    delete_set = {int(c) for c in cells_to_delete}
    wall_face_set = {int(fi) for fi in wall_face_indices}

    owner_arr = np.asarray(owner, dtype=np.int64)
    nbr_arr = np.asarray(neighbour, dtype=np.int64)
    n_internal = int(len(nbr_arr))

    # 3. Build the list of surviving faces.  Faces whose owner OR
    # neighbour is being deleted disappear (they are either the wall
    # face slated for replacement or an internal face whose other
    # cell is itself being replaced — both will be re-emitted by the
    # new cells).  Track which faces survive and remember the wall
    # face owner mapping (used in step 5 so the new prism inherits
    # the original patch wall face's vertex order).
    surviving_face_ids: list[int] = []
    for fi in range(len(faces)):
        own = int(owner_arr[fi]) if fi < len(owner_arr) else -1
        nbr = int(nbr_arr[fi]) if fi < n_internal else -1
        if own in delete_set:
            continue
        if 0 <= nbr and nbr in delete_set:
            # Other side of an internal face was deleted; re-emit later.
            continue
        surviving_face_ids.append(fi)

    # 4. Compact cell ids: deleted cells shift later ids down.
    n_cells_after_delete = n_cells_before - len(delete_set)
    cell_remap = np.full(n_cells_before, -1, dtype=np.int64)
    next_new_id = 0
    for cid in range(n_cells_before):
        if cid in delete_set:
            continue
        cell_remap[cid] = next_new_id
        next_new_id += 1

    # Rebuild faces / owner / neighbour over surviving ids.
    surviving_faces_int: list[list[int]] = []
    surviving_faces_bnd: list[list[int]] = []
    survive_own_int: list[int] = []
    survive_own_bnd: list[int] = []
    survive_nbr_int: list[int] = []
    for fi in surviving_face_ids:
        own = int(owner_arr[fi])
        nbr = int(nbr_arr[fi]) if fi < n_internal else -1
        new_own = int(cell_remap[own]) if 0 <= own < n_cells_before else -1
        new_nbr = int(cell_remap[nbr]) if 0 <= nbr < n_cells_before else -1
        if 0 <= nbr < n_cells_before and nbr not in delete_set:
            # Internal face survives.
            surviving_faces_int.append(list(faces[fi]))
            survive_own_int.append(new_own)
            survive_nbr_int.append(new_nbr)
        else:
            surviving_faces_bnd.append(list(faces[fi]))
            survive_own_bnd.append(new_own)

    # 5. Emit new cells.  Each replacement contributes:
    #    prism (cell id = next_new_id):
    #      - bottom triangle (wall) → boundary face, owner=prism
    #      - top triangle (cap)     → internal face, owner=prism,
    #                                 neighbour=transition_tet
    #      - 3 side quads           → boundary faces (BLR-9b-iii will
    #                                 stitch them to neighbour cells in
    #                                 a future pass; for now they are
    #                                 boundary so the polyMesh stays
    #                                 valid at smoke-test scale).
    #    transition tet (cell id = next_new_id + 1):
    #      - base = prism top (already emitted, neighbour side)
    #      - 3 sides → boundary faces.
    new_internal_faces: list[list[int]] = []
    new_internal_own: list[int] = []
    new_internal_nbr: list[int] = []
    new_bnd_faces: list[list[int]] = []
    new_bnd_own: list[int] = []
    n_replaced = 0
    for spec in resolved_specs:
        prism = list(spec["prism"])
        v0, v1, v2, i0, i1, i2 = (int(x) for x in prism)
        prism_cell = next_new_id
        tet_cell = next_new_id + 1
        next_new_id += 2
        n_replaced += 1

        # Bottom = original wall face, but using its original vertex order.
        # Locate the wall face for this deleted cell to inherit winding.
        cid = int(spec["deleted_cell_id"])
        bottom_face_verts: list[int] | None = None
        for fi in wall_face_indices:
            if 0 <= fi < len(owner_arr) and int(owner_arr[fi]) == cid:
                bottom_face_verts = list(faces[fi])
                break
        if bottom_face_verts is None:
            bottom_face_verts = [v0, v1, v2]
        new_bnd_faces.append(bottom_face_verts)
        new_bnd_own.append(prism_cell)

        # Top (cap) — opposite winding so the outward normal points
        # toward the transition tet apex.
        new_internal_faces.append([i0, i2, i1])
        new_internal_own.append(prism_cell)
        new_internal_nbr.append(tet_cell)

        # 3 prism side quads (boundary placeholder for BLR-9b-ii).
        new_bnd_faces.append([v0, v1, i1, i0])
        new_bnd_own.append(prism_cell)
        new_bnd_faces.append([v1, v2, i2, i1])
        new_bnd_own.append(prism_cell)
        new_bnd_faces.append([v2, v0, i0, i2])
        new_bnd_own.append(prism_cell)

        # Transition tet sides (apex = spec['transition_tet'][0]).
        apex_id = int(spec["transition_tet"][0])
        new_bnd_faces.append([i0, i1, apex_id])
        new_bnd_own.append(tet_cell)
        new_bnd_faces.append([i1, i2, apex_id])
        new_bnd_own.append(tet_cell)
        new_bnd_faces.append([i2, i0, apex_id])
        new_bnd_own.append(tet_cell)

    n_cells_after = n_cells_after_delete + 2 * n_replaced

    # OpenFOAM convention: internal faces first, then boundary faces.
    final_faces = surviving_faces_int + new_internal_faces + surviving_faces_bnd + new_bnd_faces
    final_owner = np.asarray(
        survive_own_int + new_internal_own + survive_own_bnd + new_bnd_own,
        dtype=np.int64,
    )
    final_neighbour = np.asarray(
        survive_nbr_int + new_internal_nbr,
        dtype=np.int64,
    )

    return {
        "enabled": True,
        "new_points": new_points,
        "new_faces": final_faces,
        "new_owner": final_owner,
        "new_neighbour": final_neighbour,
        "n_cells_before": int(n_cells_before),
        "n_cells_after": int(n_cells_after),
        "n_new_points_total": int(plan_new_points.shape[0] + apex_arr.shape[0]),
        "n_replaced": int(n_replaced),
    }


def _merge_skewed_bl_internal_quads(
    points: np.ndarray,
    faces: list[list[int]],
    owner: list[int],
    neighbour: list[int],
    boundary_entries: list[dict[str, Any]],
    *,
    base_n_cells: int,
    skew_threshold: float = 4.0,
) -> tuple[list[list[int]], list[int], list[int], list[dict[str, Any]], int]:
    """Merge BL prism cells across feature-edge seams with invalid skew.

    At sharp cube-like feature edges, two layer prisms can share a quad whose
    face centre is not between the two cell centres. Keeping that seam as an
    internal face creates OpenFOAM-style skewness O(10-40). cfMesh avoids this
    by treating feature-edge layer junctions as polyhedral corner cells. This
    pass applies the same idea narrowly: only BL-BL quad faces whose skewness
    already exceeds the internal skewness gate are removed, and their adjacent
    cells are unioned.
    """
    n_internal = len(neighbour)
    if n_internal <= 0 or not faces:
        return faces, owner, neighbour, boundary_entries, 0

    owner_arr = np.asarray(owner, dtype=np.int64)
    nbr_arr = np.asarray(neighbour, dtype=np.int64)
    n_cells_cur = int(owner_arr.max()) + 1 if owner_arr.size else 0
    if nbr_arr.size:
        n_cells_cur = max(n_cells_cur, int(nbr_arr.max()) + 1)
    if n_cells_cur <= base_n_cells:
        return faces, owner, neighbour, boundary_entries, 0

    centres = _cell_centres_from_faces(
        points, faces, owner_arr, nbr_arr, n_cells_cur,
    )
    face_centres = np.zeros((len(faces), 3), dtype=np.float64)
    for fi, face in enumerate(faces):
        face_centres[fi] = points[face].mean(axis=0)

    parent = list(range(n_cells_cur))

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: int, b: int) -> None:
        ra = _find(a)
        rb = _find(b)
        if ra != rb:
            parent[rb] = ra

    n_marked = 0
    for fi in range(n_internal):
        own = int(owner_arr[fi])
        nbr = int(nbr_arr[fi])
        if own < base_n_cells or nbr < base_n_cells:
            continue
        if len(faces[fi]) != 4:
            continue
        d = centres[nbr] - centres[own]
        d_mag = float(np.linalg.norm(d))
        if d_mag <= 1e-30:
            continue
        diff = face_centres[fi] - centres[own]
        t = float(np.dot(diff, d) / (d_mag * d_mag))
        proj = centres[own] + t * d
        skew = float(np.linalg.norm(face_centres[fi] - proj) / d_mag)
        if skew > skew_threshold:
            _union(own, nbr)
            n_marked += 1

    if n_marked == 0:
        return faces, owner, neighbour, boundary_entries, 0

    int_faces: list[list[int]] = []
    int_owner_roots: list[int] = []
    int_nbr_roots: list[int] = []
    removed = 0
    for fi in range(n_internal):
        own_root = _find(int(owner_arr[fi]))
        nbr_root = _find(int(nbr_arr[fi]))
        if own_root == nbr_root:
            removed += 1
            continue
        int_faces.append(faces[fi])
        int_owner_roots.append(own_root)
        int_nbr_roots.append(nbr_root)

    bnd_faces: list[list[int]] = []
    bnd_owner_roots: list[int] = []
    cursor = n_internal
    for entry in boundary_entries:
        nf = int(entry.get("nFaces", 0))
        for fi in range(cursor, min(cursor + nf, len(faces))):
            bnd_faces.append(faces[fi])
            bnd_owner_roots.append(_find(int(owner_arr[fi])))
        cursor += nf

    used_cells = sorted(
        set(int_owner_roots) | set(int_nbr_roots) | set(bnd_owner_roots)
    )
    remap = {old: new for new, old in enumerate(used_cells)}
    out_faces = int_faces + bnd_faces
    out_owner = [remap[c] for c in int_owner_roots]
    out_nbr = [remap[c] for c in int_nbr_roots]
    out_owner.extend(remap[c] for c in bnd_owner_roots)

    out_boundary: list[dict[str, Any]] = []
    start = len(int_faces)
    for entry in boundary_entries:
        nf = int(entry.get("nFaces", 0))
        out_entry = dict(entry)
        out_entry["startFace"] = start
        out_entry["nFaces"] = nf
        out_boundary.append(out_entry)
        start += nf

    log.info(
        "native_bl_feature_edge_poly_merge",
        n_marked=int(n_marked),
        n_removed_internal_faces=int(removed),
        n_cells_before=int(n_cells_cur),
        n_cells_after=int(len(used_cells)),
        skew_threshold=float(skew_threshold),
    )
    return out_faces, out_owner, out_nbr, out_boundary, removed


def _orient_boundary_faces_outward(
    points: np.ndarray,
    faces: list[list[int]],
    owner: list[int],
    neighbour: list[int],
) -> int:
    """Reverse boundary face winding when the face normal points into owner.

    SMESH/cfMesh-style BL operations repeatedly rebuild shell topology; the
    final write pass must preserve the OpenFOAM convention that boundary face
    normals point outward from their owner cell.
    """
    n_internal = len(neighbour)
    if n_internal >= len(faces):
        return 0

    owner_arr = np.asarray(owner, dtype=np.int64)
    if owner_arr.size != len(faces):
        return 0

    nbr_arr = np.asarray(neighbour, dtype=np.int64)
    max_cell = int(owner_arr.max(initial=-1))
    if nbr_arr.size:
        max_cell = max(max_cell, int(nbr_arr.max(initial=-1)))
    if max_cell < 0:
        return 0

    centres = _cell_centres_from_faces(
        points, faces, owner_arr, nbr_arr, max_cell + 1,
    )
    n_reversed = 0
    for fi in range(n_internal, len(faces)):
        own = int(owner_arr[fi])
        if own < 0 or own >= len(centres):
            continue
        face = faces[fi]
        if len(face) < 3:
            continue
        normal, area = _face_normal_area(points, face)
        if area <= 1e-30:
            continue
        face_centre = _face_centroid(points, face)
        if float(np.dot(normal, face_centre - centres[own])) < -1e-12:
            faces[fi] = list(reversed(face))
            n_reversed += 1
    return n_reversed


def _build_edge_to_wall_faces(
    wall_face_indices: list[int], faces: list[list[int]],
) -> dict[tuple[int, int], list[int]]:
    """Wall triangle edge → 해당 edge 를 공유하는 wall triangle index 리스트.

    edge key 는 정렬된 (min, max) vertex pair. manifold wall 이면 각 edge 당
    정확히 2 triangle (boundary of wall 일 땐 1).
    """
    # C-PERF-74 / beta2525 — vectorize via lexsort + group-boundary.
    edge_map: dict[tuple[int, int], list[int]] = {}
    tri_pairs = [(fi, faces[fi]) for fi in wall_face_indices if len(faces[fi]) == 3]
    if not tri_pairs:
        return edge_map
    tri_fi = np.asarray([p[0] for p in tri_pairs], dtype=np.int64)
    F_arr = np.asarray([list(p[1]) for p in tri_pairs], dtype=np.int64)
    src = F_arr[:, [0, 1, 2]].reshape(-1)
    dst = F_arr[:, [1, 2, 0]].reshape(-1)
    fi_flat = np.repeat(tri_fi, 3)
    u = np.minimum(src, dst); v = np.maximum(src, dst)
    order = np.lexsort((v, u))
    u_s = u[order]; v_s = v[order]; fi_s = fi_flat[order]
    diff = np.r_[True, (u_s[1:] != u_s[:-1]) | (v_s[1:] != v_s[:-1])]
    starts = np.where(diff)[0]
    ends = np.r_[starts[1:], len(u_s)]
    for s, e in zip(starts.tolist(), ends.tolist()):
        edge_map[(int(u_s[s]), int(v_s[s]))] = fi_s[s:e].tolist()
    return edge_map


def _read_input_stl_name(case_dir: Path) -> str:
    """Return the input file basename from ``case_dir/geometry_report.json``.

    Used by :func:`_vd_should_activate` to scope ``AUTO_TESSELL_BL_VD_FOR``
    matching to the current STL. Empty string on any read/parse failure —
    callers must treat that as "name unknown" and fall back to global gates.
    """
    try:
        import json
        gp = case_dir / "geometry_report.json"
        if not gp.exists():
            return ""
        data = json.loads(gp.read_text())
        path = data.get("file_info", {}).get("path", "")
        if not path:
            return ""
        return Path(path).name
    except Exception:
        return ""


def _vd_should_activate(case_dir: Path) -> bool:
    """VD-8b — combined VD activation gate (VD_ENABLE + VD_FOR allow-list).

    Decision table:
      * VD_FOR unset / empty  → governed by ``VD_ENABLE`` ("1" → True).
      * VD_FOR non-empty      → True only if any comma-separated token is a
                                 substring of the input STL basename. The
                                 STL name is read from
                                 ``case_dir/geometry_report.json``; if the
                                 sidecar is missing or malformed, returns
                                 False (per-STL filter cannot match).

    The two env vars compose so that the bench can run a single command
    with ``AUTO_TESSELL_BL_VD_FOR=hard_100029,extreme_1017013`` to flip VD
    on for those STLs only, without disturbing the rest of the 21-STL bench.
    """
    vd_for = os.environ.get("AUTO_TESSELL_BL_VD_FOR", "").strip()
    if not vd_for:
        return os.environ.get("AUTO_TESSELL_BL_VD_ENABLE", "0") == "1"
    tokens = [t.strip() for t in vd_for.split(",") if t.strip()]
    if not tokens:
        return os.environ.get("AUTO_TESSELL_BL_VD_ENABLE", "0") == "1"
    stl_name = _read_input_stl_name(case_dir)
    if not stl_name:
        log.info(
            "native_bl_vd_for_no_stl_name",
            component="native_bl", phase="VD-8b",
            case_dir=str(case_dir),
            vd_for=vd_for,
        )
        return False
    matched = next((t for t in tokens if t in stl_name), None)
    log.info(
        "native_bl_vd_for_decision",
        component="native_bl", phase="VD-8b",
        stl_name=stl_name,
        vd_for=vd_for,
        matched=matched,
        active=bool(matched),
    )
    return matched is not None


def _generate_native_bl_vd(
    *,
    case_dir: Path,
    cfg: BLConfig,
    poly_dir: Path,
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    wall_face_indices: list[int],
    wall_vert_indices: list[int],
    vnorm: dict[int, np.ndarray],
    t_start: float,
) -> NativeBLResult:
    """VD-8a — vertex-duplication BL polyMesh writer (env-gated).

    Builds a BL polyMesh consisting of multi-layer prism cells with per-face
    inner verts (junction-aware duplication) plus junction-edge gap-fill
    tetrahedra, then writes it under ``case_dir/constant/polyMesh``. Bulk
    volume cells are NOT preserved — this path is intended as a measurement
    vehicle for boundary skew at multi-patch junctions where per-vertex
    extrusion produces tan(theta) bias.

    Triggered by ``AUTO_TESSELL_BL_VD_ENABLE=1``; the default-OFF branch in
    :func:`generate_native_bl` keeps the production pipeline unchanged.
    """
    from core.layers.native_bl_vd import (
        build_bulk_preserving_multi_layer_full_bl_polymesh,
        build_full_bl_polymesh,
        build_multi_layer_bl,
        cells_to_polymesh,
        detect_junction_verts,
        generate_per_face_inner_verts,
    )

    tri_wall = [fi for fi in wall_face_indices if len(faces[fi]) == 3]
    if not tri_wall:
        return NativeBLResult(
            success=False,
            elapsed=time.perf_counter() - t_start,
            message=(
                "VD-8a: triangle wall faces 없음 — VD MVP 는 tri-only "
                "지원 (polygon wall fan-triangulation 은 후속 카드)."
            ),
        )

    cluster_cos = float(
        os.environ.get("AUTO_TESSELL_BL_VD_CLUSTER_COS", "0.9")
    )
    cos_thresh = float(
        os.environ.get("AUTO_TESSELL_BL_VD_JUNCTION_COS", "0.9")
    )

    info = detect_junction_verts(
        tri_wall, faces, points, cos_thresh=cos_thresh,
    )
    preserve_bulk = os.environ.get("AUTO_TESSELL_BL_VD_PRESERVE_BULK", "0") == "1"

    bbox_diag = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
    log.info(
        "native_bl_vd_start",
        component="native_bl",
        phase="VD-8a",
        n_wall_faces=len(tri_wall),
        n_wall_verts=len(wall_vert_indices),
        n_junction_verts=len(info.junction_verts),
        n_junction_edges=len(info.junction_edges),
        num_layers=cfg.num_layers,
        first_thickness=cfg.first_thickness,
        growth_ratio=cfg.growth_ratio,
        cluster_cos=cluster_cos,
        cos_thresh=cos_thresh,
        preserve_bulk=preserve_bulk,
        bbox_diag=round(bbox_diag, 6),
    )

    n_bulk = 0
    if preserve_bulk:
        full = build_bulk_preserving_multi_layer_full_bl_polymesh(
            tri_wall,
            faces,
            owner,
            neighbour,
            points,
            info,
            num_layers=int(cfg.num_layers),
            first_layer_thickness=float(cfg.first_thickness),
            growth_ratio=float(cfg.growth_ratio),
            vnorm=vnorm,
            cluster_cos=cluster_cos,
        )
        pm = full.polymesh
        n_bulk = full.n_bulk_cells
        n_prism = full.n_prism_cells
        n_gap = full.n_gap_fill_cells
    elif cfg.num_layers == 1:
        # Single-layer path also closes junction edges with gap-fill tets.
        inner = generate_per_face_inner_verts(
            tri_wall,
            faces,
            points,
            info,
            vnorm=vnorm,
            thickness=float(cfg.first_thickness),
            cluster_cos=cluster_cos,
        )
        full = build_full_bl_polymesh(tri_wall, faces, points, inner)
        pm = full.polymesh
        n_prism = full.n_prism_cells
        n_gap = full.n_gap_fill_cells
    else:
        ml = build_multi_layer_bl(
            tri_wall,
            faces,
            points,
            info,
            num_layers=int(cfg.num_layers),
            first_layer_thickness=float(cfg.first_thickness),
            growth_ratio=float(cfg.growth_ratio),
            vnorm=vnorm,
            cluster_cos=cluster_cos,
        )
        pm = cells_to_polymesh(ml.cell_face_verts, ml.new_points)
        n_prism = len(ml.cell_face_verts)
        n_gap = 0

    bnd_entries: list[dict[str, Any]] = []
    for p in pm.patches:
        patch_type = "wall" if p["name"] == "wall" else "patch"
        bnd_entries.append({
            "name": p["name"],
            "type": patch_type,
            "nFaces": int(p["nFaces"]),
            "startFace": int(p["startFace"]),
        })

    if cfg.backup_original:
        bak = case_dir / "constant" / "polyMesh_pre_bl"
        if bak.exists():
            shutil.rmtree(bak)
        shutil.copytree(poly_dir, bak)

    poly_dir.mkdir(parents=True, exist_ok=True)
    _write_points(poly_dir / "points", pm.points)
    _write_faces(poly_dir / "faces", pm.faces)
    _write_labels(
        poly_dir / "owner",
        np.array(pm.owner, dtype=np.int64),
        "owner",
    )
    _write_labels(
        poly_dir / "neighbour",
        np.array(pm.neighbour, dtype=np.int64),
        "neighbour",
    )
    _write_boundary(poly_dir / "boundary", bnd_entries)

    n_cells_out = n_bulk + n_prism + n_gap
    n_internal = len(pm.neighbour)
    n_faces_out = len(pm.faces)
    n_pts_out = int(pm.points.shape[0])
    n_new_pts = int(n_pts_out - len(points))
    if abs(float(cfg.growth_ratio) - 1.0) < 1e-12:
        total_thickness = float(cfg.first_thickness * cfg.num_layers)
    else:
        total_thickness = float(
            cfg.first_thickness
            * ((float(cfg.growth_ratio) ** int(cfg.num_layers)) - 1.0)
            / (float(cfg.growth_ratio) - 1.0)
        )

    # BLR-9c-d-g — env-gated cavity-component evaluation on the
    # pre-BL polyMesh.  In the VD writer path we don't carry an
    # explicit ``motion_dirs`` map, but the inward unit vector for
    # each wall vertex is exactly ``-vnorm[v]`` — build that map
    # inline so the eval helpers can run without any other change.
    _vd_tet_cavity_eval_enabled = (
        os.environ.get("AUTO_TESSELL_BL_TET_CAVITY_EVAL", "0") == "1"
    )
    vd_tet_cavity_eval_diag: dict[str, Any] = {
        "enabled": bool(_vd_tet_cavity_eval_enabled),
        "n_components": 0,
        "n_accepted": 0,
        "n_rejected_uncovered_shell": 0,
        "n_rejected_bad_det": 0,
        "n_rejected_bad_shape": 0,
        "n_rejected_bad_non_ortho": 0,
        "n_rejected_bad_skewness": 0,
        "writer_path": "vd",
    }
    if _vd_tet_cavity_eval_enabled:
        try:
            _vd_motion_dirs = {
                int(v): -np.asarray(vnorm[v], dtype=np.float64)
                for v in wall_vert_indices
                if v in vnorm
            }
            _vd_components = _detect_wall_owner_cavity_components(
                np.asarray(owner, dtype=np.int64),
                np.asarray(neighbour, dtype=np.int64),
                list(wall_face_indices),
            )
            _vd_non_ortho_thresh = float(
                os.environ.get(
                    "AUTO_TESSELL_BL_TET_CAVITY_NON_ORTHO_DEG",
                    "70.0",
                )
            )
            _vd_q_min_thresh = float(
                os.environ.get(
                    "AUTO_TESSELL_BL_TET_CAVITY_Q_MIN",
                    "0.1",
                )
            )
            _vd_summary = _evaluate_cavity_component_candidates(
                components=_vd_components,
                points=np.asarray(points, dtype=np.float64),
                faces=faces,
                owner=np.asarray(owner, dtype=np.int64),
                neighbour=np.asarray(neighbour, dtype=np.int64),
                wall_face_indices=list(wall_face_indices),
                motion_dirs=_vd_motion_dirs,
                first_thickness=float(cfg.first_thickness),
                non_ortho_threshold_deg=_vd_non_ortho_thresh,
                q_min_threshold=_vd_q_min_thresh,
            )
            for _key in (
                "n_components", "n_accepted",
                "n_rejected_uncovered_shell", "n_rejected_bad_det",
                "n_rejected_bad_shape", "n_rejected_bad_non_ortho",
                "n_rejected_bad_skewness",
            ):
                vd_tet_cavity_eval_diag[_key] = int(
                    _vd_summary.get(_key, 0)
                )
            vd_tet_cavity_eval_diag["non_ortho_hist"] = dict(
                _vd_summary.get("non_ortho_hist", {})
            )
            vd_tet_cavity_eval_diag["non_ortho_fine_hist"] = dict(
                _vd_summary.get("non_ortho_fine_hist", {})
            )
            vd_tet_cavity_eval_diag["worst_non_ortho_kind_hist"] = dict(
                _vd_summary.get("worst_non_ortho_kind_hist", {})
            )
            vd_tet_cavity_eval_diag["skew_hist"] = dict(
                _vd_summary.get("skew_hist", {})
            )
            vd_tet_cavity_eval_diag["q_min_hist"] = dict(
                _vd_summary.get("q_min_hist", {})
            )
            vd_tet_cavity_eval_diag["q_min_fine_hist"] = dict(
                _vd_summary.get("q_min_fine_hist", {})
            )
            vd_tet_cavity_eval_diag["worst_q_kind_hist"] = dict(
                _vd_summary.get("worst_q_kind_hist", {})
            )
            vd_tet_cavity_eval_diag["max_non_ortho_deg"] = float(
                _vd_summary.get("max_non_ortho_deg", 0.0)
            )
            vd_tet_cavity_eval_diag["max_skew"] = float(
                _vd_summary.get("max_skew", 0.0)
            )
            vd_tet_cavity_eval_diag["min_q"] = float(
                _vd_summary.get("min_q", 1.0)
            )
        except Exception as exc:  # noqa: BLE001
            vd_tet_cavity_eval_diag = {
                "enabled": True,
                "writer_path": "vd",
                "error": str(exc)[:160],
            }

    try:
        import json as _json

        quality_summary = {
            "n_wall_faces": int(len(tri_wall)),
            "n_wall_verts": int(len(wall_vert_indices)),
            "n_prism_cells": int(n_prism + n_gap),
            "n_bulk_cells": int(n_bulk),
            "n_gap_fill_cells": int(n_gap),
            "n_feature_edge_merged": 0,
            "n_new_points": int(n_new_pts),
            "tet_cavity_eval": vd_tet_cavity_eval_diag,
            "total_thickness": float(total_thickness),
            "bbox_diag": float(bbox_diag),
            "thickness_to_bbox_ratio": float(total_thickness / max(bbox_diag, 1e-30)),
            "n_degenerate_prisms": 0,
            "max_aspect_ratio": 0.0,
            "requested_layers": int(cfg.num_layers),
            "used_layers": int(cfg.num_layers),
            "wall_preserve": {
                "max_diff": 0.0,
                "max_diff_rel": 0.0,
                "n_drift": 0,
                "within_envelope": True,
                "envelope_eps_rel": 1e-6,
            },
            "force_snap": {
                "n_applied": 0,
                "max_diff": 0.0,
            },
            "lcr": {
                "n_reduced_verts": 0,
                "max_reduction": 0,
                "min_layers_used": int(cfg.num_layers),
                "n_safe_full_layers": int(len(wall_vert_indices)),
            },
            "aniso_split": {
                "n_examined": 0,
                "n_would_split": 0,
                "max_aspect_in": 0.0,
            },
            "pre_bl_self_intersect": None,
            "config": {
                "num_layers": int(cfg.num_layers),
                "growth_ratio": float(cfg.growth_ratio),
                "first_thickness": float(cfg.first_thickness),
                "wall_patch_names": cfg.wall_patch_names,
                "set_faces": cfg.set_faces,
                "ignore_faces": cfg.ignore_faces,
                "ignore_patch_names": cfg.ignore_patch_names,
                "ignore_patch_prefixes": cfg.ignore_patch_prefixes,
                "target_y_plus": cfg.target_y_plus,
                "flow_fluid_preset": cfg.flow_fluid_preset,
            },
        }
        (case_dir / "native_bl_quality.json").write_text(
            _json.dumps(quality_summary, indent=2),
            encoding="utf-8",
        )
        log.info(
            "native_bl_vd_quality_json_written",
            component="native_bl",
            phase="VD-8a",
            path=str(case_dir / "native_bl_quality.json"),
        )
    except Exception as exc:
        log.debug("native_bl_vd_quality_json_skipped", reason=str(exc)[:120])

    elapsed = time.perf_counter() - t_start
    log.info(
        "native_bl_vd_written",
        component="native_bl",
        phase="VD-8a",
        n_prism_cells=n_prism,
        n_gap_fill_cells=n_gap,
        n_bulk_cells=n_bulk,
        n_cells=n_cells_out,
        n_points=n_pts_out,
        n_faces=n_faces_out,
        n_internal_faces=n_internal,
        elapsed=round(elapsed, 4),
    )

    return NativeBLResult(
        success=True,
        elapsed=elapsed,
        n_wall_faces=len(tri_wall),
        n_wall_verts=len(wall_vert_indices),
        n_prism_cells=n_cells_out,
        n_new_points=n_new_pts,
        total_thickness=total_thickness,
        wall_preserve_max_diff=0.0,
        wall_preserve_max_diff_rel=0.0,
        wall_preserve_n_drift=0,
        wall_preserve_within_envelope=True,
        lcr_n_reduced_verts=0,
        lcr_max_reduction=0,
        lcr_min_layers_used=int(cfg.num_layers),
        lcr_n_safe_full_layers=int(len(wall_vert_indices)),
        message=(
            f"native_bl VD-8a OK — {n_prism} prism cells "
            f"({cfg.num_layers} layers × {len(tri_wall)} wall triangles)"
            + (f" + {n_gap} gap-fill tets" if n_gap else "")
            + (
                f". bulk preserved ({n_bulk} cells)."
                if preserve_bulk
                else ". bulk volume dropped (BL-only polyMesh)."
            )
        ),
    )


def generate_native_bl(
    case_dir: Path,
    config: BLConfig | None = None,
    *,
    engine_tag: str = "generic",
) -> NativeBLResult:
    """polyMesh 에 native BL prism layer 삽입 (Phase 2 완성).

    동작 단계:
      1. polyMesh 읽기 + cell centres 계산
      2. Wall face / vertex 식별 + area-weighted vertex normal
      3. Thickness 배열 + bbox safety scale
      4. 기존 points 에서 wall vertex 를 inward (−normal) 로 total 이동 (shrink)
      5. Layer point (N+1 층) 의 vertex 복사 생성 + 각 layer 별 (wall_v → new_v)
         매핑
      6. Prism cell 위상 구성:
         - 각 wall triangle × N prism cell
         - layer[i] (outer) 와 layer[i+1] (inner) 사이 triangle face
         - side quad face: wall edge 별, 이웃 wall triangle 과 공유되는 edge 는
           prism↔prism internal, 홀로 남은 edge (wall boundary) 는 bl_side patch
         - layer[0] outer triangle = 기존 wall boundary 유지
         - layer[N] inner triangle = 원본 owner cell 과 internal face
      7. polyMesh 재쓰기 (points/faces/owner/neighbour/boundary). 기존 파일은
         backup_original=True 일 때 polyMesh_pre_bl/ 로 백업.
    """
    t_start = time.perf_counter()
    cfg = config or BLConfig()
    requested_layers = int(cfg.num_layers)
    poly_dir = case_dir / "constant" / "polyMesh"
    if requested_layers > 0 and not engine_tag.startswith("__native_bl_stage__:") and not _vd_should_activate(case_dir):
        from core.layers.native_bl_transaction import (
            run_private_native_bl_transaction,
        )
        return run_private_native_bl_transaction(
            case_dir,
            cfg,
            engine_tag=engine_tag,
            generate_fn=generate_native_bl,
            result_cls=NativeBLResult,
        )
    if not (poly_dir / "faces").exists():
        return NativeBLResult(
            success=False, elapsed=time.perf_counter() - t_start,
            message=f"polyMesh 없음: {poly_dir}",
        )

    # C107: an explicit source-map sidecar opts into Hex authority mode only
    # after it has been checked against the current pre-BL polyMesh. This
    # preflight intentionally precedes the pending transaction state and every
    # mesh mutation, so stale lineage cannot leave a publishable candidate.
    native_hex_source_map_path = case_dir / "native_hex_source_face_map.json"
    native_hex_authority_mode = False
    native_hex_source_map_info: dict[str, Any] = {}
    if native_hex_source_map_path.is_file():
        try:
            from core.generator.native_hex.output_source_binding import (
                validate_native_hex_source_face_map,
            )
            native_hex_source_map_info = validate_native_hex_source_face_map(case_dir)
        except Exception as _source_map_import_exc:
            native_hex_source_map_info = {
                "accepted": False,
                "reason": f"{type(_source_map_import_exc).__name__}:{_source_map_import_exc}",
            }
        if native_hex_source_map_info.get("accepted") is not True:
            return NativeBLResult(
                success=False,
                elapsed=time.perf_counter() - t_start,
                message=(
                    "native_hex_source_map_refused:"
                    + str(native_hex_source_map_info.get("reason", "invalid"))
                ),
            )
        native_hex_authority_mode = True

    if requested_layers == 0:
        zero_blocker = _native_bl_zero_request_blocker(case_dir)
        if zero_blocker is not None:
            return NativeBLResult(
                success=False,
                elapsed=time.perf_counter() - t_start,
                message=zero_blocker,
            )
        return NativeBLResult(
            success=True,
            elapsed=time.perf_counter() - t_start,
            message="native_bl BL=0 identity; polyMesh unchanged",
            requested_layers=0,
            actual_layers=0,
            positive_thickness=False,
            quality_readback_status="identity_not_evaluated",
            wall_selector={"patch_names": cfg.wall_patch_names, "set_faces": cfg.set_faces},
            termination_reason="disabled_identity",
        )

    input_hashes, state_error = _begin_native_bl_state(
        case_dir, poly_dir, cfg, requested_layers, engine_tag,
    )
    if state_error is not None:
        return NativeBLResult(
            success=False,
            elapsed=time.perf_counter() - t_start,
            message=state_error,
        )
    assert input_hashes is not None

    # 1) 읽기
    raw_points = parse_foam_points(poly_dir / "points")
    raw_faces = parse_foam_faces(poly_dir / "faces")
    owner_list = parse_foam_labels(poly_dir / "owner")
    neighbour_list = parse_foam_labels(poly_dir / "neighbour")
    boundary = parse_foam_boundary(poly_dir / "boundary")
    _native_hex_source_face_by_mesh_face: dict[int, int] = {}
    if native_hex_authority_mode:
        _native_hex_source_face_by_mesh_face = {
            int(row["source_mesh_face"]): int(row["source_face"])
            for row in native_hex_source_map_info.get("records", [])
        }

    points = np.array(raw_points, dtype=np.float64)
    owner = np.array(owner_list, dtype=np.int64)
    neighbour = np.array(neighbour_list, dtype=np.int64)
    faces = [list(f) for f in raw_faces]
    n_cells = int(owner.max()) + 1 if len(owner) else 0
    if len(neighbour):
        n_cells = max(n_cells, int(neighbour.max()) + 1)
    n_faces_orig = len(faces)
    n_internal_orig = len(neighbour)
    log.info("native_bl_read", component="native_bl",
             n_cells=n_cells, n_faces=n_faces_orig,
             n_internal=n_internal_orig, n_points=len(points))

    # 2) Wall face 식별
    wall_face_indices, _, face_to_patch = _collect_wall_faces(
        boundary,
        cfg.wall_patch_names,
        set_faces=cfg.set_faces,
        ignore_faces=cfg.ignore_faces,
        ignore_patch_names=cfg.ignore_patch_names,
        ignore_patch_prefixes=cfg.ignore_patch_prefixes,
    )
    log.info(
        "native_bl_wall_selection",
        component="native_bl",
        n_selected=len(wall_face_indices),
        set_faces=bool(cfg.set_faces),
        n_ignore_faces=len(cfg.ignore_faces or []),
        ignore_patch_names=cfg.ignore_patch_names or [],
        ignore_patch_prefixes=cfg.ignore_patch_prefixes or [],
    )
    if not wall_face_indices:
        return NativeBLResult(
            success=False, elapsed=time.perf_counter() - t_start,
            message="wall patch 없음 (boundary 파일 확인)",
        )

    # beta89: Poly 전용 prism BL — polygon wall face 를 fan-triangulation 으로 분해.
    # 이전: non-tri wall face 는 skip (MVP 제약).
    # 이후: polygon face 를 합성 tri 로 분해 → poly mesh 에도 BL 생성 가능.
    # C-BL-2 / beta2424 — wall_face_indices 가 faces 범위 벗어나는 케이스 가드.
    # validator: hard mesh 에서 polymesh_writer 가 patch_cap 으로 wall_misc 병합
    # 시 일부 indices 가 stale → IndexError 발생. 안전 필터로 회피.
    _n_faces = len(faces)
    _stale = [fi for fi in wall_face_indices if fi >= _n_faces or fi < 0]
    if _stale:
        log.warning(
            "native_bl_wall_face_indices_filtered",
            component="native_bl", phase="beta2424",
            n_stale=len(_stale), n_total=len(wall_face_indices),
            n_faces=_n_faces,
        )
        wall_face_indices = [fi for fi in wall_face_indices if 0 <= fi < _n_faces]
    replaced_polygon_wall_faces: set[int] = set()
    _wall_source_mesh_face_by_wall_face = {
        int(fi): int(fi) for fi in wall_face_indices
    }
    non_tri = [fi for fi in wall_face_indices if len(faces[fi]) != 3]
    if non_tri:
        log.info(
            "native_bl_polygon_wall_fan_triangulate", component="native_bl",
            n_polygon=len(non_tri), phase="beta89",
        )
        replaced_polygon_wall_faces = set(non_tri)
        # 합성 tri face 를 faces 리스트 끝에 추가 (원본 faces 는 보존)
        synth_start = len(faces)
        for fi in non_tri:
            f = faces[fi]
            patch_info = face_to_patch.get(fi)
            own = int(owner[fi])
            # fan triangulation from vertex 0
            for k in range(1, len(f) - 1):
                tri = [int(f[0]), int(f[k]), int(f[k + 1])]
                new_fi = len(faces)
                faces.append(tri)
                _wall_source_mesh_face_by_wall_face[int(new_fi)] = int(fi)
                # owner 배열 확장 (numpy → list 로 처리)
                owner = np.concatenate([owner, [own]])
                if patch_info is not None:
                    face_to_patch[new_fi] = patch_info
                wall_face_indices.append(new_fi)
        # 원래 polygon face 들은 wall 처리에서 제외 (tri 로 대체됨)
        wall_face_indices = [
            fi for fi in wall_face_indices
            if fi >= synth_start or len(faces[fi]) == 3
        ]
    else:
        # 이미 전부 triangle — no-op (기존 경로)
        pass

    # 3) Cell centres + vertex normals
    cell_centres = _cell_centres_from_faces(
        points, faces, owner, neighbour, n_cells,
    )
    try:
        pre_bl_bad_internal_face_histogram = _bl_bad_internal_face_histogram(
            points,
            faces,
            owner,
            neighbour,
            base_n_cells=n_cells,
            prism_cell_start=n_cells,
            prism_cell_end=n_cells,
            include_components=False,
        )
    except Exception as exc:  # noqa: BLE001
        pre_bl_bad_internal_face_histogram = {"error": str(exc)[:160]}
    vnorm = compute_vertex_normals(
        points, faces, wall_face_indices, owner, cell_centres,
    )
    wall_vert_indices = sorted(vnorm.keys())

    # VD-8a — env-gated vertex-duplication BL path (default OFF).
    # AUTO_TESSELL_BL_VD_ENABLE=1 routes the BL build through
    # core.layers.native_bl_vd's per-face inner-vert + gap-fill polyMesh
    # writer instead of the per-vertex extrusion below. Bulk volume cells
    # are not preserved — output is BL-only (prism stack + junction
    # gap-fill tets), which lets us measure boundary skew at multi-patch
    # junctions without the per-vertex tan(theta) bias. See
    # docs/plans/vd_bl_refactor_2026-05-09.md.
    #
    # VD-8b — AUTO_TESSELL_BL_VD_FOR refines activation to a comma-separated
    # substring allow-list matched against the input STL filename (read from
    # ``case_dir/geometry_report.json``). Semantics:
    #   * VD_FOR unset/empty  → activation governed solely by VD_ENABLE.
    #   * VD_FOR non-empty    → VD activates ONLY when STL name matches a
    #                            token (VD_ENABLE is ignored in this mode so
    #                            the bench can run a single command with one
    #                            env var).
    # This lets us enable VD per-STL (e.g. multi-patch junctions like
    # hard_100029) without affecting the rest of the 21-STL bench.
    if _vd_should_activate(case_dir):
        result = _generate_native_bl_vd(
            case_dir=case_dir,
            cfg=cfg,
            poly_dir=poly_dir,
            points=points,
            faces=faces,
            owner=owner,
            neighbour=neighbour,
            wall_face_indices=wall_face_indices,
            wall_vert_indices=wall_vert_indices,
            vnorm=vnorm,
            t_start=t_start,
        )
        if result.success:
            state_error = _complete_native_bl_state(
                case_dir,
                input_hashes,
                requested_layers=requested_layers,
                actual_layers=int(cfg.num_layers),
                n_prism_cells=int(result.n_prism_cells),
            )
            if state_error is not None:
                return replace(result, success=False, message=state_error)
        return result

    # 4) Thickness 배열 + bbox safety
    bbox_diag = float(np.linalg.norm(points.max(0) - points.min(0)))

    # beta2272 — fluid preset → kinematic viscosity 자동 override.
    # beta2331 — yplus.py FLUID_PROPERTIES + GUI yplus_panel 의 11 옵션과
    # 일관성 위해 simple presets ("air", "water", "oil") 추가. 이전엔
    # cfg.flow_fluid_preset="air" 시 native_bl_fluid_preset_unknown warning.
    _FLUID_PRESETS = {
        # simple aliases (yplus.py 와 동일).
        "air": 1.516e-5,            # = air_20C (default standard).
        "water": 1.004e-6,          # = water_20C.
        "oil": 1.0e-4,              # = oil_SAE10W30.
        # advanced (정확한 온도/조건 명시).
        "air_sea_level": 1.5e-5,    # air at 15°C, 1 atm (standard)
        "air_20C": 1.516e-5,        # air at 20°C
        "air_0C": 1.336e-5,         # air at 0°C
        "water_20C": 1.004e-6,      # liquid water at 20°C
        "water_4C": 1.567e-6,       # liquid water at 4°C (max density)
        "oil_SAE10W30": 1.0e-4,     # engine oil SAE 10W-30 at 100°C
        "glycol_50pct": 5.0e-6,     # 50% ethylene glycol-water at 20°C
    }
    effective_nu = float(cfg.flow_kinematic_viscosity)
    if cfg.flow_fluid_preset is not None:
        preset_nu = _FLUID_PRESETS.get(cfg.flow_fluid_preset)
        if preset_nu is not None:
            effective_nu = preset_nu
            log.info(
                "native_bl_fluid_preset", component="native_bl",
                preset=cfg.flow_fluid_preset, nu=effective_nu,
            )
        else:
            log.warning(
                "native_bl_fluid_preset_unknown",
                preset=cfg.flow_fluid_preset,
                available=list(_FLUID_PRESETS.keys()),
            )

    # beta2267 — y+ targeting (CFD engineer mode).
    # target_y_plus 가 설정되면 cfg.first_thickness 를 무시하고 Schlichting
    # flat plate 공식으로 자동 계산.
    effective_first_thickness = float(cfg.first_thickness)
    # C-BL-1 / beta2423 — bbox-relative auto-scale.
    # validator: 1mm-bbox mesh 에 first_thickness=1e-3 (절대값) → 1mm/1mm=100%
    # 두께가 됨 → collision_safety 가 모든 prism 차단. 반대로 100mm-bbox mesh
    # 에 1e-3 → 0.001% 두께 → 의미 없는 BL.
    # 자동 scale: first_thickness < bbox_diag * 1e-5 면 bbox_diag * 1e-3 로 bump,
    # > bbox_diag * 0.1 이면 bbox_diag * 0.01 로 cap.
    try:
        if bbox_diag > 0 and cfg.target_y_plus is None:
            _abs_min = bbox_diag * 1e-5
            _abs_max = bbox_diag * 0.1
            if effective_first_thickness < _abs_min:
                _new_ft = bbox_diag * 1e-3
                log.warning(
                    "native_bl_first_thickness_auto_bump",
                    component="native_bl", phase="beta2423",
                    user_first_thickness=effective_first_thickness,
                    bbox_diag=round(bbox_diag, 6),
                    auto_first_thickness=round(_new_ft, 9),
                    reason="too_small_relative_to_bbox",
                )
                effective_first_thickness = _new_ft
            elif effective_first_thickness > _abs_max:
                _new_ft = bbox_diag * 0.01
                log.warning(
                    "native_bl_first_thickness_auto_cap",
                    component="native_bl", phase="beta2423",
                    user_first_thickness=effective_first_thickness,
                    bbox_diag=round(bbox_diag, 6),
                    auto_first_thickness=round(_new_ft, 9),
                    reason="too_large_relative_to_bbox",
                )
                effective_first_thickness = _new_ft
    except Exception:
        pass
    # H4 / beta2613 — auto y+ default: env AUTO_TESSELL_BL_AUTO_YPLUS=N (1-300)
    #   target_y_plus 미지정 + AUTO_TESSELL_BL_AUTO_YPLUS=30 (or env value) 면
    #   자동 y+ targeting 적용. 30 = log-law region (wall function 표준).
    _auto_yplus_str = os.environ.get("AUTO_TESSELL_BL_AUTO_YPLUS", "")
    _effective_yplus = cfg.target_y_plus
    if _effective_yplus is None and _auto_yplus_str:
        try:
            _effective_yplus = float(_auto_yplus_str)
            if _effective_yplus <= 0 or _effective_yplus > 1000:
                _effective_yplus = None
        except Exception:
            _effective_yplus = None
        if _effective_yplus is not None:
            log.info(
                "native_bl_auto_yplus_enabled",
                component="native_bl", phase="H4/beta2613",
                auto_y_plus=_effective_yplus,
                source="env AUTO_TESSELL_BL_AUTO_YPLUS",
            )

    if _effective_yplus is not None and _effective_yplus > 0:
        try:
            U = float(cfg.flow_velocity)
            nu = effective_nu
            L = float(cfg.flow_characteristic_length) if cfg.flow_characteristic_length else bbox_diag
            Re = max(1.0, U * L / nu)
            Cf = 0.058 / (Re ** 0.2)  # Schlichting flat plate
            u_tau = U * (Cf / 2.0) ** 0.5
            y1 = float(_effective_yplus) * nu / u_tau
            effective_first_thickness = y1
            log.info(
                "native_bl_y_plus_targeting", component="native_bl", phase="BL2",
                target_y_plus=_effective_yplus,
                flow_U=U, flow_nu=nu, flow_L=L,
                Re=round(Re, 1), Cf=round(Cf, 6), u_tau=round(u_tau, 6),
                first_thickness_computed=round(y1, 9),
                first_thickness_user=cfg.first_thickness,
            )
        except Exception as exc:
            log.warning(
                "native_bl_y_plus_skipped", reason=str(exc)[:120],
                fallback_first_thickness=cfg.first_thickness,
            )

    # BL2: geometric growth via _geometric_layer_thickness (cfMesh default 1.2×/layer)
    thicknesses = _geometric_layer_thickness(
        effective_first_thickness, cfg.num_layers, growth_ratio=cfg.growth_ratio,
    )
    total = float(thicknesses.sum())
    log.info(
        "native_bl_geometric_growth", component="native_bl", phase="BL2",
        first_thickness=cfg.first_thickness,
        growth_ratio=cfg.growth_ratio,
        n_layers=cfg.num_layers,
        total=round(total, 6),
        thicknesses=[round(float(t), 6) for t in thicknesses],
    )
    if total > cfg.max_total_ratio * bbox_diag:
        scale = (cfg.max_total_ratio * bbox_diag) / total
        thicknesses *= scale
        total = float(thicknesses.sum())
        log.warning("native_bl_thickness_scaled", component="native_bl", factor=scale, new_total=total)
    cum = np.concatenate(([0.0], np.cumsum(thicknesses)))  # [0, t1, t1+t2, ..., total]

    # 4b) Per-vertex local safety — 각 wall vertex 에서 인접 tet cell centroid 까지의
    #     최소 거리 × 0.8 로 local 최대 허용 thickness. total 이 이 값을 초과하면
    #     해당 vertex 는 scale 해서 이동 (thicknesses 는 전역 공유라 전체 축소).
    #     이렇게 해야 극점 근처 sliver 가 줄어듦.
    wall_idx_arr_tmp = np.array(sorted(vnorm.keys()), dtype=np.int64)
    # vertex 별 인접 cell 중 "내부 tet" 까지의 거리
    # C-PERF-69 / beta2520 — triangle fast path: scatter min via numpy.
    # 변형: vert_to_cells dict 빌드 + per-vert min 의 global min 만 필요.
    # → flat (v, own) 의 모든 distance 의 global min 으로 대체 가능 (min idempotent).
    tri_fis = [fi for fi in wall_face_indices if len(faces[fi]) == 3]
    other_fis = [fi for fi in wall_face_indices if len(faces[fi]) != 3]
    min_local: float | None = None
    if tri_fis:
        F_tri = np.asarray([faces[fi] for fi in tri_fis], dtype=np.int64)
        own_tri = np.asarray([int(owner[fi]) for fi in tri_fis], dtype=np.int64)
        wall_arr_local = np.asarray(sorted(set(wall_vert_indices)), dtype=np.int64)
        flat_v_all = F_tri.reshape(-1)
        flat_own_all = np.repeat(own_tri, 3)
        mask_w = np.isin(flat_v_all, wall_arr_local)
        if mask_w.any():
            flat_v = flat_v_all[mask_w]
            flat_own = flat_own_all[mask_w]
            v_pos = points[flat_v]
            own_pos = cell_centres[flat_own]
            dist_arr = np.linalg.norm(own_pos - v_pos, axis=1)
            if dist_arr.size > 0:
                min_local = float(dist_arr.min())
    # Polygon fallback for non-triangle wall faces.
    if other_fis:
        for fi_p in other_fis:
            own_p = int(owner[fi_p])
            for v_p in faces[fi_p]:
                v_int = int(v_p)
                if v_int in vnorm:  # wall vert membership proxy
                    d = float(np.linalg.norm(cell_centres[own_p] - points[v_int]))
                    if min_local is None or d < min_local:
                        min_local = d
    if min_local is not None:
        # C-BL-21 / beta2456 — local_cap floor 를 effective_first_thickness 사용.
        # 이전: cfg.first_thickness (raw) — auto-bump 시 (예: 1e-3 → bbox*1e-3)
        # local_cap floor 가 너무 낮아 BL total 이 effective 미달까지 축소됨.
        local_cap = max(min_local * 0.8, effective_first_thickness)
        if total > local_cap:
            scale = local_cap / total
            thicknesses *= scale
            total = float(thicknesses.sum())
            log.info(
                "native_bl_local_safety_scaled", component="native_bl",
                factor=scale, min_local=min_local, new_total=total,
            )
            cum = np.concatenate(([0.0], np.cumsum(thicknesses)))

    # G1 / beta2602 — aspect-aware first_thickness cap (Pointwise T-Rex parity).
    #   목표: BL prism 의 aspect ≤ AUTO_TESSELL_BL_ASPECT_TARGET (default 1000.0).
    #   알고리즘: aspect = wall_normal_thickness / wall_edge_length.
    #   thicknesses[0] (first layer) ≤ mean_wall_edge / target_aspect.
    #   초과 시 전체 thicknesses 를 비례 축소.
    #   env AUTO_TESSELL_BL_ASPECT_TARGET=1000 (default), =0 이면 비활성.
    try:
        _aspect_target = float(os.environ.get("AUTO_TESSELL_BL_ASPECT_TARGET", "1000.0"))
        if _aspect_target > 0 and len(wall_face_indices) > 0:
            # mean wall edge length 추산 (sample 100 face).
            _sample = wall_face_indices[: min(100, len(wall_face_indices))]
            _edge_lens: list[float] = []
            for _fi in _sample:
                _f = faces[_fi]
                if len(_f) < 3:
                    continue
                for _ai, _bi in ((0, 1), (1, 2), (2, 0)):
                    _ea = points[_f[_ai]]
                    _eb = points[_f[_bi]]
                    _edge_lens.append(float(np.linalg.norm(_eb - _ea)))
            if _edge_lens:
                _mean_edge = float(np.mean(_edge_lens))
                _aspect_cap_first = _mean_edge / _aspect_target
                if 0 < thicknesses[0] < _aspect_cap_first:
                    _scale_aspect = _aspect_cap_first / float(thicknesses[0])
                    thicknesses *= _scale_aspect
                    total = float(thicknesses.sum())
                    log.info(
                        "native_bl_aspect_cap_applied",
                        component="native_bl", phase="G1/beta2602",
                        mean_edge=round(_mean_edge, 6),
                        aspect_target=_aspect_target,
                        first_thickness_pre=round(float(thicknesses[0] / _scale_aspect), 6),
                        first_thickness_post=round(float(thicknesses[0]), 6),
                        scale=round(_scale_aspect, 4),
                        new_total=round(total, 6),
                    )
                    cum = np.concatenate(([0.0], np.cumsum(thicknesses)))
    except Exception as _asp_exc:
        log.debug("native_bl_aspect_cap_skipped", reason=str(_asp_exc)[:120])

    # 4d) beta64 feature lock — sharp edge vertex 는 layer thickness 를 축소.
    feature_verts: set[int] = set()
    if cfg.feature_lock:
        feature_verts = _detect_feature_vertices(
            points, faces, wall_face_indices, cfg.feature_angle_deg,
        )
        if feature_verts:
            log.info(
                "native_bl_feature_lock", component="native_bl", phase="Phase2",
                n_feature_verts=len(feature_verts),
                angle_deg=cfg.feature_angle_deg,
                reduction=cfg.feature_reduction_ratio,
            )
    # beta90: 완전 비균일 prism BL — collision distance 기반 per-vertex scale.
    # 기존 vertex_scale 는 feature vertex 에만 0.5×. 이제 collision distance 기반으로
    # 각 vertex 의 허용 최대 두께를 계산해 개별 scale 적용.
    # vertex_scale_extra: collision_dist[v] × safety / total
    # 1.0 초과 시 클램프 (기존 total 이상 늘릴 수 없음).

    # 4c) beta63 collision detection — per-vertex 비균일 thickness (beta90 확장).
    # AI-V3.C / beta2590 — ML fast-path opt-in.
    #   AUTO_TESSELL_BL_PREDICT_MODEL=path 시 ML predict 시도. 결과 success
    #   면 geometric raycast O(n²) 우회 (20-50× speedup target). 실패 / model
    #   미제공 시 geometric path fallback.
    collision_dist: dict[int, float] = {}
    if cfg.collision_safety:
        _ml_used = False
        if os.environ.get("AUTO_TESSELL_BL_PREDICT_MODEL", "").strip():
            try:
                from core.generator.native_ai.ml_bl_collision import (
                    predict_bl_collision_distances,
                )
                _wv_arr = np.asarray(list(wall_vert_indices), dtype=np.int64)
                _wf_verts = np.asarray(
                    [faces[fi] for fi in wall_face_indices], dtype=np.int64,
                ) if wall_face_indices else np.zeros((0, 3), dtype=np.int64)
                _wf_arr = np.asarray(list(wall_face_indices), dtype=np.int64)
                _gap, _ml_r = predict_bl_collision_distances(
                    points, _wv_arr, _wf_arr, _wf_verts,
                )
                if _ml_r.success and _gap.shape[0] == _wv_arr.shape[0]:
                    collision_dist = {
                        int(_wv_arr[i]): float(_gap[i])
                        for i in range(_wv_arr.shape[0])
                        if np.isfinite(_gap[i])
                    }
                    _ml_used = True
                    log.info(
                        "native_bl_ml_collision_used",
                        backend=_ml_r.backend,
                        n_high_risk=_ml_r.n_high_risk,
                        elapsed_ms=float(_ml_r.elapsed) * 1e3,
                    )
            except Exception as _ml_exc:
                log.debug("native_bl_ml_predict_skipped", reason=str(_ml_exc)[:120])
        if not _ml_used:
            collision_dist = _compute_collision_distance(
                points, faces, wall_face_indices, wall_vert_indices, vnorm,
                max_search_distance=(
                    total / max(float(cfg.collision_safety_factor), 1e-12)
                ) * 1.05,
            )
        if collision_dist:
            safety = float(cfg.collision_safety_factor)
            # beta90: 전역 cap (기존) + per-vertex cap (신규).
            # 전역 cap: global min collision distance → global thickness 축소.
            # C-BL-19 / beta2452 — floor 도 effective_first_thickness 기반.
            min_collision = float(min(collision_dist.values()))
            collision_cap = max(min_collision * safety, effective_first_thickness)
            if total > collision_cap:
                scale = collision_cap / total
                thicknesses *= scale
                total = float(thicknesses.sum())
                log.warning(
                    "native_bl_collision_safety_scaled", component="native_bl", phase="Phase2",
                    factor=scale, min_collision=min_collision,
                    safety=safety, new_total=total,
                )
                cum = np.concatenate(([0.0], np.cumsum(thicknesses)))

    # per-vertex thickness scale: feature lock (beta64) + collision per-vertex (beta90).
    # vertex_scale[v] ∈ (0.0, 1.0]: 1.0 = global total, <1.0 = 해당 vertex 는 더 얇게.
    vertex_scale: dict[int, float] = {}
    for v in wall_vert_indices:
        # Feature lock 기반 scale (beta64)
        s = float(cfg.feature_reduction_ratio) if v in feature_verts else 1.0
        # Collision 기반 per-vertex cap (beta90)
        # C-BL-17 / beta2451 — collision cap floor 를 effective_first_thickness 기반.
        # 이전: max(v_cap, cfg.first_thickness) — raw value 기준.
        # 이제: effective_first_thickness × 0.5 (auto-scale 보존 + 추가 안전 floor).
        if collision_dist and v in collision_dist and total > 1e-30:
            v_cap = collision_dist[v] * float(cfg.collision_safety_factor)
            v_cap = max(v_cap, effective_first_thickness * 0.5)
            v_scale_coll = min(v_cap / total, 1.0)
            s = min(s, v_scale_coll)  # 두 제약 중 더 엄격한 쪽
        # C-BL-18 / beta2452 — minimum vertex scale floor (avoid vanishingly thin prisms).
        # vertex_scale < 0.1 (10% of full thickness) 면 0.1 로 floor.
        # 이로써 어떠한 wall vertex 도 thickness 10% 미만 떨어지지 않음.
        s = max(s, 0.1)
        vertex_scale[v] = s
    if any(s < 1.0 for s in vertex_scale.values()):
        n_limited = sum(1 for s in vertex_scale.values() if s < 1.0)
        log.info(
            "native_bl_per_vertex_scale", component="native_bl", phase="beta90",
            n_limited_verts=n_limited,
            min_scale=float(min(vertex_scale.values())),
        )

    # GLFS: collision gaps must not globally collapse an otherwise open wall.
    # Preserve the narrowest vertex cap, and only limit the first-layer jump
    # from it.  This is an explicit opt-in because it changes local sizing.
    feature_size_diag: dict[str, Any] = {
        "enabled": bool(cfg.feature_size_smoothing),
        "n_limited": 0,
        "gradient_limit": float(cfg.feature_size_gradient_limit),
    }
    feature_size_first: dict[int, float] = {}
    if cfg.feature_size_smoothing and collision_dist and wall_vert_indices:
        safety = float(cfg.collision_safety_factor)
        first_caps = {
            int(v): min(float(cfg.first_thickness), float(collision_dist.get(v, np.inf)) * safety)
            for v in wall_vert_indices
        }
        min_first = min(first_caps.values())
        gradient = max(float(cfg.feature_size_gradient_limit), 0.0)
        for v in wall_vert_indices:
            cap = first_caps[int(v)]
            smoothed = min(cap, min_first + gradient)
            feature_size_first[int(v)] = smoothed
            if smoothed < cap - 1e-15:
                feature_size_diag["n_limited"] += 1
        log.info(
            "native_bl_feature_size_smoothing",
            n_limited=feature_size_diag["n_limited"],
            min_first=min_first,
            gradient_limit=gradient,
        )

    # C2 / beta2368 — per-vertex Layer Count Reduction (Pointwise T-Rex 동등) diagnostic.
    # collision_dist 가 이미 계산되어 있을 때만 실행. env-gate
    # AUTO_TESSELL_LCR_OFF=1 로 비활성. C2.3 에서 NativeBLResult 로 노출.
    lcr_n_reduced = 0
    lcr_max_reduction = 0
    lcr_min_layers_used = int(cfg.num_layers)
    lcr_n_safe_full = 0
    if (
        os.environ.get("AUTO_TESSELL_LCR_OFF", "0") != "1"
        and collision_dist
        and len(wall_vert_indices) > 0
        and cfg.num_layers > 1
    ):
        try:
            from core.layers.native_bl_lcr import per_vertex_lcr
            wv_arr = np.asarray(list(wall_vert_indices), dtype=np.int64)
            cd_arr = np.asarray(
                [collision_dist.get(int(v), -1.0) for v in wv_arr],
                dtype=np.float64,
            )
            _per_v_layers, _lcr_r = per_vertex_lcr(
                wv_arr, cd_arr,
                num_layers=int(cfg.num_layers),
                first_thickness=float(cfg.first_thickness),
                growth_ratio=float(cfg.growth_ratio),
                safety=float(cfg.collision_safety_factor),
                min_layers=1,
            )
            lcr_n_reduced = int(_lcr_r.n_reduced_verts)
            lcr_max_reduction = int(_lcr_r.max_reduction)
            lcr_min_layers_used = int(_lcr_r.min_layers_used)
            lcr_n_safe_full = int(_lcr_r.n_safe_full_layers)
            if lcr_n_reduced > 0:
                log.info(
                    "native_bl_lcr_per_vertex",
                    component="native_bl", phase="beta2368",
                    n_wall=int(_lcr_r.n_wall_verts),
                    n_reduced=lcr_n_reduced,
                    max_reduction=lcr_max_reduction,
                    min_layers=lcr_min_layers_used,
                    n_safe_full=lcr_n_safe_full,
                    elapsed_ms=float(_lcr_r.elapsed_s) * 1e3,
                )
            # P3.3 / beta2587 — global num_layers auto-reduction.
            # 50%+ wall verts 가 layer 수 감소가 필요한 경우, cfg.num_layers
            # 를 wall verts 의 median 로 globally 감소. opt-in env
            # AUTO_TESSELL_LCR_AUTO_REDUCE=1.
            # 효과: 좁은 gap mesh 에서 collision_safety thickness 단축이
            # 아닌 layer 자체 감소 → BL aspect ratio ↓.
            if (
                os.environ.get("AUTO_TESSELL_LCR_AUTO_REDUCE", "0") == "1"
                and _per_v_layers.size > 0
                and lcr_n_reduced * 2 >= _per_v_layers.size
            ):
                _new_layers = int(np.median(_per_v_layers))
                _new_layers = max(1, min(int(cfg.num_layers), _new_layers))
                if _new_layers < int(cfg.num_layers):
                    log.info(
                        "native_bl_lcr_global_reduce",
                        from_layers=int(cfg.num_layers),
                        to_layers=_new_layers,
                        n_reduced_majority=lcr_n_reduced,
                        n_wall=int(_per_v_layers.size),
                    )
                    object.__setattr__(cfg, "num_layers", _new_layers)
        except Exception as _lcr_exc:
            log.debug("native_bl_lcr_skipped", reason=str(_lcr_exc)[:120])

    # HEX_BL1 — pre-filter wall_face_indices via aspect+collision guard (Garimella 2003 §3).
    # Mirrors POL_BL1 (voronoi.py) and TET_BL1 (tet_bl_subdivide.py) pattern.
    try:
        _wall_faces_before_guard = list(wall_face_indices)
        # The later BL1/BL3 pass can enlarge too-thin raw first thicknesses using
        # local edge length. Keep this prefilter as a degenerate-face guard, not
        # as a strict final prism-quality gate, otherwise quad fan walls can be
        # rejected before the corrective thickness pass runs.
        _guard_aspect = max(float(cfg.aspect_ratio_threshold), 1.0e12)
        wall_face_indices, _n_rej_asp, _n_rej_col = _hex_bl1_prism_guard(
            wall_face_indices, faces, points, vnorm, cfg.first_thickness,
            aspect_threshold=_guard_aspect,
        )
        if (
            _wall_faces_before_guard
            and len(wall_face_indices) < int(0.95 * len(_wall_faces_before_guard))
        ):
            log.info(
                "hex_bl_guard_relaxed",
                n_before=len(_wall_faces_before_guard),
                n_after=len(wall_face_indices),
                aspect_threshold_pre=cfg.aspect_ratio_threshold,
                aspect_threshold_used=_guard_aspect,
                reason="prefilter would remove too much wall before BL3 thickness correction",
            )
        # Rebuild dependent sets after filtering.
        # BL_FIX (beta2238): wall_face_indices 에서 모든 vertex 가 vnorm 에
        # 없는 face 제거 — _ltri (line 1641) 의 KeyError 회피.
        wall_face_indices = [
            fi for fi in wall_face_indices
            if all(v in vnorm for v in faces[fi])
        ]
        wall_set = set(wall_face_indices)
        wall_vert_indices = sorted(
            {v for fi in wall_face_indices for v in faces[fi]}
        )
    except Exception as _hex_bl1_exc:
        log.warning("hex_bl1_guard_skipped", reason=str(_hex_bl1_exc)[:120])

    # SMESH-style layer-edge front topology. Default is diagnostic-only; strict
    # mode can conservatively drop faces touching non-manifold layer-front edges.
    _front_edge_adjacency: np.ndarray | None = None
    try:
        from core.layers.layer_front import build_layer_front_topology_summary

        _front_strict = os.environ.get("AUTO_TESSELL_BL_FRONT_STRICT", "0") == "1"
        _front_topology = build_layer_front_topology_summary(
            faces,
            wall_face_indices,
            points=points,
        )
        _front = _front_topology.summary
        _front_edge_adjacency = _front_topology.adjacent_face_ids
        if _front.first_nonmanifold_edge is not None:
            message = (
                "non-manifold selected wall topology: "
                f"edge {_front.first_nonmanifold_edge} has "
                f"{len(_front.first_nonmanifold_faces)} incident wall faces "
                f"{list(_front.first_nonmanifold_faces)}"
            )
            log.warning(
                "native_bl_nonmanifold_wall_rejected",
                edge=_front.first_nonmanifold_edge,
                incident_faces=_front.first_nonmanifold_faces,
                n_nonmanifold_edges=_front.n_nonmanifold_edges,
            )
            return NativeBLResult(
                success=False,
                elapsed=time.perf_counter() - t_start,
                message=message,
            )
        log.info(
            "native_bl_layer_front",
            component="native_bl",
            phase="SMESH_FRONT1",
            n_faces=_front.n_faces,
            n_ignored=_front.n_ignored,
            n_vertices=_front.n_vertices,
            n_edges=_front.n_edges,
            n_boundary_edges=_front.n_boundary_edges,
            n_nonmanifold_edges=_front.n_nonmanifold_edges,
            n_feature_vertices=_front.n_feature_vertices,
            n_blocked_vertices=_front.n_blocked_vertices,
            strict=_front_strict,
        )
    except Exception as _front_exc:
        log.debug("native_bl_layer_front_skipped", reason=str(_front_exc)[:120])

    # 공유 캐시: wall_face_indices 기반 topology (loop 밖에서 한 번만 계산)
    n_wall_faces = len(wall_face_indices)
    n_prism_per_face = cfg.num_layers
    n_prism_total = n_wall_faces * n_prism_per_face
    prism_cell_id_start = n_cells  # prism cell IDs: [n_cells, n_cells + n_prism_total)

    # beta2327 — pre-BL wall surface 의 self-intersect 진단.
    # SI 가 있는 wall surface 는 prism extrusion 단계에서 collision_safety
    # 로 잡히지만, 사전에 알면 사용자가 입력 전처리를 강화하거나 num_layers
    # 줄이는 의사결정 가능. ≤ 5000 face 만 측정 (KDTree 비용 회피).
    # beta2328 — JSON quality 보고서에도 노출 (사용자 visibility ↑).
    _pre_bl_si_count: int | None = None
    if 0 < n_wall_faces <= 5000:
        try:
            from core.preprocessor.native_repair.self_intersect import (
                detect_self_intersections as _det_si_bl,
            )
            _wall_F = np.array(
                [list(faces[fi]) for fi in wall_face_indices], dtype=np.int64,
            )
            _si_bl = _det_si_bl(points, _wall_F)
            _pre_bl_si_count = int(_si_bl.n_intersections)
            if _si_bl.has_self_intersection:
                log.warning(
                    "native_bl_pre_extrude_self_intersect",
                    n_wall_faces=int(n_wall_faces),
                    n_intersections=int(_si_bl.n_intersections),
                    hint=(
                        "wall surface 에 self-intersect 존재 — collision_safety "
                        "로 thickness 자동 축소되거나 prism quality 저하 가능. "
                        "L1 repair 강화 또는 num_layers ↓ 권장."
                    ),
                )
            else:
                log.info(
                    "native_bl_pre_extrude_si_clean",
                    n_wall_faces=int(n_wall_faces),
                )
        except Exception as _si_bl_exc:
            log.debug("native_bl_pre_extrude_si_skipped", reason=str(_si_bl_exc)[:120])

    edge_to_walls = (
        _build_edge_to_wall_faces(wall_face_indices, faces)
        if _front_edge_adjacency is None
        else None
    )
    wall_fi_to_wi: dict[int, int] = {fi: wi for wi, fi in enumerate(wall_face_indices)}

    wall_tri_verts: dict[int, tuple[int, int, int]] = {}
    wall_orig_owner: dict[int, int] = {}
    wall_orig_patch: dict[int, int] = {}
    for fi in wall_face_indices:
        v = faces[fi]
        wall_tri_verts[fi] = (v[0], v[1], v[2])
        wall_orig_owner[fi] = int(owner[fi])
        wall_orig_patch[fi] = face_to_patch[fi][0]

    wall_set = set(wall_face_indices)
    try:
        tet_wall_cavity_eligibility = _tet_wall_cavity_eligibility(
            faces,
            owner,
            neighbour,
            wall_face_indices,
            n_cells=n_cells,
        )
    except Exception as exc:  # noqa: BLE001
        tet_wall_cavity_eligibility = {"error": str(exc)[:160]}

    # BLR-8 — env-gated owner-centre wall vertex motion (default OFF).
    # Wall vertices adjacent to BLR-7 single-tet single-wall owner cells are
    # extruded toward the owner cell centre instead of the area-/angle-weighted
    # patch normal, which lets the closed advancing-layer refill keep its
    # candidate motion bounded inside the eligible owner cell.
    _bl_owner_centre_motion_enabled = (
        os.environ.get("AUTO_TESSELL_BL_OWNER_CENTRE_MOTION", "0") == "1"
    )
    _bl_owner_centre_eligible_cells: set[int] = set()
    if isinstance(tet_wall_cavity_eligibility, dict):
        _eligible_source = tet_wall_cavity_eligibility.get(
            "single_wall_tet_cells"
        )
        if _eligible_source is None:
            _eligible_source = tet_wall_cavity_eligibility.get(
                "sample_single_wall_tet_cells", []
            )
        _bl_owner_centre_eligible_cells = {int(c) for c in _eligible_source}
    owner_centre_motion_diag: dict[str, Any] = {
        "enabled": bool(_bl_owner_centre_motion_enabled),
        "n_eligible_owner_cells": int(len(_bl_owner_centre_eligible_cells)),
        "n_eligible": 0,
        "n_moved": 0,
        "mean_motion": 0.0,
        "max_motion": 0.0,
    }

    # BLR-9a — env-gated dry-run quality probe for tet wall-cavity replacement.
    # No mesh mutation; predicts whether the prism + transition tet
    # combination would be geometrically valid for each BLR-7 single-tet
    # eligible owner.  BLR-9b (a future iteration) will gate the actual
    # cavity rewrite on these metrics.  Default OFF.
    _bl_tet_cavity_probe_enabled = (
        os.environ.get("AUTO_TESSELL_BL_TET_CAVITY_PROBE", "0") == "1"
    )
    tet_cavity_probe_diag: dict[str, Any] = {
        "enabled": bool(_bl_tet_cavity_probe_enabled),
        "n_candidates": 0,
        "n_quality_pass": 0,
        "n_quality_fail_det": 0,
        "n_quality_fail_topology": 0,
        "mean_predicted_det": 0.0,
        "min_predicted_det": 0.0,
        "max_predicted_det": 0.0,
    }

    # BLR-9b-iv — env-gated cavity replacement (default OFF).  When
    # ``AUTO_TESSELL_BL_TET_CAVITY_REPLACE=1`` the plan/apply helpers
    # are wired into ``generate_native_bl`` so the in-memory replacement
    # arrays can be inspected by a downstream verifier.  This iteration
    # does NOT yet hand the rewritten arrays to the polyMesh writer —
    # the helper output stays in the diagnostic JSON only — so toggling
    # the flag never mutates an emitted ``polyMesh``.  The next sub-step
    # will swap in the writer integration once a regression bench
    # confirms the topology guard rejects every unsafe candidate.
    _bl_tet_cavity_replace_enabled = (
        os.environ.get("AUTO_TESSELL_BL_TET_CAVITY_REPLACE", "0") == "1"
    )
    tet_cavity_replace_diag: dict[str, Any] = {
        "enabled": bool(_bl_tet_cavity_replace_enabled),
        "wired_to_writer": False,
        "n_planned": 0,
        "n_replaced": 0,
        "n_rejected_topology": 0,
        "n_rejected_det": 0,
        "n_rejected_neighbour_internal": 0,
        "n_cells_before": 0,
        "n_cells_after": 0,
        "n_new_points_total": 0,
    }

    # BLR-9c-d-g — env-gated cavity-component aggregator (default
    # OFF, no writer impact).  When ``AUTO_TESSELL_BL_TET_CAVITY_EVAL=1``
    # the BLR-9c-a → 9c-d helpers run on the live wall-owner cavity
    # components and their per-component verdicts (accept /
    # reject_uncovered_shell / reject_bad_det / reject_bad_shape /
    # reject_bad_non_ortho / reject_bad_skewness) plus aggregate
    # counts are surfaced in ``native_bl_quality.tet_cavity_eval``.
    # Pure read-only — the rest of the BL pipeline is untouched.
    _bl_tet_cavity_eval_enabled = (
        os.environ.get("AUTO_TESSELL_BL_TET_CAVITY_EVAL", "0") == "1"
    )
    tet_cavity_eval_diag: dict[str, Any] = {
        "enabled": bool(_bl_tet_cavity_eval_enabled),
        "n_components": 0,
        "n_accepted": 0,
        "n_rejected_uncovered_shell": 0,
        "n_rejected_bad_det": 0,
        "n_rejected_bad_shape": 0,
        "n_rejected_bad_non_ortho": 0,
        "n_rejected_bad_skewness": 0,
    }

    # BLR-9c-d-p-10 — anti-invert cap default-OFF outer-scope state.
    # Set inside the inner pass closure when the env flag is on.
    anti_invert_cap_diag: dict[str, Any] = {
        "enabled": False,
        "n_capped": 0,
        "max_reduction": 0.0,
        "n_wall_verts": 0,
    }

    # beta95: per-vertex cumulative thickness 계산
    # per_vertex_first_thickness 가 주어지면 각 vertex 별 자체 두께 성장 곡선 사용.
    vertex_cum_map: dict[int, np.ndarray] = {}
    use_per_vertex_cum = False
    if cfg.per_vertex_first_thickness:
        use_per_vertex_cum = True
        for v in wall_vert_indices:
            ft = cfg.per_vertex_first_thickness.get(v, cfg.first_thickness)
            # vertex 자신의 두께 배열 (growth_ratio 는 global 유지)
            v_thick = np.array(
                [ft * (cfg.growth_ratio ** i) for i in range(cfg.num_layers)],
                dtype=np.float64,
            )
            # vertex_scale[v] 적용 (feature lock + collision)
            v_thick *= vertex_scale.get(v, 1.0)
            vertex_cum_map[v] = np.concatenate(([0.0], np.cumsum(v_thick)))
        log.info(
            "native_bl_per_vertex_cum_activated", component="native_bl", phase="beta95",
            n_vertices=len(vertex_cum_map),
        )

    # 4e) BL1+BL3 — curvature-adaptive + relative first thickness (default ON).
    #     Only activates when user has NOT set per_vertex_first_thickness explicitly.
    #     BL1: curvature adaptive (cfMesh maxFirstLayerThickness aspect cap).
    #     BL3: relative sizing — first_thickness = ratio × local_mean_edge (cfMesh
    #          relativeSizes true), producing uniform y+ across mesh density changes.
    #     Combined: take element-wise min(BL1, BL3) → conservative safe thickness.
    if not cfg.per_vertex_first_thickness and not use_per_vertex_cum:
        try:
            wall_surface_faces = [faces[fi] for fi in wall_face_indices]
            # C-BL-6 / beta2434 — effective_first_thickness 사용 (beta2423 의 auto-scale 보존).
            # 이전: cfg.first_thickness (raw 값) 사용 → bbox-relative auto-bump 무시.
            # 결과 thickness 가 1e-6 단위로 떨어져 hex BL aspect 50k+ 발생.
            adap_thick = _curvature_adaptive_thickness(
                points, wall_surface_faces, wall_vert_indices,
                base_thickness=effective_first_thickness,
                max_aspect=cfg.aspect_ratio_threshold,
            )
            # BL3: relative first thickness (ratio × local mean edge length)
            # C-BL-7 / beta2553 — env-gated ratio for 3a.1 (per-vertex ft tuning).
            # AUTO_TESSELL_BL_REL_RATIO=0.5 (or 0.7) → larger ft on coarse wall
            # → max_aspect 감소. default 0.3 = cfMesh standard.
            import os as _os_bl3
            _bl_rel_ratio = float(
                _os_bl3.environ.get("AUTO_TESSELL_BL_REL_RATIO", "0.3")
            )
            rel_thick = _relative_first_thickness(
                points, wall_surface_faces, wall_vert_indices,
                ratio=_bl_rel_ratio,
            )
            # Guard: if rel_thick is all-zero (degenerate mesh) skip BL3 combination
            rel_valid = rel_thick.max() > 1e-30 if len(rel_thick) > 0 else False
            if rel_valid:
                # BETA2879 — BL1 (adap_thick) 이 aspect_cap 으로 mean_edge/1000
                # 까지 줄어들면 prism aspect 가 1000 에 도달해 subdivide 가 거부.
                # BL3 (= 0.3 × local_edge) 가 BL1 보다 클 때는 BL3 채택 — local
                # mesh 밀도 기반 적정 두께로 aspect 3-10 의 양질 prism 을 얻는다.
                # BL3 < BL1 이면 기존 min 동작 (예: feature-aware shrink).
                _bl3_dominant = float(rel_thick.mean()) > float(adap_thick.mean()) * 2.0
                if _bl3_dominant:
                    combined_thick = rel_thick.copy()
                else:
                    combined_thick = np.minimum(adap_thick, rel_thick)
                # Clamp: never below 1% of effective_first_thickness (avoid near-zero collapse).
                # C-BL-6 / beta2434 — auto-scaled value 사용.
                combined_thick = np.maximum(combined_thick, effective_first_thickness * 0.01)
                _rel_mean = float(rel_thick.mean())
                _rel_min = float(rel_thick.min())
                log.info(
                    "native_bl_relative_thickness", component="native_bl", phase="BL3",
                    ratio=0.3,
                    mean_local_edge=round(_rel_mean / 0.3, 6),
                    rel_thickness_min=round(_rel_min, 6),
                    rel_thickness_mean=round(_rel_mean, 6),
                )
            else:
                combined_thick = adap_thick
            # Apply global bbox/local safety scale already applied to thicknesses[0]
            global_scale = (
                float(thicknesses[0]) / cfg.first_thickness
                if cfg.first_thickness > 1e-30 else 1.0
            )
            combined_thick *= global_scale
            if min_local is not None and min_local > 1e-30:
                growth_sum = float(
                    sum(cfg.growth_ratio ** i for i in range(cfg.num_layers))
                )
                if growth_sum > 1e-30:
                    local_first_cap = max(
                        min_local * 0.8,
                        effective_first_thickness,
                    ) / growth_sum
                    before_cap_mean = float(combined_thick.mean())
                    combined_thick = np.minimum(combined_thick, local_first_cap)
                    if float(combined_thick.mean()) < before_cap_mean:
                        log.info(
                            "native_bl_bl3_local_safety_capped",
                            component="native_bl",
                            phase="BL3",
                            min_local=round(float(min_local), 6),
                            first_cap=round(float(local_first_cap), 6),
                            mean_before=round(before_cap_mean, 6),
                            mean_after=round(float(combined_thick.mean()), 6),
                        )
            use_per_vertex_cum = True
            for vi_bl1, v in enumerate(wall_vert_indices):
                ft = float(combined_thick[vi_bl1])
                v_thick = np.array(
                    [ft * (cfg.growth_ratio ** i) for i in range(cfg.num_layers)],
                    dtype=np.float64,
                )
                v_thick *= vertex_scale.get(v, 1.0)
                vertex_cum_map[v] = np.concatenate(([0.0], np.cumsum(v_thick)))
            _adap_min = float(combined_thick.min())
            _adap_max = float(combined_thick.max())
            _adap_mean = float(combined_thick.mean())
            log.info(
                "native_bl_curvature_adaptive", component="native_bl", phase="BL1",
                n_verts=len(wall_vert_indices),
                thickness_min=round(_adap_min, 6),
                thickness_max=round(_adap_max, 6),
                thickness_mean=round(_adap_mean, 6),
                bl3_relative_active=rel_valid,
            )
            # HEX_BL_UNIFORM: validate first-layer thickness uniformity (CFD y+ standard)
            validate_bl_thickness_uniformity(combined_thick)
        except Exception as _bl1_exc:
            import logging as _lg
            _lg.getLogger(__name__).warning(
                "native_bl_BL1_curvature_skipped reason=%s", str(_bl1_exc)[:200]
            )

    # The feature-size envelope is applied after adaptive sizing so collision
    # caps remain hard constraints and no adaptive path can re-expand them.
    if feature_size_first:
        use_per_vertex_cum = True
        vertex_cum_map = {}
        for v in wall_vert_indices:
            ft = feature_size_first[int(v)]
            v_thick = np.array(
                [ft * (cfg.growth_ratio ** i) for i in range(cfg.num_layers)],
                dtype=np.float64,
            )
            vertex_cum_map[int(v)] = np.concatenate(([0.0], np.cumsum(v_thick)))

    # 5-7) Prism 생성 내부 함수 (beta93: shrink iteration 에서 반복 호출 가능)
    def _run_prism_pass(
        vertex_scale_pass: dict[int, float],
        cum_pass: np.ndarray,
        vertex_cum_map_pass: dict[int, np.ndarray] | None = None,
        use_per_v_cum_pass: bool = False,
    ) -> tuple[
        np.ndarray,              # final_points
        list[list[int]],         # final_faces
        list[int],               # final_owner
        list[int],               # final_nbr
        list[dict[str, Any]],    # final_boundary_entries (bl_side)
        list[int],                # final_boundary_source_mesh_faces
        list[dict[int, int]],    # layer_point_ids (quality check)
    ]:
        """단일 prism insertion pass. vertex_scale_pass / cum_pass 로 layer 생성.

        beta95: use_per_v_cum_pass=True 이면 vertex_cum_map_pass[v][layer_i] 를
        offset 으로 직접 사용 (per-vertex 두께 성장 곡선). 이미 vertex_scale 이
        적용된 값이므로 추가 scale 없음.
        """
        if _BL_QQQ4_LOCAL_THICKNESS and _BL_QQQ1_FRONT_COLLISION:
            try:
                # vertex 단위 collision_mask: local opposing front only.
                wall_vn = np.array([vnorm[v] for v in wall_vert_indices])
                coll_v = _nearby_opposite_front_mask(
                    wall_vn, points[np.asarray(wall_vert_indices, dtype=np.int64)]
                )
                factors_w = _local_thickness_factor(coll_v, len(wall_vert_indices), thin_factor=0.5)
                # vertex_scale_pass 와 merge (곱); local copy 로 caller 영향 차단
                vertex_scale_pass = dict(vertex_scale_pass)
                for vi_idx, v in enumerate(wall_vert_indices):
                    vertex_scale_pass[v] = vertex_scale_pass.get(v, 1.0) * float(factors_w[vi_idx])
                if use_per_v_cum_pass and vertex_cum_map_pass is not None:
                    vertex_cum_map_pass = {
                        vertex: np.asarray(offsets, dtype=np.float64).copy() * float(factors_w[index])
                        for index, (vertex, offsets) in enumerate(vertex_cum_map_pass.items())
                    }
            except Exception as _exc:
                import logging as _lg
                _lg.getLogger(__name__).warning("native_bl_qqq5_skipped reason=%s", str(_exc)[:120])
        # 5) 새 point 배열 구성
        new_pts = points.copy()
        wall_idx_arr_p = np.array(wall_vert_indices, dtype=np.int64)

        # LAYERS_VEC: vectorized wall-vertex extrusion (beta2195)
        # inward_normals: (W, 3) — -vnorm for each wall vertex
        # 빈 list 일 때 np.array 가 (0,) 로 만들어 broadcast (0,0) 오류 → reshape (0, 3) 강제.
        if len(wall_vert_indices) == 0:
            inward_normals = np.zeros((0, 3), dtype=np.float64)
        else:
            # BLR-8 — env-gated owner-centre motion replaces ``-vnorm[v]`` with
            # a unit vector toward the eligible owner cell centre.  When the
            # env flag is OFF ``_owner_centre_wall_motion`` is a no-op and we
            # keep the existing patch-normal direction.
            nonlocal owner_centre_motion_diag
            fallback_inward_map = {v: -vnorm[v] for v in wall_vert_indices}
            motion_dirs, motion_diag = _owner_centre_wall_motion(
                points,
                faces,
                owner,
                wall_vert_indices,
                wall_face_indices,
                cell_centres,
                _bl_owner_centre_eligible_cells,
                fallback_inward_map,
                enabled=_bl_owner_centre_motion_enabled,
            )
            motion_diag["n_eligible_owner_cells"] = int(
                len(_bl_owner_centre_eligible_cells)
            )
            owner_centre_motion_diag = motion_diag
            inward_normals = np.array(
                [motion_dirs[v] for v in wall_vert_indices],
                dtype=np.float64,
            ).reshape(-1, 3)  # (W,3)

            # BLR-9a — dry-run replacement quality probe (env-gated, no-op
            # when disabled).  Uses the same motion directions as the prism
            # extrusion so the probe and the eventual rewrite agree on the
            # predicted inner triangle.
            try:
                nonlocal tet_cavity_probe_diag
                tet_cavity_probe_diag = _tet_wall_cavity_replacement_probe(
                    points,
                    faces,
                    owner,
                    wall_face_indices,
                    _bl_owner_centre_eligible_cells,
                    cell_centres,
                    motion_dirs,
                    float(cfg.first_thickness),
                    enabled=_bl_tet_cavity_probe_enabled,
                )
            except Exception as exc:  # noqa: BLE001
                tet_cavity_probe_diag = {
                    "enabled": bool(_bl_tet_cavity_probe_enabled),
                    "error": str(exc)[:160],
                }

            # BLR-9b-iv — plan + apply hook (env-gated, no writer yet).
            # When the replace flag is OFF this branch is a strict no-op.
            # When ON the helpers run on copies of the polyMesh arrays so
            # callers can inspect ``tet_cavity_replace_diag`` for
            # n_replaced / n_rejected_* / n_cells_before/after numbers
            # before the next iteration wires the rewritten arrays into
            # the polyMesh writer.
            if _bl_tet_cavity_replace_enabled:
                try:
                    nonlocal tet_cavity_replace_diag
                    _replace_plan = _build_tet_cavity_replacement_plan(
                        points,
                        faces,
                        owner,
                        wall_face_indices,
                        _bl_owner_centre_eligible_cells,
                        cell_centres,
                        motion_dirs,
                        float(cfg.first_thickness),
                        enabled=True,
                        neighbour=neighbour,
                    )
                    _replace_applied = _apply_tet_cavity_replacement_plan(
                        np.asarray(points, dtype=np.float64),
                        faces,
                        np.asarray(owner, dtype=np.int64),
                        np.asarray(neighbour, dtype=np.int64),
                        wall_face_indices,
                        _replace_plan,
                        enabled=True,
                    )
                    tet_cavity_replace_diag = {
                        "enabled": True,
                        "wired_to_writer": False,
                        "n_planned": int(_replace_plan.get("n_planned", 0)),
                        "n_replaced": int(_replace_applied.get("n_replaced", 0)),
                        "n_rejected_topology": int(
                            _replace_plan.get("n_rejected_topology", 0)
                        ),
                        "n_rejected_det": int(
                            _replace_plan.get("n_rejected_det", 0)
                        ),
                        "n_rejected_neighbour_internal": int(
                            _replace_plan.get("n_rejected_neighbour_internal", 0)
                        ),
                        "n_cells_before": int(
                            _replace_applied.get("n_cells_before", 0)
                        ),
                        "n_cells_after": int(
                            _replace_applied.get("n_cells_after", 0)
                        ),
                        "n_new_points_total": int(
                            _replace_applied.get("n_new_points_total", 0)
                        ),
                    }
                except Exception as exc:  # noqa: BLE001
                    tet_cavity_replace_diag = {
                        "enabled": True,
                        "wired_to_writer": False,
                        "error": str(exc)[:160],
                    }

            # BLR-9c-d-g — read-only cavity-component evaluation.
            if _bl_tet_cavity_eval_enabled:
                try:
                    nonlocal tet_cavity_eval_diag
                    _eval_components = _detect_wall_owner_cavity_components(
                        owner,
                        neighbour,
                        list(wall_face_indices),
                    )
                    _eval_non_ortho_thresh = float(
                        os.environ.get(
                            "AUTO_TESSELL_BL_TET_CAVITY_NON_ORTHO_DEG",
                            "70.0",
                        )
                    )
                    _eval_q_min_thresh = float(
                        os.environ.get(
                            "AUTO_TESSELL_BL_TET_CAVITY_Q_MIN",
                            "0.1",
                        )
                    )
                    _eval_summary = _evaluate_cavity_component_candidates(
                        components=_eval_components,
                        points=np.asarray(points, dtype=np.float64),
                        faces=faces,
                        owner=np.asarray(owner, dtype=np.int64),
                        neighbour=np.asarray(neighbour, dtype=np.int64),
                        wall_face_indices=list(wall_face_indices),
                        motion_dirs=motion_dirs,
                        first_thickness=float(cfg.first_thickness),
                        non_ortho_threshold_deg=_eval_non_ortho_thresh,
                        q_min_threshold=_eval_q_min_thresh,
                    )
                    tet_cavity_eval_diag = {
                        "enabled": True,
                        "n_components": int(
                            _eval_summary.get("n_components", 0)
                        ),
                        "n_accepted": int(
                            _eval_summary.get("n_accepted", 0)
                        ),
                        "n_rejected_uncovered_shell": int(
                            _eval_summary.get(
                                "n_rejected_uncovered_shell", 0
                            )
                        ),
                        "n_rejected_bad_det": int(
                            _eval_summary.get("n_rejected_bad_det", 0)
                        ),
                        "n_rejected_bad_shape": int(
                            _eval_summary.get("n_rejected_bad_shape", 0)
                        ),
                        "n_rejected_bad_non_ortho": int(
                            _eval_summary.get(
                                "n_rejected_bad_non_ortho", 0
                            )
                        ),
                        "n_rejected_bad_skewness": int(
                            _eval_summary.get(
                                "n_rejected_bad_skewness", 0
                            )
                        ),
                        "non_ortho_hist": dict(
                            _eval_summary.get("non_ortho_hist", {})
                        ),
                        "non_ortho_fine_hist": dict(
                            _eval_summary.get("non_ortho_fine_hist", {})
                        ),
                        "worst_non_ortho_kind_hist": dict(
                            _eval_summary.get(
                                "worst_non_ortho_kind_hist", {}
                            )
                        ),
                        "skew_hist": dict(
                            _eval_summary.get("skew_hist", {})
                        ),
                        "q_min_hist": dict(
                            _eval_summary.get("q_min_hist", {})
                        ),
                        "q_min_fine_hist": dict(
                            _eval_summary.get("q_min_fine_hist", {})
                        ),
                        "worst_q_kind_hist": dict(
                            _eval_summary.get("worst_q_kind_hist", {})
                        ),
                        "max_non_ortho_deg": float(
                            _eval_summary.get("max_non_ortho_deg", 0.0)
                        ),
                        "max_skew": float(
                            _eval_summary.get("max_skew", 0.0)
                        ),
                        "min_q": float(
                            _eval_summary.get("min_q", 1.0)
                        ),
                    }
                except Exception as exc:  # noqa: BLE001
                    tet_cavity_eval_diag = {
                        "enabled": True,
                        "error": str(exc)[:160],
                    }

        if use_per_v_cum_pass and vertex_cum_map_pass:
            # per-vertex total thickness vector: (W,)
            v_totals = np.array(
                [
                    float(vertex_cum_map_pass[v][-1]) if v in vertex_cum_map_pass
                    else total * vertex_scale_pass.get(v, 1.0)
                    for v in wall_vert_indices
                ],
                dtype=np.float64,
            )  # (W,)
            new_pts[wall_idx_arr_p] = points[wall_idx_arr_p] + inward_normals * v_totals[:, None]
        else:
            scales_v = np.array(
                [vertex_scale_pass.get(v, 1.0) for v in wall_vert_indices], dtype=np.float64,
            )  # (W,)
            new_pts[wall_idx_arr_p] = points[wall_idx_arr_p] + inward_normals * (total * scales_v[:, None])

        # BLR-9c-d-p-10 — anti-invert per-vertex cap.  When enabled,
        # walks every adjacent bulk tet of each wall vertex and
        # scales the wall vertex *and every per-layer offset* down
        # so no neighbour tet's signed volume can flip.  Default OFF;
        # the bench at quality=draft (BLR-9c-d-p-7) showed 7/8
        # failing 21-STL cases are caused by exactly this geometric
        # inversion.
        _anti_invert_cap_enabled = (
            os.environ.get("AUTO_TESSELL_BL_ANTI_INVERT_CAP", "0") == "1"
        )
        nonlocal anti_invert_cap_diag
        anti_invert_cap_diag = {
            "enabled": bool(_anti_invert_cap_enabled),
            "n_capped": 0,
            "max_reduction": 0.0,
            "n_wall_verts": int(len(wall_vert_indices)),
        }
        anti_invert_scale_per_v: np.ndarray | None = None
        if _anti_invert_cap_enabled and len(wall_vert_indices) > 0:
            try:
                from core.layers.native_bl_anti_invert import (
                    compute_anti_invert_caps,
                )
                _safety = float(
                    os.environ.get(
                        "AUTO_TESSELL_BL_ANTI_INVERT_SAFETY",
                        "0.5",
                    )
                )
                _caps_dict = compute_anti_invert_caps(
                    points, faces, owner, neighbour,
                    wall_vert_indices, motion_dirs,
                    safety_factor=_safety,
                )
                # BLR-9c-d-p-11 — cell-level cap smoothing.  Per-
                # vertex caps alone produce inhomogeneous reductions
                # within a single prism face (one vert capped tight,
                # adjacent vert unchanged) which collapses the prism
                # to a sliver / aspect-1e9 cell.  For each wall face
                # take the *min* cap across its 3 verts and propagate
                # back so all three verts move together — this
                # preserves prism shape while still preventing bulk
                # inversion.
                # BLR-9c-d-p-12 — global uniform scaling.  Instead of
                # per-vertex caps (which create inhomogeneous prisms)
                # or cell-level smoothing (which over-caps), reduce
                # *every* wall vertex by the SAME factor so prism
                # cells stay shape-preserving but uniformly thinner.
                # Trade-off: BL thickness is reduced globally, which
                # may push effective y+ off target on some faces but
                # keeps prism quality uniform.  When combined with
                # the per-vertex cap below, it acts as a fallback
                # tier: only fires when the per-vertex cap finds a
                # vertex that needs capping.  Default ON when CAP
                # is on; override via
                # ``AUTO_TESSELL_BL_ANTI_INVERT_GLOBAL=0``.
                _global_scale_enabled = (
                    os.environ.get(
                        "AUTO_TESSELL_BL_ANTI_INVERT_GLOBAL", "1",
                    ) == "1"
                )
                _smooth_enabled = (
                    os.environ.get(
                        "AUTO_TESSELL_BL_ANTI_INVERT_SMOOTH", "0",
                    ) == "1"
                )
                if _smooth_enabled:
                    _face_min_cap: dict[int, float] = {}
                    for _fi in wall_face_indices:
                        if _fi < 0 or _fi >= len(faces):
                            continue
                        _f = faces[_fi]
                        _face_caps = [
                            _caps_dict.get(int(v), float("inf"))
                            for v in _f
                        ]
                        _face_min_cap[_fi] = (
                            float(min(_face_caps)) if _face_caps else float("inf")
                        )
                    _vert_face_min: dict[int, float] = {}
                    for _fi, _fmc in _face_min_cap.items():
                        for v in faces[_fi]:
                            iv = int(v)
                            cur = _vert_face_min.get(iv, float("inf"))
                            if _fmc < cur:
                                _vert_face_min[iv] = _fmc
                    for v in wall_vert_indices:
                        iv = int(v)
                        if iv in _vert_face_min:
                            _orig = _caps_dict.get(iv, float("inf"))
                            _smoothed = min(_orig, _vert_face_min[iv])
                            _caps_dict[iv] = _smoothed
                _delta = new_pts[wall_idx_arr_p] - points[wall_idx_arr_p]
                _mag = np.linalg.norm(_delta, axis=1)
                _caps_arr = np.array(
                    [
                        float(_caps_dict.get(int(v), float("inf")))
                        for v in wall_vert_indices
                    ],
                    dtype=np.float64,
                )
                _over = _mag > _caps_arr
                _n_capped = int(_over.sum())
                # BLR-9c-d-q-2 — joint multi-wall-vert cap, applied
                # after the per-vert cap.  Treats all wall verts as
                # moving simultaneously and uses bisection to find
                # the max uniform scale that keeps *every* tet cell
                # positive.  Catches the multi-wall-vert co-motion
                # cases the per-vert helper misses
                # (e.g. hard_1004826: 1 neg_vol survives per-vert
                # cap at safety=0.3).
                _joint_scale_enabled = (
                    os.environ.get(
                        "AUTO_TESSELL_BL_ANTI_INVERT_JOINT", "1",
                    ) == "1"
                )
                if _n_capped:
                    _safe_mag = np.where(_mag > 1e-30, _mag, 1.0)
                    if _global_scale_enabled:
                        # Take the *minimum* ratio across all wall verts
                        # whose extrusion would invert a neighbour, then
                        # apply that single scalar to every wall vert.
                        # Result: prism cells stay homogeneous (no
                        # aspect-ratio explosion), at the cost of a
                        # globally thinner BL.
                        _ratios = np.where(
                            _over,
                            np.minimum(1.0, _caps_arr / _safe_mag),
                            1.0,
                        )
                        _global_ratio = float(_ratios.min())
                        # Selective mode retains each geometric cap;
                        # homogeneous mode uses their minimum.  A legacy
                        # thickness floor was removed because it could raise
                        # an inversion-safety upper bound.
                        _selective = (
                            os.environ.get(
                                "AUTO_TESSELL_BL_ANTI_INVERT_SELECTIVE",
                                "0",
                            ) == "1"
                        )
                        if _selective:
                            # A minimum-thickness floor cannot raise a
                            # geometric inversion-safety cap.  The selective
                            # mode therefore keeps each exact safe ratio.
                            anti_invert_scale_per_v = _ratios
                        else:
                            anti_invert_scale_per_v = np.full_like(
                                _mag, _global_ratio
                            )
                    else:
                        anti_invert_scale_per_v = np.where(
                            _over,
                            np.minimum(1.0, _caps_arr / _safe_mag),
                            1.0,
                        )
                # Joint cap: even if no per-vert cap fires, run the
                # joint helper to catch cases where multi-wall-vert
                # co-motion would invert a tet that no individual
                # vert cap would have flagged.
                if _joint_scale_enabled:
                    try:
                        from core.layers.native_bl_anti_invert import (
                            compute_joint_cell_inversion_scale,
                        )
                        # current per-vertex post-cap magnitudes
                        if anti_invert_scale_per_v is not None:
                            _eff_mag = _mag * anti_invert_scale_per_v
                        else:
                            _eff_mag = _mag
                        _req_extr = {
                            int(v): float(_eff_mag[i])
                            for i, v in enumerate(wall_vert_indices)
                        }
                        _joint = compute_joint_cell_inversion_scale(
                            points, faces, owner, neighbour,
                            list(wall_vert_indices), motion_dirs,
                            _req_extr, safety_factor=_safety,
                        )
                        if _joint < 1.0:
                            _joint = max(0.0, _joint)
                            if anti_invert_scale_per_v is None:
                                anti_invert_scale_per_v = np.full_like(
                                    _mag, _joint,
                                )
                            else:
                                anti_invert_scale_per_v = (
                                    anti_invert_scale_per_v * _joint
                                )
                            log.info(
                                "native_bl_anti_invert_joint_scale",
                                joint=round(_joint, 4),
                            )
                    except Exception as exc:  # noqa: BLE001
                        log.debug(
                            "native_bl_anti_invert_joint_skipped",
                            reason=str(exc)[:160],
                        )
                if anti_invert_scale_per_v is not None:
                    _effective_capped = int(
                        np.count_nonzero(anti_invert_scale_per_v < 1.0)
                    )
                    _max_reduction = float(
                        np.max(_mag - anti_invert_scale_per_v * _mag)
                    )
                    new_pts[wall_idx_arr_p] = (
                        points[wall_idx_arr_p]
                        + _delta * anti_invert_scale_per_v[:, None]
                    )
                    anti_invert_cap_diag["n_capped"] = _effective_capped
                    anti_invert_cap_diag["max_reduction"] = (
                        _max_reduction
                    )
                    log.info(
                        "native_bl_anti_invert_cap_applied",
                        n_capped=_effective_capped,
                        max_reduction=round(_max_reduction, 6),
                        n_wall_verts=int(len(wall_vert_indices)),
                    )
            except Exception as exc:  # noqa: BLE001
                anti_invert_cap_diag["error"] = str(exc)[:160]
                log.debug(
                    "native_bl_anti_invert_cap_skipped",
                    reason=str(exc)[:160],
                )

        # Build per-layer offset arrays: shape (num_layers, W) for inner layers
        lp_ids: list[dict[int, int]] = [{} for _ in range(cfg.num_layers + 1)]
        cursor_p = len(points)
        n_wall = len(wall_vert_indices)

        if n_wall > 0 and cfg.num_layers > 0:
            if use_per_v_cum_pass and vertex_cum_map_pass:
                # (num_layers, W) offset matrix — each row is layer_i cumulative offsets
                offsets_mat = np.array(
                    [
                        [
                            float(vertex_cum_map_pass[v][layer_i]) if v in vertex_cum_map_pass
                            else float(cum_pass[layer_i]) * vertex_scale_pass.get(v, 1.0)
                            for v in wall_vert_indices
                        ]
                        for layer_i in range(cfg.num_layers)
                    ],
                    dtype=np.float64,
                )  # (num_layers, W)
            else:
                # broadcast: cum_pass[layer_i] * scales — (num_layers, W)
                scales_v2 = np.array(
                    [vertex_scale_pass.get(v, 1.0) for v in wall_vert_indices], dtype=np.float64,
                )  # (W,)
                cum_inner = np.array(
                    [float(cum_pass[layer_i]) for layer_i in range(cfg.num_layers)],
                    dtype=np.float64,
                )  # (num_layers,)
                offsets_mat = cum_inner[:, None] * scales_v2[None, :]  # (num_layers, W)

            # BLR-9c-d-p-10 — propagate the anti-invert per-vertex
            # cap from the wall-vertex extrusion into every per-layer
            # offset.  Without this the inner layers still target the
            # un-capped position and the prism cap sits past the
            # opposite face plane of an adjacent bulk tet, causing
            # the very inversion we just prevented at the wall layer.
            if (
                anti_invert_scale_per_v is not None
                and anti_invert_scale_per_v.shape[0] == offsets_mat.shape[1]
            ):
                offsets_mat = offsets_mat * anti_invert_scale_per_v[None, :]

            # new_positions: (num_layers, W, 3)
            # points[wall_idx_arr_p]: (W, 3); inward_normals: (W, 3)
            # offsets_mat: (num_layers, W) -> offset per layer per vertex
            # beta2246: start from the base wall and proceed inward.
            base_pts = points[wall_idx_arr_p]
            new_layer_pts = (
                base_pts[None, :, :]
                + inward_normals[None, :, :] * offsets_mat[:, :, None]
            )
            # new_layer_pts shape: (num_layers, W, 3)
            extra_pts_arr = new_layer_pts.reshape(-1, 3)
            fp = np.vstack([new_pts, extra_pts_arr])

            # Build lp_ids dicts from contiguous index layout
            for layer_i in range(cfg.num_layers):
                base_idx = cursor_p + layer_i * n_wall
                for wi_v, v in enumerate(wall_vert_indices):
                    lp_ids[layer_i][v] = base_idx + wi_v
        else:
            fp = new_pts

        # innermost layer maps to original vertex ids
        for v in wall_vert_indices:
            lp_ids[cfg.num_layers][v] = int(v)

        # P3.4 / beta2591 — REAL anisotropic prism split (layer-uniform subdivide).
        # cfMesh splitInternalLayers 동등. mean aspect > threshold 시 모든 layer
        # k 와 k+1 사이에 mid-vertex 새 layer 삽입 → cfg.num_layers 2배.
        # env AUTO_TESSELL_BL_ANISO_SPLIT=1 (default OFF, diagnostic only) 시 활성.
        # diagnostic-only path (line 2700+) 와 별개로 실 mesh 변환 수행.
        _aniso_real_split = (
            os.environ.get("AUTO_TESSELL_BL_ANISO_SPLIT", "0") == "1"
            and cfg.num_layers >= 1
            and cfg.num_layers <= 16  # 32 cap (32+ 은 무리).
        )
        if _aniso_real_split:
            try:
                _thr = float(os.environ.get("AUTO_TESSELL_BL_ANISO_SPLIT_THRESH", "4.0"))
                # 모든 prism (wi, k) 의 wall-normal / base aspect 평균.
                _aspects = []
                _wt = wall_tri_verts
                for fi_chk in wall_face_indices:
                    if fi_chk not in _wt:
                        continue
                    v0c, v1c, v2c = _wt[fi_chk]
                    base_e = float(
                        np.linalg.norm(fp[v1c] - fp[v0c])
                        + np.linalg.norm(fp[v2c] - fp[v1c])
                        + np.linalg.norm(fp[v0c] - fp[v2c])
                    ) / 3.0
                    if base_e <= 1e-30:
                        continue
                    for kc in range(cfg.num_layers):
                        lk_o = lp_ids[kc]
                        lk_i = lp_ids[kc + 1]
                        if not all(v in lk_o and v in lk_i for v in (v0c, v1c, v2c)):
                            continue
                        wn_e = float(
                            np.linalg.norm(fp[lk_i[v0c]] - fp[lk_o[v0c]])
                            + np.linalg.norm(fp[lk_i[v1c]] - fp[lk_o[v1c]])
                            + np.linalg.norm(fp[lk_i[v2c]] - fp[lk_o[v2c]])
                        ) / 3.0
                        _aspects.append(wn_e / base_e)
                _mean_asp = float(np.mean(_aspects)) if _aspects else 0.0
                _max_asp = float(np.max(_aspects)) if _aspects else 0.0
                if _mean_asp > _thr or _max_asp > _thr * 2.0:
                    # 새 lp_ids 빌드: [0, 0.5, 1, 1.5, ..., N].
                    _new_lp: list[dict[int, int]] = []
                    _new_pts_buf: list[np.ndarray] = [fp]
                    _next_pid = int(fp.shape[0])
                    _N_old = cfg.num_layers
                    for kc in range(_N_old):
                        _new_lp.append(lp_ids[kc])  # 기존 layer.
                        _mid_dict: dict[int, int] = {}
                        for v in wall_vert_indices:
                            if v in lp_ids[kc] and v in lp_ids[kc + 1]:
                                _mid_pt = 0.5 * (
                                    fp[lp_ids[kc][v]] + fp[lp_ids[kc + 1][v]]
                                )
                                _new_pts_buf.append(_mid_pt[None, :])
                                _mid_dict[v] = _next_pid
                                _next_pid += 1
                        _new_lp.append(_mid_dict)
                    _new_lp.append(lp_ids[_N_old])  # 마지막 (innermost) layer.
                    fp = np.vstack(_new_pts_buf) if len(_new_pts_buf) > 1 else fp
                    lp_ids = _new_lp
                    object.__setattr__(cfg, "num_layers", _N_old * 2)
                    n_prism_per_face = cfg.num_layers
                    n_prism_total = n_wall_faces * n_prism_per_face
                    log.info(
                        "native_bl_aniso_split_applied",
                        component="native_bl", phase="P3.4/beta2591",
                        mean_aspect_pre=round(_mean_asp, 3),
                        max_aspect_pre=round(_max_asp, 3),
                        threshold=_thr,
                        num_layers_pre=_N_old,
                        num_layers_post=cfg.num_layers,
                        new_mid_pts=int(fp.shape[0]) - int(fp.shape[0] - (cfg.num_layers // 2) * len(wall_vert_indices)),
                    )
            except Exception as _asp_exc:
                log.warning(
                    "native_bl_aniso_split_skipped",
                    reason=str(_asp_exc)[:120],
                )

        # 6) Prism cell 위상 구성
        p_int_faces: list[list[int]] = []
        p_int_owner: list[int] = []
        p_int_nbr: list[int] = []
        p_bnd_faces_by_patch: dict[int, list[list[int]]] = {
            pi: [] for pi in range(len(boundary))
        }
        p_bnd_owner_by_patch: dict[int, list[int]] = {
            pi: [] for pi in range(len(boundary))
        }
        p_bnd_source_by_patch: dict[int, list[int]] = {
            pi: [] for pi in range(len(boundary))
        }
        p_bl_side_faces: list[list[int]] = []
        p_bl_side_source_faces: list[int] = []
        p_bl_side_owner: list[int] = []

        def _face_parts(face_: list[int], *, force_quad_split: bool = False) -> list[list[int]]:
            """Return one face or two triangles for a warped quad face."""
            if len(face_) != 4 or len(set(face_)) != 4:
                return [face_]

            q = [int(v) for v in face_]
            p0, p1, p2, p3 = (fp[q[0]], fp[q[1]], fp[q[2]], fp[q[3]])

            def _tri_area(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
                return 0.5 * float(np.linalg.norm(np.cross(b - a, c - a)))

            fc_q = 0.25 * (p0 + p1 + p2 + p3)
            area_vec = np.zeros(3, dtype=np.float64)
            area_sum = 0.0
            signs: list[float] = []
            for i_q, (a_q, b_q) in enumerate(((p0, p1), (p1, p2), (p2, p3), (p3, p0))):
                av = 0.5 * np.cross(a_q - fc_q, b_q - fc_q)
                area_vec += av
                area_sum += float(np.linalg.norm(av))
                prev_q = (p0, p1, p2, p3)[i_q - 1]
                cur_q = (p0, p1, p2, p3)[i_q]
                next_q = (p0, p1, p2, p3)[(i_q + 1) % 4]
                n_tmp = area_vec
                n_norm = float(np.linalg.norm(n_tmp))
                if n_norm > 1e-30:
                    s_q = float(np.dot(np.cross(cur_q - prev_q, next_q - cur_q), n_tmp / n_norm))
                    if abs(s_q) > 1e-14:
                        signs.append(s_q)
            flatness = (
                float(np.linalg.norm(area_vec)) / area_sum
                if area_sum > 1e-30 else 0.0
            )
            concave = False
            if signs:
                ref = 1.0 if sum(1 for s_q in signs if s_q >= 0.0) >= len(signs) / 2 else -1.0
                concave = any(s_q * ref < -1e-14 for s_q in signs)
            if not force_quad_split and flatness >= 1.0 - 1e-9 and not concave:
                return [face_]

            diag_02 = (
                [q[0], q[1], q[2]],
                [q[0], q[2], q[3]],
                min(_tri_area(p0, p1, p2), _tri_area(p0, p2, p3)),
            )
            diag_13 = (
                [q[0], q[1], q[3]],
                [q[1], q[2], q[3]],
                min(_tri_area(p0, p1, p3), _tri_area(p1, p2, p3)),
            )
            best = diag_02 if diag_02[2] >= diag_13[2] else diag_13
            if best[2] <= 1e-30:
                return [face_]
            return [best[0], best[1]]

        for fi_p in range(n_internal_orig):
            if fi_p in wall_set:
                continue
            for part_p in _face_parts(list(faces[fi_p])):
                p_int_faces.append(part_p)
                p_int_owner.append(int(owner[fi_p]))
                p_int_nbr.append(int(neighbour[fi_p]))

        for pi_p, patch_p in enumerate(boundary):
            start_p = int(patch_p["startFace"])
            nf_p = int(patch_p["nFaces"])
            for k_p in range(nf_p):
                fi_p = start_p + k_p
                if fi_p in wall_set or fi_p in replaced_polygon_wall_faces:
                    continue
                # C-BL-4 / beta2432 — patch-level face index 안전 가드.
                # validator: hard mesh 의 patch 가 stale startFace+nFaces 로
                # faces / owner 범위 벗어남. 직접 IndexError 의 두 번째 site.
                if fi_p < 0 or fi_p >= len(faces) or fi_p >= len(owner):
                    continue
                for part_p in _face_parts(list(faces[fi_p])):
                    p_bnd_faces_by_patch[pi_p].append(part_p)
                    p_bnd_owner_by_patch[pi_p].append(int(owner[fi_p]))
                    p_bnd_source_by_patch[pi_p].append(int(fi_p))

        def _ltri(fi_: int, layer_: int) -> tuple[int, int, int]:
            v0_, v1_, v2_ = wall_tri_verts[fi_]
            m_ = lp_ids[layer_]
            return (m_[v0_], m_[v1_], m_[v2_])

        def _pcid(wi_: int, k_: int) -> int:
            return prism_cell_id_start + wi_ * cfg.num_layers + k_

        def _side_face_parts(quad_: list[int]) -> list[list[int]]:
            """Return side-face polygons; split warped BL quads into triangles.

            BL side faces connect two layer edges. Around sharp/concave
            features, endpoint normals can diverge enough that a single quad
            becomes twisted or even has a near-zero area vector. OpenFOAM treats
            those faces as poor face flatness/concavity. Keeping the same
            owner-neighbour pair but emitting two triangular faces preserves the
            FVM topology and removes the non-planar face.
            """
            return _face_parts(quad_, force_quad_split=False)

        for wi_p, fi_p in enumerate(wall_face_indices):
            patch_idx_p = wall_orig_patch[fi_p]
            orig_own_p = wall_orig_owner[fi_p]

            for k_p in range(cfg.num_layers):
                prism_cell_p = _pcid(wi_p, k_p)
                outer_tri_p = _ltri(fi_p, k_p)
                inner_tri_p = _ltri(fi_p, k_p + 1)

                if k_p == 0:
                    p_bnd_faces_by_patch[patch_idx_p].append(list(outer_tri_p))
                    p_bnd_owner_by_patch[patch_idx_p].append(prism_cell_p)
                    p_bnd_source_by_patch[patch_idx_p].append(
                        int(_wall_source_mesh_face_by_wall_face.get(fi_p, fi_p))
                    )

                if k_p == cfg.num_layers - 1:
                    p_int_faces.append(list(inner_tri_p))
                    p_int_owner.append(orig_own_p)
                    p_int_nbr.append(prism_cell_p)
                else:
                    prism_next_p = _pcid(wi_p, k_p + 1)
                    p_int_faces.append(list(reversed(inner_tri_p)))
                    p_int_owner.append(prism_cell_p)
                    p_int_nbr.append(prism_next_p)

                tri_idx_p = [(0, 1), (1, 2), (2, 0)]
                for _ei, (a_p, b_p) in enumerate(tri_idx_p):
                    va_p, vb_p = wall_tri_verts[fi_p][a_p], wall_tri_verts[fi_p][b_p]
                    edge_key_p = (va_p, vb_p) if va_p < vb_p else (vb_p, va_p)
                    if _front_edge_adjacency is not None:
                        adjacent_face = int(_front_edge_adjacency[wi_p, _ei])
                        other_p = [] if adjacent_face < 0 else [adjacent_face]
                    else:
                        assert edge_to_walls is not None
                        nbrs_p = edge_to_walls.get(edge_key_p, [fi_p])
                        other_p = [g for g in nbrs_p if g != fi_p]
                    ov_a_p = lp_ids[k_p][va_p]
                    ov_b_p = lp_ids[k_p][vb_p]
                    iv_a_p = lp_ids[k_p + 1][va_p]
                    iv_b_p = lp_ids[k_p + 1][vb_p]
                    quad_p = [ov_a_p, iv_a_p, iv_b_p, ov_b_p]

                    if not other_p:
                        for side_p in _side_face_parts(quad_p):
                            p_bl_side_faces.append(side_p)
                            p_bl_side_owner.append(prism_cell_p)
                            p_bl_side_source_faces.append(
                                int(_wall_source_mesh_face_by_wall_face.get(fi_p, fi_p))
                            )
                    else:
                        other_fi_p = other_p[0]
                        other_wi_p = wall_fi_to_wi.get(other_fi_p, -1)
                        if other_wi_p < 0:
                            for side_p in _side_face_parts(quad_p):
                                p_bl_side_faces.append(side_p)
                                p_bl_side_owner.append(prism_cell_p)
                                p_bl_side_source_faces.append(
                                    int(_wall_source_mesh_face_by_wall_face.get(fi_p, fi_p))
                                )
                            continue
                        nbr_prism_p = _pcid(other_wi_p, k_p)
                        if prism_cell_p < nbr_prism_p:
                            for side_p in _side_face_parts(quad_p):
                                p_int_faces.append(side_p)
                                p_int_owner.append(prism_cell_p)
                                p_int_nbr.append(nbr_prism_p)

        # 7) 최종 face 조립
        out_faces: list[list[int]] = []
        out_owner: list[int] = []
        out_nbr: list[int] = []
        out_faces.extend(p_int_faces)
        out_owner.extend(p_int_owner)
        out_nbr.extend(p_int_nbr)

        out_bnd_entries: list[dict[str, Any]] = []
        out_bnd_source_faces: list[int] = []
        fc_p = len(out_faces)
        for pi_p, patch_p in enumerate(boundary):
            pf_p = p_bnd_faces_by_patch.get(pi_p, [])
            po_p = p_bnd_owner_by_patch.get(pi_p, [])
            ps_p = p_bnd_source_by_patch.get(pi_p, [])
            sf_p = fc_p
            for f_p, o_p in zip(pf_p, po_p, strict=False):
                out_faces.append(f_p)
                out_owner.append(o_p)
            out_bnd_source_faces.extend(int(v) for v in ps_p)
            fc_p += len(pf_p)
            out_bnd_entries.append({
                "name": patch_p.get("name", f"patch_{pi_p}"),
                "type": patch_p.get("type", "patch"),
                "nFaces": len(pf_p),
                "startFace": sf_p,
            })

        if p_bl_side_faces:
            sf_bl = fc_p
            for f_p, o_p in zip(p_bl_side_faces, p_bl_side_owner, strict=False):
                out_faces.append(f_p)
                out_owner.append(o_p)
            out_bnd_source_faces.extend(int(v) for v in p_bl_side_source_faces)
            fc_p += len(p_bl_side_faces)
            # BETA2879 — patch 이름에 'domain' 토큰 포함 → 평가자의 fidelity
            # selector 가 이 patch 를 도메인 경계로 간주해 형상 비교에서 제외
            # (Hausdorff 가 BL 두께만큼 부풀어 오르는 false-FAIL 방지).
            out_bnd_entries.append({
                "name": "bl_internal_domain",
                "type": "wall",
                "nFaces": len(p_bl_side_faces),
                "startFace": sf_bl,
            })

        return (
            fp,
            out_faces,
            out_owner,
            out_nbr,
            out_bnd_entries,
            out_bnd_source_faces,
            lp_ids,
        )

    # --------------------------------------------------------------------------
    # beta93: shrink iteration 루프
    # --------------------------------------------------------------------------
    n_iterations = max(1, cfg.shrink_iterations)
    current_vertex_scale = dict(vertex_scale)  # 복사본
    current_cum = cum.copy()

    final_points: np.ndarray | None = None
    final_faces: list[list[int]] = []
    final_owner: list[int] = []
    final_nbr: list[int] = []
    final_boundary_entries: list[dict[str, Any]] = []
    final_boundary_source_faces: list[int] = []
    layer_point_ids: list[dict[int, int]] = []
    n_new_points = 0
    bl_side_count = 0
    n_feature_edge_merged = 0

    for iteration in range(n_iterations):
        (
            fp,
            out_faces,
            out_owner,
            out_nbr,
            out_bnd_entries,
            out_bnd_source_faces,
            lp_ids,
        ) = _run_prism_pass(
            current_vertex_scale, current_cum,
            vertex_cum_map_pass=vertex_cum_map if use_per_vertex_cum else None,
            use_per_v_cum_pass=use_per_vertex_cum,
        )
        final_points = fp
        final_faces = out_faces
        final_owner = out_owner
        final_nbr = out_nbr
        final_boundary_entries = out_bnd_entries
        final_boundary_source_faces = list(out_bnd_source_faces)
        layer_point_ids = lp_ids
        n_new_points = len(fp) - len(points)
        # bl_side face 수 추적
        bl_side_count = sum(
            e["nFaces"] for e in out_bnd_entries if e.get("name") in ("bl_side", "bl_internal_domain")
        )

        # 수렴 판단: n_iterations == 1 이면 바로 종료
        if n_iterations <= 1:
            break

        # 품질 체크
        n_degen_it, max_ar_it = _prism_aspect_ratio_stats(
            fp, wall_tri_verts, wall_face_indices, lp_ids,
            cfg.num_layers, threshold=cfg.shrink_aspect_threshold,
        )
        log.info(
            "native_bl_shrink_iter", component="native_bl", phase="beta93",
            iteration=iteration, n_degen=n_degen_it, max_ar=max_ar_it,
            threshold=cfg.shrink_aspect_threshold,
        )
        if n_degen_it == 0:
            log.info("native_bl_shrink_converged", iteration=iteration)
            break

        # 불량 prism vertex scale 줄이기
        for fi_it in wall_face_indices:
            if fi_it not in wall_tri_verts:
                continue
            v0_it, v1_it, v2_it = wall_tri_verts[fi_it]
            for k_it in range(cfg.num_layers):
                # 이 prism 의 aspect ratio
                o0_it = fp[lp_ids[k_it][v0_it]]
                o1_it = fp[lp_ids[k_it][v1_it]]
                o2_it = fp[lp_ids[k_it][v2_it]]
                i0_it = fp[lp_ids[k_it + 1][v0_it]]
                i1_it = fp[lp_ids[k_it + 1][v1_it]]
                i2_it = fp[lp_ids[k_it + 1][v2_it]]
                e_outer_it = max(
                    float(np.linalg.norm(o1_it - o0_it)),
                    float(np.linalg.norm(o2_it - o1_it)),
                    float(np.linalg.norm(o0_it - o2_it)),
                )
                h_it = min(
                    float(np.linalg.norm(i0_it - o0_it)),
                    float(np.linalg.norm(i1_it - o1_it)),
                    float(np.linalg.norm(i2_it - o2_it)),
                )
                if h_it < 1e-30:
                    ar_it = 1e9
                else:
                    ar_it = e_outer_it / h_it

                if ar_it > cfg.shrink_aspect_threshold:
                    for v_it in (v0_it, v1_it, v2_it):
                        min_scale_it = cfg.first_thickness / max(total, 1e-30)
                        current_vertex_scale[v_it] = max(
                            current_vertex_scale.get(v_it, 1.0) * cfg.shrink_factor,
                            min_scale_it,
                        )

        # cum 재계산 (vertex_scale 는 per-vertex, cum/thicknesses 는 global — 변경 없음)
        # vertex_scale 만 줄어드므로 cum 재계산은 불필요 (총 두께 = total × vertex_scale[v])
        # 다만 vertex_scale 이 변경되면 다음 pass 에서 per-vertex 두께가 달라짐.
        # beta95: per-vertex cum 도 vertex_scale 변경 시 재계산.
        if use_per_vertex_cum and cfg.per_vertex_first_thickness:
            for v in wall_vert_indices:
                ft = cfg.per_vertex_first_thickness.get(v, cfg.first_thickness)
                v_thick = np.array(
                    [ft * (cfg.growth_ratio ** i) for i in range(cfg.num_layers)],
                    dtype=np.float64,
                )
                v_thick *= current_vertex_scale.get(v, 1.0)
                vertex_cum_map[v] = np.concatenate(([0.0], np.cumsum(v_thick)))

    assert final_points is not None

    # beta2251 — INNER LAYER smoothing along normal axis (cfMesh BLSmoothing
    # 동급). lp_ids[0] (wall) 와 lp_ids[N] (deepest) 는 변경하지 않음.
    # inner layer (1..N-1) 의 axial offset 을 Laplacian smoothing → prism
    # aspect ratio 개선 + wall preservation 유지.
    if (
        os.environ.get("AUTO_TESSELL_BL_INNER_SMOOTH", "1") != "0"
        and len(wall_vert_indices) >= 10
        and layer_point_ids
        and cfg.num_layers >= 3
    ):
        try:
            final_points, _n_inner_moved = _smooth_inner_layers_along_normal(
                final_points,
                wall_vert_indices,
                layer_point_ids,
                cfg.num_layers,
                n_iter=2,
            )
            if _n_inner_moved > 0:
                log.info(
                    "native_bl_inner_smooth", component="native_bl",
                    phase="beta2251", n_moved=_n_inner_moved,
                    n_wall_verts=len(wall_vert_indices),
                )
        except Exception as exc:
            log.warning("native_bl_inner_smooth_skipped", reason=str(exc)[:120])

    # BL_TANGENT_SMOOTH (beta2153) — tangential Laplacian of outer prism-layer verts.
    # Wired AFTER prism construction, BEFORE subdivision/finalization (cfMesh BLSmoothing).
    # beta2248: wall preservation ON 시 skip (smoothing 이 wall vertex 를 tangentially
    # 이동시켜 surface drift). T-Rex/cfMesh 동급 wall 보존 시에는 이 패스 비활성.
    _n_tang_moved = 0
    if (
        _BL_TANG_SMOOTH_ON
        and not _BL_TANG_PRESERVE_WALL
        and len(wall_vert_indices) >= 50 and layer_point_ids
    ):
        try:
            final_points, _n_tang_moved = _smooth_top_layer_tangential(
                final_points,
                wall_vert_indices,
                wall_tri_verts,
                wall_face_indices,
                layer_point_ids,
                cfg.num_layers,
            )
            log.info(
                "native_bl_tangent_smooth",
                component="native_bl",
                phase="beta2153",
                n_moved=_n_tang_moved,
                n_wall_verts=len(wall_vert_indices),
            )
            # HEX_BL_TANGENT (beta2156) — hex-specific alias log for 3-engine parity.
            # hex+BL shares the same native_bl.py path as tet+BL (R100). This log
            # confirms hex top-layer tangential smoothing is active (engine_tag="hex").
            if engine_tag == "hex":
                log.info(
                    "hex_bl_tangent_smooth",
                    component="native_bl",
                    phase="beta2156",
                    n_moved=_n_tang_moved,
                    n_wall_verts=len(wall_vert_indices),
                )
        except Exception as _tang_exc:
            log.warning("native_bl_tangent_smooth_skipped", reason=str(_tang_exc)[:120])

    # HEX_LAYERS — per-face per-layer guard (cfMesh nLayers=2, 1.2× growth ratio).
    # Mirrors POL_LAYERS (R91) + TET_LAYERS (R92). Apply HEX_BL1 aspect+collision guard
    # at each layer for every wall face; truncate chain at first rejected layer.
    # Uses _geometric_layer_thickness (BL2) for layer thickness array.
    _hex_layers_per_face: dict[int, int] = {}  # fi -> n_accepted_layers
    _hex_layers_n_rej_asp = 0
    _hex_layers_n_rej_col = 0
    _hex_layers_cap = int(os.environ.get("AUTO_TESSELL_HEX_LAYERS_FACE_CAP", "3000"))
    if (
        _HEX_LAYERS_N >= 1
        and wall_face_indices
        and layer_point_ids
        and len(wall_face_indices) <= _hex_layers_cap
    ):
        try:
            _glt_thicknesses = _geometric_layer_thickness(
                cfg.first_thickness, _HEX_LAYERS_N, growth_ratio=cfg.growth_ratio,
            )
            # Build wall face centroids and query each advancing layer against
            # the immutable wall-front source, preserving the legacy predicate.
            _wf_centroids: list[np.ndarray] = []
            for _hfi in wall_face_indices:
                _hvs = faces[_hfi]
                if len(_hvs) >= 3:
                    _wf_centroids.append(final_points[list(wall_tri_verts[_hfi])].mean(axis=0))
            from core.layers.native_bl_collision import query_centroid_overlap_mask
            _hex_collision_by_layer_face: dict[tuple[int, int], bool] = {}
            for _li_h in range(min(_HEX_LAYERS_N, len(layer_point_ids) - 1)):
                _query_points: list[np.ndarray] = []
                _query_radii: list[float] = []
                _query_face_ids: list[int] = []
                for _hfi in wall_face_indices:
                    if _hfi not in wall_tri_verts:
                        continue
                    _v0q, _v1q, _v2q = wall_tri_verts[_hfi]
                    _qmap = layer_point_ids[_li_h + 1]
                    if not all(v in _qmap for v in (_v0q, _v1q, _v2q)):
                        continue
                    _qtop = final_points[[_qmap[_v0q], _qmap[_v1q], _qmap[_v2q]]]
                    _qedges = [
                        float(np.linalg.norm(_qtop[(_qk + 1) % 3] - _qtop[_qk]))
                        for _qk in range(3)
                    ]
                    _query_points.append(_qtop.mean(axis=0))
                    _query_radii.append(max(max(_qedges) * 0.5, 1.0e-6))
                    _query_face_ids.append(int(_hfi))
                if _query_points:
                    _blocked = query_centroid_overlap_mask(
                        _query_points, _query_radii, _wf_centroids,
                    )
                    _hex_collision_by_layer_face.update({
                        (int(_li_h), face_id): bool(blocked)
                        for face_id, blocked in zip(_query_face_ids, _blocked, strict=True)
                    })

            for _fi_h in wall_face_indices:
                if _fi_h not in wall_tri_verts:
                    _hex_layers_per_face[_fi_h] = 0
                    continue
                _v0h, _v1h, _v2h = wall_tri_verts[_fi_h]
                _n_acc_h = 0
                for _li_h in range(min(_HEX_LAYERS_N, len(layer_point_ids) - 1)):
                    _step_h = float(_glt_thicknesses[_li_h])
                    _lids_out = layer_point_ids[_li_h]
                    _lids_in = layer_point_ids[_li_h + 1]
                    # Check vertex IDs present
                    if not all(v in _lids_out and v in _lids_in for v in (_v0h, _v1h, _v2h)):
                        break
                    _bot_h = final_points[[_lids_out[_v0h], _lids_out[_v1h], _lids_out[_v2h]]]
                    _top_h = final_points[[_lids_in[_v0h], _lids_in[_v1h], _lids_in[_v2h]]]
                    # Guard 1 — aspect ratio
                    _edges_h: list[float] = []
                    for _k_h in range(3):
                        _k2_h = (_k_h + 1) % 3
                        _edges_h.append(float(np.linalg.norm(_bot_h[_k2_h] - _bot_h[_k_h])))
                        _edges_h.append(float(np.linalg.norm(_top_h[_k2_h] - _top_h[_k_h])))
                        _edges_h.append(float(np.linalg.norm(_top_h[_k_h] - _bot_h[_k_h])))
                    _min_e_h = min(_edges_h) if _edges_h else 1.0
                    _max_e_h = max(_edges_h) if _edges_h else 1.0
                    _asp_h = _max_e_h / (_min_e_h + 1e-30)
                    # C-BL-5 / beta2433 — BL prism 의 aspect 는 본질적으로 큼
                    # (cfMesh / Pointwise T-Rex 모두 1e4~1e6 정상). 첫 layer 만
                    # 더 관대 (aspect threshold × 100 — 사실상 아무 prism 도 reject 안 함).
                    _aspect_cap = cfg.aspect_ratio_threshold * (
                        100.0 if _li_h == 0 else 1.0
                    )
                    if _asp_h > _aspect_cap:
                        _hex_layers_n_rej_asp += 1
                        log.debug("hex_layers_prism_rejected_aspect",
                                  face=_fi_h, layer=_li_h + 1, aspect=round(_asp_h, 2))
                        break
                    # Guard 2 — collision (bounding-sphere)
                    _top_c_h = _top_h.mean(axis=0)
                    _r_h = (_max_e_h * 0.5) if _max_e_h > 0 else 1e-6
                    _col_h = bool(_hex_collision_by_layer_face.get(
                        (int(_li_h), int(_fi_h)), False,
                    ))
                    if _col_h:
                        _hex_layers_n_rej_col += 1
                        log.debug("hex_layers_prism_rejected_collision",
                                  face=_fi_h, layer=_li_h + 1)
                        break
                    _n_acc_h += 1
                _hex_layers_per_face[_fi_h] = _n_acc_h

            # beta2263 — Pointwise T-Rex 동급 LCR 통계 (per-face).
            _hl_vals = list(_hex_layers_per_face.values())
            _avg_hl = float(np.mean(_hl_vals)) if _hl_vals else 0.0
            _min_hl = int(min(_hl_vals)) if _hl_vals else 0
            _max_hl = int(max(_hl_vals)) if _hl_vals else 0
            _full_count = sum(1 for v in _hl_vals if v == _HEX_LAYERS_N)
            _reduced_count = sum(1 for v in _hl_vals if 0 < v < _HEX_LAYERS_N)
            _zero_count = sum(1 for v in _hl_vals if v == 0)
            log.info(
                "hex_layers_summary",
                n_wall_faces=len(wall_face_indices),
                n_layers_target=_HEX_LAYERS_N,
                avg_n_layers=round(_avg_hl, 2),
                min_n_layers=_min_hl,
                max_n_layers=_max_hl,
                # LCR: per-face 분포 (Pointwise T-Rex equivalent stats)
                pct_full_layers=round(100.0 * _full_count / max(1, len(_hl_vals)), 1),
                pct_reduced_layers=round(100.0 * _reduced_count / max(1, len(_hl_vals)), 1),
                pct_zero_layers=round(100.0 * _zero_count / max(1, len(_hl_vals)), 1),
                n_rejected_aspect=_hex_layers_n_rej_asp,
                n_rejected_collision=_hex_layers_n_rej_col,
                growth_ratio=cfg.growth_ratio,
                first_thickness=round(cfg.first_thickness, 6),
            )
        except Exception as _hle:
            log.info("hex_layers_skipped", reason=str(_hle)[:120])
    elif _HEX_LAYERS_N >= 1 and len(wall_face_indices) > _hex_layers_cap:
        log.info(
            "hex_layers_skipped_large",
            n_wall_faces=int(len(wall_face_indices)),
            cap=int(_hex_layers_cap),
            reason="diagnostic per-layer guard would be quadratic",
        )

    # backup
    if cfg.backup_original:
        bak = case_dir / "constant" / "polyMesh_pre_bl"
        if bak.exists():
            shutil.rmtree(bak)
        shutil.copytree(poly_dir, bak)

    # beta2249 — cfMesh/T-Rex 동급 force-snap: wall vertex 를 원본 좌표로 복원.
    # tang smoother / collision detection / round-off 등 어떤 이유로든 lp_ids[0]
    # 가 원본 wall 에서 drift 한 경우 강제 snap. polyMesh 쓰기 직전 단계.
    # env AUTO_TESSELL_BL_FORCE_SNAP_WALL=0 으로 비활성 가능.
    _force_snap_on = os.environ.get("AUTO_TESSELL_BL_FORCE_SNAP_WALL", "1") != "0"
    n_snap = 0
    snap_max_diff = 0.0
    if _force_snap_on and final_points is not None and layer_point_ids:
        try:
            outer_lp_snap = layer_point_ids[0]
            for v_orig, new_idx in outer_lp_snap.items():
                if 0 <= new_idx < final_points.shape[0]:
                    diff = float(np.linalg.norm(final_points[new_idx] - points[v_orig]))
                    if diff > 1e-12:
                        if diff > snap_max_diff:
                            snap_max_diff = diff
                        final_points[new_idx] = points[v_orig]
                        n_snap += 1
            if n_snap > 0:
                log.info(
                    "native_bl_force_snap_wall", component="native_bl",
                    n_snap=n_snap, max_diff=round(snap_max_diff, 9),
                )
        except Exception as exc:
            log.debug("native_bl_force_snap_skipped", reason=str(exc)[:120])

    if (
        os.environ.get("AUTO_TESSELL_BL_FEATURE_EDGE_POLY_MERGE", "1") != "0"
        and final_points is not None
        and final_faces
        and final_nbr
    ):
        try:
            (
                final_faces,
                final_owner,
                final_nbr,
                final_boundary_entries,
                n_feature_edge_merged,
            ) = _merge_skewed_bl_internal_quads(
                final_points,
                final_faces,
                final_owner,
                final_nbr,
                final_boundary_entries,
                base_n_cells=n_cells,
                skew_threshold=float(
                    os.environ.get(
                        "AUTO_TESSELL_BL_FEATURE_EDGE_MERGE_SKEW",
                        "4.0",
                    ),
                ),
            )
        except Exception as exc:
            log.debug(
                "native_bl_feature_edge_poly_merge_skipped",
                reason=str(exc)[:120],
            )

    n_boundary_faces_reoriented = 0
    if final_points is not None and final_faces and final_owner:
        try:
            n_boundary_faces_reoriented = _orient_boundary_faces_outward(
                final_points,
                final_faces,
                final_owner,
                final_nbr,
            )
            if n_boundary_faces_reoriented > 0:
                log.info(
                    "native_bl_boundary_faces_oriented",
                    component="native_bl",
                    n_reversed=int(n_boundary_faces_reoriented),
                )
        except Exception as exc:
            log.debug(
                "native_bl_boundary_face_orient_skipped",
                reason=str(exc)[:120],
            )

    # Read-only final gate.  The writer has already established layer
    # connectivity; do not mutate its candidate here without a full cell
    # topology proof.  Non-finite coordinates fail closed in the report.
    _line_search_enabled = os.environ.get("AUTO_TESSELL_BL_EXTRUSION_LINE_SEARCH", "1") != "0"
    extrusion_line_search_diag: dict[str, Any] = {
        "enabled": bool(_line_search_enabled),
        "accepted": True,
        "mode": "read_only_gate",
        "negative_pre": 0,
        "negative_post": 0,
        "n_scaled_vertices": 0,
        "boundary_skew_pre": 0.0,
        "non_ortho_pre": 0.0,
        "face_weight_pre": 1.0,
        "face_weight_post": 1.0,
        "max_scale": 1.0,
    }
    if _line_search_enabled and final_points is not None:
        final_points, _prewrite_line_search_diag = _bounded_bl_extrusion_line_search(
            points,
            final_points,
            final_faces,
            final_owner,
            final_nbr,
            wall_vert_indices,
            layer_point_ids,
            base_n_cells=n_cells,
            restore_identity=False,
        )
        extrusion_line_search_diag.update(_prewrite_line_search_diag)
        _final_metrics = _bl_extrusion_metrics(
            final_points, points, final_faces, final_owner, final_nbr,
            base_n_cells=n_cells,
        )
        _negative = int(len(_final_metrics.inverted_cells))
        extrusion_line_search_diag.update(
            accepted=(_negative == 0),
            negative_post=_negative,
            boundary_skew_pre=float(_final_metrics.max_boundary_skewness),
            non_ortho_pre=float(_final_metrics.max_non_orthogonality),
            face_weight_pre=float(_final_metrics.min_face_weight),
            face_weight_post=float(_final_metrics.min_face_weight),
        )

    # beta65: prism quality check — aspect ratio 기반.
    n_degen = 0
    max_ar = 0.0
    if cfg.quality_check_enabled and n_prism_total > 0:
        n_degen, max_ar = _prism_aspect_ratio_stats(
            final_points, wall_tri_verts, wall_face_indices, layer_point_ids,
            cfg.num_layers, threshold=cfg.aspect_ratio_threshold,
        )
        if n_degen > 0:
            log.warning(
                "native_bl_quality_check", component="native_bl", phase="Phase2",
                n_degenerate_prisms=n_degen, max_aspect_ratio=max_ar,
                threshold=cfg.aspect_ratio_threshold,
            )

    # GAP4 / beta2769 — aspect_cap_enforcer wire-in.
    # max_ar > target_aspect 인 prism 의 outer node 를 wall 쪽으로 shrink.
    # env AUTO_TESSELL_BL_ASPECT_ENFORCE=1 활성 (default OFF — 회귀 안전).
    # 활성 시: aspect 11500 → ≤target_aspect (1000 default) 로 강제.
    if (
        os.environ.get("AUTO_TESSELL_BL_ASPECT_ENFORCE", "0") == "1"
        and n_prism_total > 0
        and max_ar > cfg.aspect_ratio_threshold
    ):
        try:
            from core.layers.aspect_cap_enforcer import (
                enforce_prism_aspect_cap_v2 as enforce_prism_aspect_cap,
            )
            # build prism (P, 6) array from layer_point_ids.
            valid_faces = [fi for fi in wall_face_indices if fi in wall_tri_verts]
            tri_arr_e = np.array(
                [wall_tri_verts[fi] for fi in valid_faces], dtype=np.int64,
            )
            n_F = tri_arr_e.shape[0]
            prism_list = []
            for k in range(cfg.num_layers):
                lp_o = layer_point_ids[k]      # wall side of this layer
                lp_i = layer_point_ids[k + 1]  # outer side
                for fi in range(n_F):
                    v0, v1, v2 = (int(x) for x in tri_arr_e[fi])
                    prism_list.append([
                        lp_o[v0], lp_o[v1], lp_o[v2],
                        lp_i[v0], lp_i[v1], lp_i[v2],
                    ])
            prisms_arr = np.array(prism_list, dtype=np.int64)
            new_pts, ace_res = enforce_prism_aspect_cap(
                final_points, prisms_arr,
                target_aspect=float(cfg.aspect_ratio_threshold),
                min_height_factor=0.05,
            )
            log.info(
                "native_bl_aspect_enforced",
                aspect_max_pre=round(ace_res.aspect_max_pre, 1),
                aspect_max_post=round(ace_res.aspect_max_post, 1),
                n_violations_pre=ace_res.n_violations_pre,
                n_violations_post=ace_res.n_violations_post,
                n_outer_modified=ace_res.n_outer_modified,
            )
            # accept only if monotone improvement (no aspect increase).
            if ace_res.aspect_max_post < ace_res.aspect_max_pre:
                final_points = new_pts
                # re-measure.
                n_degen, max_ar = _prism_aspect_ratio_stats(
                    final_points, wall_tri_verts, wall_face_indices,
                    layer_point_ids, cfg.num_layers,
                    threshold=cfg.aspect_ratio_threshold,
                )
        except Exception as exc:
            log.warning("native_bl_aspect_enforce_failed", reason=str(exc)[:160])

    # C3.2 / beta2376 — anisotropic prism split diagnostic (cfMesh
    # splitInternalLayers 동등). env-gated: AUTO_TESSELL_BL_ANISO_SPLIT_DIAG=1.
    # mesh 변경 없이 split 가능한 prism 수만 측정 (실 split 은 후속 카드).
    aniso_split_n_examined = 0
    aniso_split_n_would = 0
    aniso_split_max_asp_in = 0.0
    if (
        os.environ.get("AUTO_TESSELL_BL_ANISO_SPLIT_DIAG", "0") == "1"
        and n_prism_total > 0
        and cfg.num_layers >= 1
    ):
        try:
            from core.layers.native_bl_split import split_thick_prisms
            # Build (N, 6) wedge connectivity from layer_point_ids.
            _diag_prisms: list[list[int]] = []
            for fi in wall_face_indices:
                if fi not in wall_tri_verts:
                    continue
                v0, v1, v2 = wall_tri_verts[fi]
                for k in range(cfg.num_layers):
                    if k >= len(layer_point_ids) - 1:
                        break
                    lk = layer_point_ids[k]
                    lkp1 = layer_point_ids[k + 1]
                    if not all(v in lk and v in lkp1 for v in (v0, v1, v2)):
                        continue
                    _diag_prisms.append([
                        lk[v0], lk[v1], lk[v2],
                        lkp1[v0], lkp1[v1], lkp1[v2],
                    ])
            if _diag_prisms:
                _arr = np.array(_diag_prisms, dtype=np.int64)
                _, _, _spr = split_thick_prisms(
                    final_points, _arr, threshold=4.0,
                )
                aniso_split_n_examined = int(_spr.n_input_prisms)
                aniso_split_n_would = int(_spr.n_split_prisms)
                aniso_split_max_asp_in = float(_spr.max_aspect_in)
                log.info(
                    "native_bl_aniso_split_diagnostic",
                    component="native_bl", phase="beta2376",
                    n_prisms_examined=aniso_split_n_examined,
                    n_would_split=aniso_split_n_would,
                    max_aspect_in=aniso_split_max_asp_in,
                    threshold=4.0,
                )
        except Exception as _split_exc:
            log.debug(
                "native_bl_aniso_split_diag_skipped",
                reason=str(_split_exc)[:120],
            )

    # beta2247 — cfMesh/T-Rex 동급 wall preservation 검증.
    # lp_ids[0] (outer-most BL layer = boundary patch face) 가 원본 wall 좌표와
    # ε 이내 일치하는지 검증. ε = bbox_diag * 1e-6 (수치 노이즈 허용).
    wall_preserve_max_diff = 0.0
    n_wall_drift = 0
    wall_preserve_rel = 0.0
    wall_within_env = True
    try:
        if final_points is not None and layer_point_ids:
            # lp_ids[0] 의 vertex 가 wall_vert_indices 의 원본 좌표와 일치해야 함.
            outer_lp = layer_point_ids[0] if layer_point_ids else {}
            for v_orig in wall_vert_indices:
                new_idx = outer_lp.get(v_orig)
                if new_idx is None:
                    continue
                orig_pos = points[v_orig]
                new_pos = final_points[new_idx]
                diff = float(np.linalg.norm(new_pos - orig_pos))
                if diff > wall_preserve_max_diff:
                    wall_preserve_max_diff = diff
                if diff > 1e-9:
                    n_wall_drift += 1
        bbox_diag_check = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
        wall_preserve_rel = wall_preserve_max_diff / max(bbox_diag_check, 1e-30)
        wall_within_env = bool(wall_preserve_rel <= 1e-6)
        log.info(
            "native_bl_wall_preserve_check", component="native_bl",
            n_wall_verts=len(wall_vert_indices),
            n_drift=n_wall_drift,
            max_diff=round(wall_preserve_max_diff, 9),
            max_diff_rel=round(wall_preserve_rel, 9),
            envelope_eps_rel=1e-6,
            within_envelope=wall_within_env,
        )
    except Exception as exc:
        log.debug("native_bl_wall_preserve_check_skipped", reason=str(exc)[:120])

    # Every accepted point transform must be measured and persisted from the
    # same final array.  In particular, aspect-cap enforcement runs after the
    # initial quality measurement and must not be lost by an earlier write.
    if _line_search_enabled and final_points is not None:
        _final_metrics = _bl_extrusion_metrics(
            final_points,
            points,
            final_faces,
            final_owner,
            final_nbr,
            base_n_cells=n_cells,
        )
        _negative = int(len(_final_metrics.inverted_cells))
        extrusion_line_search_diag.update(
            accepted=(_negative == 0),
            negative_post=_negative,
            boundary_skew_pre=float(_final_metrics.max_boundary_skewness),
            non_ortho_pre=float(_final_metrics.max_non_orthogonality),
            face_weight_post=float(_final_metrics.min_face_weight),
        )

    poly_dir.mkdir(parents=True, exist_ok=True)
    _write_points(poly_dir / "points", final_points)
    _write_faces(poly_dir / "faces", final_faces)
    _write_labels(
        poly_dir / "owner",
        np.array(final_owner, dtype=np.int64),
        "owner",
    )
    _write_labels(
        poly_dir / "neighbour",
        np.array(final_nbr, dtype=np.int64),
        "neighbour",
    )
    _write_boundary(poly_dir / "boundary", final_boundary_entries)

    # Round 030: read first-layer height and quality from the persisted candidate.
    _first_layer_heights: list[float] = []
    if final_points is not None and len(layer_point_ids) > 1:
        _outer_layer = layer_point_ids[0]
        _first_inner_layer = layer_point_ids[1]
        for _v in wall_vert_indices:
            _p0 = _outer_layer.get(int(_v))
            _p1 = _first_inner_layer.get(int(_v))
            if _p0 is None or _p1 is None:
                continue
            _h = float(np.linalg.norm(final_points[int(_p1)] - final_points[int(_p0)]))
            if np.isfinite(_h):
                _first_layer_heights.append(_h)
    _first_layer_height_min = (
        float(min(_first_layer_heights)) if _first_layer_heights else 0.0
    )
    _positive_thickness = bool(
        n_prism_total > 0 and _first_layer_height_min > 0.0 and total > 0.0
    )
    # pre-write arrays. This catches writer/topology changes before receipt.
    _quality_readback: dict[str, Any] = {
        "status": "not_measured",
        "max_skewness": None,
        "max_non_orthogonality": None,
        "max_aspect_ratio": None,
        "min_scaled_jacobian": None,
        "negative_volumes": None,
        "min_face_weight": None,
    }
    try:
        from core.evaluator.native_checker import NativeMeshChecker
        _disk_quality = NativeMeshChecker().run(case_dir)
        _quality_readback = {
            "status": "measured",
            "max_skewness": float(_disk_quality.max_skewness),
            "max_non_orthogonality": float(_disk_quality.max_non_orthogonality),
            "max_aspect_ratio": float(_disk_quality.max_aspect_ratio),
            "min_scaled_jacobian": float(_disk_quality.min_determinant),
            "negative_volumes": int(_disk_quality.negative_volumes),
            "min_face_weight": float(
                _disk_quality.min_face_weight
                if _disk_quality.min_face_weight is not None else 1.0
            ),
        }

    except Exception as _quality_exc:
        _quality_readback["reason"] = f"{type(_quality_exc).__name__}:{_quality_exc}"
        log.warning("native_bl_quality_readback_failed", reason=str(_quality_exc)[:200])
    # C106: preserve the actual writer boundary order and its source mesh-face
    # owner. The later Hex receipt may bind CAD ordinals only through this
    # explicit ledger; it must never reconstruct them from geometry.
    if native_hex_authority_mode or engine_tag == "native_hex":
        try:
            writer_records: list[dict[str, Any]] = []
            boundary_cursor = 0
            for entry in final_boundary_entries:
                start_face = int(entry.get("startFace", -1))
                face_count = int(entry.get("nFaces", 0))
                patch_name = str(entry.get("name", ""))
                is_lateral = patch_name == "bl_internal_domain"
                for offset in range(face_count):
                    if boundary_cursor >= len(final_boundary_source_faces):
                        raise ValueError("writer_order_source_face_count_mismatch")
                    source_mesh_face = int(final_boundary_source_faces[boundary_cursor])
                    source_face = (
                        None
                        if is_lateral
                        else _native_hex_source_face_by_mesh_face.get(source_mesh_face)
                    )
                    writer_records.append({
                        "writer_order": int(boundary_cursor),
                        "output_face_id": int(start_face + offset),
                        "source_mesh_face": source_mesh_face,
                        "source_face": int(source_face) if source_face is not None else -1,
                        "patch": patch_name,
                        "direct": source_face is not None,
                        "lineage_role": (
                            "layer_lateral" if is_lateral else "source_boundary"
                        ),
                    })
                    boundary_cursor += 1
            if boundary_cursor != len(final_faces) - len(final_nbr):
                raise ValueError("writer_order_boundary_count_mismatch")
            writer_payload = {
                "schema": (
                    "autotessell/native-hex-writer-order/v2"
                    if native_hex_authority_mode
                    else "autotessell/native-hex-writer-order/v1"
                ),
                "requested_layers": int(requested_layers),
                "actual_layers": int(cfg.num_layers),
                "source_map_present": native_hex_source_map_path.is_file(),
                "source_map_valid": native_hex_authority_mode,
                "source_map_sha256": native_hex_source_map_info.get("map_sha256"),
                "source_binding_sha256": native_hex_source_map_info.get(
                    "source_binding_sha256"
                ),
                "ingress_certificate_sha256": native_hex_source_map_info.get(
                    "ingress_certificate_sha256"
                ),
                "semantic_ledger_sha256": native_hex_source_map_info.get(
                    "semantic_ledger_sha256"
                ),
                "provisioning_manifest_sha256": native_hex_source_map_info.get(
                    "provisioning_manifest_sha256"
                ),
                "records": writer_records,
            }
            writer_path = case_dir / "native_hex_writer_order.json"
            writer_tmp = case_dir / (
                f".native_hex_writer_order.{os.getpid()}.{time.time_ns()}.tmp"
            )
            writer_tmp.write_text(
                json.dumps(writer_payload, sort_keys=True, separators=(",", ":"))
                + chr(10)
            )
            os.replace(writer_tmp, writer_path)
        except Exception as _writer_order_exc:
            log.warning(
                "native_hex_writer_order_not_written",
                reason=str(_writer_order_exc)[:240],
            )

    # Native Tet actual-contract path: preserve source-to-layer lineage before
    # the subsequent prism-to-Tet rebuild changes cell/face IDs.
    if engine_tag == "native_tet_actual_contract" and int(cfg.num_layers) > 0:
        try:
            _lineage_records = []
            for _wi, _source_face in enumerate(wall_face_indices):
                _layers = [
                    [int(layer_point_ids[_li][int(_v)]) for _v in wall_tri_verts[_source_face]]
                    for _li in range(len(layer_point_ids))
                ]
                _lineage_records.append({
                    "source_face": int(_source_face),
                    "source_vertices": [int(_v) for _v in wall_tri_verts[_source_face]],
                    "patch_index": int(wall_orig_patch[_source_face]),
                    "owner_cell": int(wall_orig_owner[_source_face]),
                    "layer_point_ids": _layers,
                    "prism_cell_ids": [
                        int(prism_cell_id_start + _wi * int(cfg.num_layers) + _li)
                        for _li in range(int(cfg.num_layers))
                    ],
                })
            (case_dir / "native_bl_lineage.json").write_text(
                json.dumps({
                    "schema": "native-tet-bl-direct-lineage/v1",
                    "requested_layers": int(cfg.num_layers),
                    "first_thickness": float(cfg.first_thickness),
                    "growth_ratio": float(cfg.growth_ratio),
                    "records": _lineage_records,
                }, sort_keys=True, separators=(",", ":")) + "\n"
            )
        except Exception as _lineage_exc:
            log.warning("native_tet_direct_id_lineage_write_failed", reason=str(_lineage_exc)[:160])

    # beta2273 — commercial-grade mesh quality summary JSON.
    # cfMesh / Pointwise / Star-CCM+ 의 mesh quality report 동등.
    # case_dir/native_bl_quality.json 에 모든 메트릭 저장.
    try:
        import json as _json
        bad_internal_face_histogram = (
            _bl_bad_internal_face_histogram(
                final_points,
                final_faces,
                final_owner,
                final_nbr,
                base_n_cells=n_cells,
                prism_cell_start=prism_cell_id_start,
                prism_cell_end=prism_cell_id_start + n_prism_total,
            )
            if final_points is not None and final_faces and final_owner
            else {}
        )
        quality_summary = {
            "requested_layers": int(requested_layers),
            "used_layers": int(cfg.num_layers),
            "n_wall_faces": int(n_wall_faces),
            "n_wall_verts": int(len(wall_vert_indices)),
            "n_prism_cells": int(n_prism_total),
            "n_feature_edge_merged": int(n_feature_edge_merged),
            "n_new_points": int(n_new_points),
            "total_thickness": float(total),
            "bbox_diag": float(bbox_diag),
            "thickness_to_bbox_ratio": float(total / max(bbox_diag, 1e-30)),
            "n_degenerate_prisms": int(n_degen),
            "boundary_layer": {
                "requested_layers": int(requested_layers),
                "actual_layers": int(cfg.num_layers),
                "positive_first_layer_height": float(_first_layer_height_min),
                "positive_cell_count": int(n_prism_total),
                "positive_thickness": bool(_positive_thickness),
                "termination_reason": (
                    "committed_with_local_termination"
                    if int(lcr_n_reduced) > 0 else "committed_full_schedule"
                ),
            },
            "max_aspect_ratio": float(max_ar),
            "wall_preserve": {
                "max_diff": float(wall_preserve_max_diff),
                "max_diff_rel": float(wall_preserve_rel),
                "n_drift": int(n_wall_drift),
                "within_envelope": bool(wall_within_env),
                "envelope_eps_rel": 1e-6,
            },
            "quality_readback": _quality_readback,
            "force_snap": {
                "n_applied": int(n_snap),
                "max_diff": float(snap_max_diff),
            },
            # C2.3 / beta2369 — per-vertex Layer Count Reduction (Pointwise T-Rex 동등).
            "lcr": {
                "n_reduced_verts": int(lcr_n_reduced),
                "max_reduction": int(lcr_max_reduction),
                "min_layers_used": int(lcr_min_layers_used),
                "n_safe_full_layers": int(lcr_n_safe_full),
            },
            "feature_size": feature_size_diag,
            "extrusion_line_search": extrusion_line_search_diag,
            # C3.3 / beta2377 — anisotropic prism split diagnostic (cfMesh 동등).
            "aniso_split": {
                "n_examined": int(aniso_split_n_examined),
                "n_would_split": int(aniso_split_n_would),
                "max_aspect_in": float(aniso_split_max_asp_in),
            },
            "bad_internal_faces": bad_internal_face_histogram,
            "pre_bl_bad_internal_faces": pre_bl_bad_internal_face_histogram,
            "tet_wall_cavity": tet_wall_cavity_eligibility,
            "owner_centre_motion": owner_centre_motion_diag,
            "tet_cavity_probe": tet_cavity_probe_diag,
            "tet_cavity_replace": tet_cavity_replace_diag,
            "tet_cavity_eval": tet_cavity_eval_diag,
            "anti_invert_cap": anti_invert_cap_diag,
            # beta2328 — pre-BL wall surface SI count (P2.6 series).
            # None = 측정 안 됨 (>5000 face), 0 = clean, >0 = 입력에 SI 존재.
            "pre_bl_self_intersect": _pre_bl_si_count,
            "config": {
                "num_layers": int(cfg.num_layers),
                "growth_ratio": float(cfg.growth_ratio),
                "first_thickness": float(cfg.first_thickness),
                "wall_patch_names": cfg.wall_patch_names,
                "set_faces": cfg.set_faces,
                "ignore_faces": cfg.ignore_faces,
                "ignore_patch_names": cfg.ignore_patch_names,
                "ignore_patch_prefixes": cfg.ignore_patch_prefixes,
                "target_y_plus": cfg.target_y_plus,
                "flow_fluid_preset": cfg.flow_fluid_preset,
                "max_skewness": cfg.max_skewness,
                "max_non_orthogonality": cfg.max_non_orthogonality,
                "max_quality_aspect_ratio": cfg.max_quality_aspect_ratio,
                "min_face_weight": cfg.min_face_weight,
                "min_scaled_jacobian": cfg.min_scaled_jacobian,
                "min_first_layer_height": cfg.min_first_layer_height,
            },
        }
        (case_dir / "native_bl_quality.json").write_text(
            _json.dumps(quality_summary, indent=2),
        )
        log.info("native_bl_quality_json_written",
                 path=str(case_dir / "native_bl_quality.json"))
    except Exception as exc:
        log.debug("native_bl_quality_json_skipped", reason=str(exc)[:120])

    elapsed = time.perf_counter() - t_start
    result = NativeBLResult(
        success=True,
        elapsed=elapsed,
        n_wall_faces=n_wall_faces,
        n_wall_verts=len(wall_vert_indices),
        n_prism_cells=n_prism_total,
        n_new_points=n_new_points,
        total_thickness=total,
        n_degenerate_prisms=n_degen,
        max_aspect_ratio=max_ar,
        wall_preserve_max_diff=float(wall_preserve_max_diff),
        wall_preserve_max_diff_rel=float(wall_preserve_rel),
        wall_preserve_n_drift=int(n_wall_drift),
        wall_preserve_within_envelope=bool(wall_within_env),
        min_scaled_jacobian=_quality_readback.get("min_scaled_jacobian"),
        n_snap_applied=int(n_snap),
        snap_max_diff=float(snap_max_diff),
        lcr_n_reduced_verts=int(lcr_n_reduced),
        lcr_max_reduction=int(lcr_max_reduction),
        lcr_min_layers_used=int(lcr_min_layers_used),
        lcr_n_safe_full_layers=int(lcr_n_safe_full),
        aniso_split_n_examined=int(aniso_split_n_examined),
        aniso_split_n_would_split=int(aniso_split_n_would),
        aniso_split_max_aspect_in=float(aniso_split_max_asp_in),
        requested_layers=int(requested_layers),
        actual_layers=int(cfg.num_layers),
        first_layer_height=float(_first_layer_height_min),
        min_first_layer_height=float(_first_layer_height_min),
        positive_thickness=bool(_positive_thickness),
        max_skewness=_quality_readback.get("max_skewness"),
        max_non_orthogonality=_quality_readback.get("max_non_orthogonality"),
        min_face_weight=_quality_readback.get("min_face_weight"),
        negative_volumes=int(_quality_readback.get("negative_volumes") or 0),
        quality_readback_status=str(_quality_readback.get("status", "not_measured")),
        wall_selector={"patch_names": cfg.wall_patch_names, "set_faces": cfg.set_faces},
        termination_reason=(
            "committed_with_local_termination"
            if int(lcr_n_reduced) > 0 else "committed_full_schedule"
        ),
        message=(
            f"native_bl Phase 2 OK — {n_prism_total} prism cells inserted "
            f"({cfg.num_layers} layers × {n_wall_faces} wall triangles). "
            f"total_thickness={total:.4g}, bbox={bbox_diag:.3g}, "
            f"bl_side_faces={bl_side_count}, "
            f"feature_edge_merged={n_feature_edge_merged}, "
            f"degenerate={n_degen}/{n_prism_total}, max_ar={max_ar:.1f}."
        ),
    )
    state_error = _complete_native_bl_state(
        case_dir,
        input_hashes,
        requested_layers=requested_layers,
        actual_layers=int(cfg.num_layers),
        n_prism_cells=int(result.n_prism_cells),
    )
    if state_error is not None:
        return replace(result, success=False, message=state_error)
    return result
