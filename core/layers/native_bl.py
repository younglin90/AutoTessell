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

import os

import shutil
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.utils.logging import get_logger
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

log = get_logger(__name__)

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
        if self.first_thickness <= 0:
            raise ValueError(
                f"BLConfig.first_thickness 는 양수여야 합니다 "
                f"(got {self.first_thickness}). bbox * 0.001 권장."
            )
        if self.num_layers < 1:
            raise ValueError(
                f"BLConfig.num_layers >= 1 필수 (got {self.num_layers})."
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

        # Accumulate per-vertex weighted normals: sum(n * area) for each vertex.
        contrib = n_arr * area_vec[:, None]  # (F, 3)
        n_pts = points.shape[0]
        accum = np.zeros((n_pts, 3), dtype=np.float64)
        # Add contribution to all 3 vertices of each face.
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
import os as _os
_BL_TANG_SMOOTH_ON: bool = _os.environ.get("AUTO_TESSELL_BL_TANG_OFF", "0") != "1"
# beta2248 — cfMesh/T-Rex 동급 wall preservation 강화. tangent smoothing 이
# lp_ids[0] (=wall) vertex 를 tangential 로 이동시켜 surface drift 유발 →
# default OFF. fluid 시뮬에서 wall 위치는 정확해야 하므로 이 trade-off 가 옳음.
# env AUTO_TESSELL_BL_TANG_PRESERVE_WALL=0 으로 이전 동작 (smoothing 활성) 가능.
_BL_TANG_PRESERVE_WALL: bool = _os.environ.get(
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
            next_pos = fp[all_layer_idx[layer_i + 1]]
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
        max_tris: wall triangle 수가 이 값을 초과하면 collision check 를 skip
            (메모리/시간 폭증 방지). 기본 20000 → R=T=2만 기준 메모리 ~9.6 GB.

    Returns:
        dict[vertex_id, distance]. 충돌 없거나 skip 시 빈 dict.

    beta70 hotfix: exclude mask 를 vectorized 로 구성 + max_tris cap.
    """
    tri_indices = [fi for fi in wall_face_indices if len(faces[fi]) == 3]
    if not tri_indices or not wall_vert_indices:
        return {}
    T = len(tri_indices)
    R = len(wall_vert_indices)
    if T > max_tris:
        log.info(
            "native_bl_collision_skipped_large", component="native_bl", phase="Phase2",
            n_tris=T, cap=max_tris,
            hint="너무 큰 wall mesh → collision check 생략 (local cell-dist cap 사용)",
        )
        return {}

    # tri_verts: (T, 3, 3)
    tri_arr = np.array(tri_indices, dtype=np.int64)
    tri_face_ids = np.array(
        [[faces[fi][0], faces[fi][1], faces[fi][2]] for fi in tri_indices],
        dtype=np.int64,
    )  # (T, 3)
    tri_verts = points[tri_face_ids]  # (T, 3, 3)

    wall_v_arr = np.array(wall_vert_indices, dtype=np.int64)
    origins = points[wall_v_arr]                                       # (R, 3)
    dirs = np.array([-vnorm[v] for v in wall_vert_indices], dtype=np.float64)  # (R, 3)

    # cfMesh-style local front collision pruning: for BL safety we only need
    # intersections closer than the generated layer thickness.  A centroid KDTree
    # keeps the exact ray-triangle test but avoids the old all-rays × all-faces
    # matrix on large wall meshes.
    if max_search_distance is not None and np.isfinite(max_search_distance):
        search = float(max_search_distance)
        if search > 0.0 and R * T >= 1_000_000:
            try:
                from scipy.spatial import cKDTree  # noqa: PLC0415

                tri_centers = tri_verts.mean(axis=1)
                tri_radii = np.linalg.norm(
                    tri_verts - tri_centers[:, None, :], axis=2,
                ).max(axis=1)
                radius = search + float(tri_radii.max(initial=0.0))
                tree = cKDTree(tri_centers)
                candidate_lists = tree.query_ball_point(origins, r=radius)
                out: dict[int, float] = {}
                n_candidates = 0
                n_nonempty = 0
                for ri, cand in enumerate(candidate_lists):
                    if not cand:
                        continue
                    cand_arr = np.asarray(cand, dtype=np.int64)
                    n_candidates += int(cand_arr.size)
                    n_nonempty += 1
                    v = int(wall_v_arr[ri])
                    c_face_ids = tri_face_ids[cand_arr]
                    exclude = (
                        (c_face_ids[:, 0] == v)
                        | (c_face_ids[:, 1] == v)
                        | (c_face_ids[:, 2] == v)
                    )[None, :]
                    t_min = _ray_triangle_min_distance(
                        origins[ri:ri + 1],
                        dirs[ri:ri + 1],
                        tri_verts[cand_arr],
                        exclude,
                        chunk_size=1,
                    )[0]
                    if np.isfinite(t_min) and float(t_min) <= search:
                        out[v] = float(t_min)
                log.info(
                    "native_bl_collision_local_pruned",
                    component="native_bl", phase="Phase2",
                    n_rays=int(R), n_tris=int(T),
                    n_nonempty=int(n_nonempty),
                    avg_candidates=round(
                        float(n_candidates) / max(1, int(R)), 2,
                    ),
                    search_distance=round(search, 8),
                )
                return out
            except Exception as _local_exc:
                log.debug(
                    "native_bl_collision_local_prune_skipped",
                    reason=str(_local_exc)[:120],
                )

    # exclude: vertex v 가 tri 에 포함되면 True. broadcasting 으로 O(R+T).
    # (R, 1) == (1, T, 3) → (R, T, 3) — too big? No: R, T up to 2만 → R*T=4e8 bools = 400MB.
    # 대신 (R,1) 와 각 tri column 3 번 OR 로 메모리 3× 절약.
    wall_col = wall_v_arr[:, None]  # (R, 1)
    exclude = (
        (wall_col == tri_face_ids[None, :, 0])
        | (wall_col == tri_face_ids[None, :, 1])
        | (wall_col == tri_face_ids[None, :, 2])
    )  # (R, T)

    t_min = _ray_triangle_min_distance(origins, dirs, tri_verts, exclude)
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


def _write_points(path: Path, points: np.ndarray) -> None:
    """beta85: numpy savetxt → 대형 mesh 에서 10× 빠른 I/O."""
    import io  # noqa: PLC0415
    header = _FOAM_HEADER.format(cls="vectorField", obj="points")
    buf = io.StringIO()
    np.savetxt(buf, points, fmt="(%.9g %.9g %.9g)")
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
) -> tuple[list[int], set[int], dict[int, tuple[int, int]]]:
    """Wall patch 들의 face index 모음 + patch 매핑 반환.

    Returns:
        (wall_face_indices,
         wall_patch_set (idx of patch),
         face_to_patch: {fi: (patch_idx, local_offset)})
    """
    wall_face_indices: list[int] = []
    face_to_patch: dict[int, tuple[int, int]] = {}
    for pi, patch in enumerate(boundary):
        name = str(patch.get("name", ""))
        kind = str(patch.get("type", "")).lower()
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
            wall_face_indices.append(fi)
            face_to_patch[fi] = (pi, k)
    return wall_face_indices, {p[0] for p in face_to_patch.values()}, face_to_patch


def _cell_centres_from_faces(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
) -> np.ndarray:
    n_int = len(neighbour)
    fc = np.zeros((len(faces), 3), dtype=np.float64)
    for i, f in enumerate(faces):
        fc[i] = points[f].mean(axis=0)
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
    poly_dir = case_dir / "constant" / "polyMesh"
    if not (poly_dir / "faces").exists():
        return NativeBLResult(
            success=False, elapsed=time.perf_counter() - t_start,
            message=f"polyMesh 없음: {poly_dir}",
        )

    # 1) 읽기
    raw_points = parse_foam_points(poly_dir / "points")
    raw_faces = parse_foam_faces(poly_dir / "faces")
    owner_list = parse_foam_labels(poly_dir / "owner")
    neighbour_list = parse_foam_labels(poly_dir / "neighbour")
    boundary = parse_foam_boundary(poly_dir / "boundary")

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
        boundary, cfg.wall_patch_names,
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
    non_tri = [fi for fi in wall_face_indices if len(faces[fi]) != 3]
    if non_tri:
        log.info(
            "native_bl_polygon_wall_fan_triangulate", component="native_bl",
            n_polygon=len(non_tri), phase="beta89",
        )
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
    vnorm = compute_vertex_normals(
        points, faces, wall_face_indices, owner, cell_centres,
    )
    wall_vert_indices = sorted(vnorm.keys())

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
        wall_face_indices, _n_rej_asp, _n_rej_col = _hex_bl1_prism_guard(
            wall_face_indices, faces, points, vnorm, cfg.first_thickness,
            aspect_threshold=cfg.aspect_ratio_threshold,
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

    edge_to_walls = _build_edge_to_wall_faces(wall_face_indices, faces)
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
        list[dict[str, Any]],    # final_boundary_entries (bl_side 포함)
        list[dict[int, int]],    # layer_point_ids (quality check 용)
    ]:
        """단일 prism insertion pass. vertex_scale_pass / cum_pass 로 layer 생성.

        beta95: use_per_v_cum_pass=True 이면 vertex_cum_map_pass[v][layer_i] 를
        offset 으로 직접 사용 (per-vertex 두께 성장 곡선). 이미 vertex_scale 이
        적용된 값이므로 추가 scale 없음.
        """
        if _BL_QQQ4_LOCAL_THICKNESS and _BL_QQQ1_FRONT_COLLISION:
            try:
                # vertex 단위 collision_mask: 인접 wall vertex 와 법선이 거의 반대(dot<-0.5)
                wall_vn = np.array([vnorm[v] for v in wall_vert_indices])
                dots_v = wall_vn @ wall_vn.T
                np.fill_diagonal(dots_v, 0.0)
                coll_v = (dots_v < -0.5).any(axis=1)  # shape (Nw,)
                factors_w = _local_thickness_factor(coll_v, len(wall_vert_indices), thin_factor=0.5)
                # vertex_scale_pass 와 merge (곱); local copy 로 caller 영향 차단
                vertex_scale_pass = dict(vertex_scale_pass)
                for vi_idx, v in enumerate(wall_vert_indices):
                    vertex_scale_pass[v] = vertex_scale_pass.get(v, 1.0) * float(factors_w[vi_idx])
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
            inward_normals = np.array([-vnorm[v] for v in wall_vert_indices], dtype=np.float64).reshape(-1, 3)  # (W,3)

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

            # new_positions: (num_layers, W, 3)
            # points[wall_idx_arr_p]: (W, 3); inward_normals: (W, 3)
            # offsets_mat: (num_layers, W) → offset per layer per vertex
            # beta2246 — sign FIX: 이전은 `- inward * offset` 로 OUTWARD 방향 (cube
            # bbox max=0.503 vs orig 0.5 검증) → BL 이 원본 volume 바깥으로 확장.
            # `+ inward * offset` 로 수정 — wall (lp_ids[0]=base, offset=0) 에서
            # 시작해 INWARD 로 깊어짐. T-Rex/cfMesh 정확.
            base_pts = points[wall_idx_arr_p]                            # (W, 3)
            new_layer_pts = base_pts[None, :, :] + inward_normals[None, :, :] * offsets_mat[:, :, None]
            # new_layer_pts shape: (num_layers, W, 3)
            extra_pts_arr = new_layer_pts.reshape(-1, 3)                 # (num_layers*W, 3)
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
        p_bl_side_faces: list[list[int]] = []
        p_bl_side_owner: list[int] = []

        for fi_p in range(n_internal_orig):
            if fi_p in wall_set:
                continue
            p_int_faces.append(list(faces[fi_p]))
            p_int_owner.append(int(owner[fi_p]))
            p_int_nbr.append(int(neighbour[fi_p]))

        for pi_p, patch_p in enumerate(boundary):
            start_p = int(patch_p["startFace"])
            nf_p = int(patch_p["nFaces"])
            for k_p in range(nf_p):
                fi_p = start_p + k_p
                if fi_p in wall_set:
                    continue
                # C-BL-4 / beta2432 — patch-level face index 안전 가드.
                # validator: hard mesh 의 patch 가 stale startFace+nFaces 로
                # faces / owner 범위 벗어남. 직접 IndexError 의 두 번째 site.
                if fi_p < 0 or fi_p >= len(faces) or fi_p >= len(owner):
                    continue
                p_bnd_faces_by_patch[pi_p].append(list(faces[fi_p]))
                p_bnd_owner_by_patch[pi_p].append(int(owner[fi_p]))

        def _ltri(fi_: int, layer_: int) -> tuple[int, int, int]:
            v0_, v1_, v2_ = wall_tri_verts[fi_]
            m_ = lp_ids[layer_]
            return (m_[v0_], m_[v1_], m_[v2_])

        def _pcid(wi_: int, k_: int) -> int:
            return prism_cell_id_start + wi_ * cfg.num_layers + k_

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
                    nbrs_p = edge_to_walls.get(edge_key_p, [fi_p])
                    other_p = [g for g in nbrs_p if g != fi_p]
                    ov_a_p = lp_ids[k_p][va_p]
                    ov_b_p = lp_ids[k_p][vb_p]
                    iv_a_p = lp_ids[k_p + 1][va_p]
                    iv_b_p = lp_ids[k_p + 1][vb_p]
                    quad_p = [ov_a_p, iv_a_p, iv_b_p, ov_b_p]

                    if not other_p:
                        p_bl_side_faces.append(quad_p)
                        p_bl_side_owner.append(prism_cell_p)
                    else:
                        other_fi_p = other_p[0]
                        other_wi_p = wall_fi_to_wi.get(other_fi_p, -1)
                        if other_wi_p < 0:
                            p_bl_side_faces.append(quad_p)
                            p_bl_side_owner.append(prism_cell_p)
                            continue
                        nbr_prism_p = _pcid(other_wi_p, k_p)
                        if prism_cell_p < nbr_prism_p:
                            p_int_faces.append(quad_p)
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
        fc_p = len(out_faces)
        for pi_p, patch_p in enumerate(boundary):
            pf_p = p_bnd_faces_by_patch.get(pi_p, [])
            po_p = p_bnd_owner_by_patch.get(pi_p, [])
            sf_p = fc_p
            for f_p, o_p in zip(pf_p, po_p, strict=False):
                out_faces.append(f_p)
                out_owner.append(o_p)
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

        return fp, out_faces, out_owner, out_nbr, out_bnd_entries, lp_ids

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
    layer_point_ids: list[dict[int, int]] = []
    n_new_points = 0
    bl_side_count = 0

    for iteration in range(n_iterations):
        fp, out_faces, out_owner, out_nbr, out_bnd_entries, lp_ids = _run_prism_pass(
            current_vertex_scale, current_cum,
            vertex_cum_map_pass=vertex_cum_map if use_per_vertex_cum else None,
            use_per_v_cum_pass=use_per_vertex_cum,
        )
        final_points = fp
        final_faces = out_faces
        final_owner = out_owner
        final_nbr = out_nbr
        final_boundary_entries = out_bnd_entries
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
        _os.environ.get("AUTO_TESSELL_BL_INNER_SMOOTH", "1") != "0"
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
            # Build wall face centroid list for collision check (bounding-sphere approx).
            _wf_centroids: list[np.ndarray] = []
            for _hfi in wall_face_indices:
                _hvs = faces[_hfi]
                if len(_hvs) >= 3:
                    _wf_centroids.append(final_points[list(wall_tri_verts[_hfi])].mean(axis=0))

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
                    _col_h = any(
                        bool(np.linalg.norm(_top_c_h - _tc_h) < _r_h and
                             not np.allclose(_top_c_h, _tc_h))
                        for _tc_h in _wf_centroids
                    )
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
    _force_snap_on = _os.environ.get("AUTO_TESSELL_BL_FORCE_SNAP_WALL", "1") != "0"
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

    # 쓰기
    poly_dir.mkdir(parents=True, exist_ok=True)
    _write_points(poly_dir / "points", final_points)
    _write_faces(poly_dir / "faces", final_faces)
    _write_labels(
        poly_dir / "owner",
        np.array(final_owner, dtype=np.int64), "owner",
    )
    _write_labels(
        poly_dir / "neighbour",
        np.array(final_nbr, dtype=np.int64), "neighbour",
    )
    _write_boundary(poly_dir / "boundary", final_boundary_entries)

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
            from core.layers.aspect_cap_enforcer import enforce_prism_aspect_cap_v2 as enforce_prism_aspect_cap
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

    # beta2273 — commercial-grade mesh quality summary JSON.
    # cfMesh / Pointwise / Star-CCM+ 의 mesh quality report 동등.
    # case_dir/native_bl_quality.json 에 모든 메트릭 저장.
    try:
        import json as _json
        quality_summary = {
            "n_wall_faces": int(n_wall_faces),
            "n_wall_verts": int(len(wall_vert_indices)),
            "n_prism_cells": int(n_prism_total),
            "n_new_points": int(n_new_points),
            "total_thickness": float(total),
            "bbox_diag": float(bbox_diag),
            "thickness_to_bbox_ratio": float(total / max(bbox_diag, 1e-30)),
            "n_degenerate_prisms": int(n_degen),
            "max_aspect_ratio": float(max_ar),
            "wall_preserve": {
                "max_diff": float(wall_preserve_max_diff),
                "max_diff_rel": float(wall_preserve_rel),
                "n_drift": int(n_wall_drift),
                "within_envelope": bool(wall_within_env),
                "envelope_eps_rel": 1e-6,
            },
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
            # C3.3 / beta2377 — anisotropic prism split diagnostic (cfMesh 동등).
            "aniso_split": {
                "n_examined": int(aniso_split_n_examined),
                "n_would_split": int(aniso_split_n_would),
                "max_aspect_in": float(aniso_split_max_asp_in),
            },
            # beta2328 — pre-BL wall surface SI count (P2.6 series).
            # None = 측정 안 됨 (>5000 face), 0 = clean, >0 = 입력에 SI 존재.
            "pre_bl_self_intersect": _pre_bl_si_count,
            "config": {
                "num_layers": int(cfg.num_layers),
                "growth_ratio": float(cfg.growth_ratio),
                "first_thickness": float(cfg.first_thickness),
                "target_y_plus": cfg.target_y_plus,
                "flow_fluid_preset": cfg.flow_fluid_preset,
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
    return NativeBLResult(
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
        n_snap_applied=int(n_snap),
        snap_max_diff=float(snap_max_diff),
        lcr_n_reduced_verts=int(lcr_n_reduced),
        lcr_max_reduction=int(lcr_max_reduction),
        lcr_min_layers_used=int(lcr_min_layers_used),
        lcr_n_safe_full_layers=int(lcr_n_safe_full),
        aniso_split_n_examined=int(aniso_split_n_examined),
        aniso_split_n_would_split=int(aniso_split_n_would),
        aniso_split_max_aspect_in=float(aniso_split_max_asp_in),
        message=(
            f"native_bl Phase 2 OK — {n_prism_total} prism cells inserted "
            f"({cfg.num_layers} layers × {n_wall_faces} wall triangles). "
            f"total_thickness={total:.4g}, bbox={bbox_diag:.3g}, "
            f"bl_side_faces={bl_side_count}, "
            f"degenerate={n_degen}/{n_prism_total}, max_ar={max_ar:.1f}."
        ),
    )
