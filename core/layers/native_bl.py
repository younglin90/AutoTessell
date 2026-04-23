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

Phase 3 예정 (v0.5+): shrinkage iteration (반복 수렴), 완전 비균일 prism.

라이선스: 모든 알고리즘 clean-room 구현 (numpy + 공개 문서 기반).
"""
from __future__ import annotations

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
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class BLConfig:
    """Native BL 생성 설정."""
    num_layers: int = 3
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
    aspect_ratio_threshold: float = 50.0
    # beta93: shrinkage iteration — 품질 불량 prism vertex 두께를 반복적으로 줄여 수렴.
    shrink_iterations: int = 1      # 반복 최대 횟수 (1=기존 단일 pass)
    shrink_factor: float = 0.7      # 각 iteration 에서 불량 vertex scale 감소율
    shrink_aspect_threshold: float = 30.0  # 이 값 초과 prism → 해당 vertex 두께 감소
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

    OpenFOAM polyMesh convention: boundary face normal 은 owner cell 에서 바깥 방향.
    cell_centres 가 주어지면 face centre → cell centre 반대 방향으로 sign 교정.
    """
    vertex_accum: dict[int, np.ndarray] = {}

    for fi in wall_face_indices:
        face = faces[fi]
        n, area = _face_normal_area(points, face)
        if area < 1e-30:
            continue
        # Sign fix: face centre 가 owner cell centre 의 바깥쪽이어야 함
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

    # Normalize
    result: dict[int, np.ndarray] = {}
    for v, acc in vertex_accum.items():
        m = float(np.linalg.norm(acc))
        if m > 1e-30:
            result[v] = acc / m
        else:
            result[v] = np.zeros(3)
    return result


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

    Returns:
        (n_degenerate, max_ratio) — degenerate 는 ratio > threshold.
    """
    n_degenerate = 0
    max_ratio = 0.0
    for fi in wall_face_indices:
        if fi not in wall_tri_verts:
            continue
        v0, v1, v2 = wall_tri_verts[fi]
        for k in range(num_layers):
            o0 = points[layer_point_ids[k][v0]]
            o1 = points[layer_point_ids[k][v1]]
            o2 = points[layer_point_ids[k][v2]]
            i0 = points[layer_point_ids[k + 1][v0]]
            i1 = points[layer_point_ids[k + 1][v1]]
            i2 = points[layer_point_ids[k + 1][v2]]
            # outer edge 길이
            e_outer = max(
                float(np.linalg.norm(o1 - o0)),
                float(np.linalg.norm(o2 - o1)),
                float(np.linalg.norm(o0 - o2)),
            )
            # 각 vertex 의 height (outer ↔ inner)
            h = min(
                float(np.linalg.norm(i0 - o0)),
                float(np.linalg.norm(i1 - o1)),
                float(np.linalg.norm(i2 - o2)),
            )
            if h < 1e-30:
                # height 0 → degenerate
                n_degenerate += 1
                max_ratio = max(max_ratio, 1e9)
                continue
            ratio = e_outer / h
            if ratio > max_ratio:
                max_ratio = ratio
            if ratio > threshold:
                n_degenerate += 1
    return n_degenerate, float(max_ratio)


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
    # 먼저 wall triangle 의 unit normal 배열
    face_normal: dict[int, np.ndarray] = {}
    for fi in wall_face_indices:
        f = faces[fi]
        if len(f) != 3:
            continue
        n, a = _face_normal_area(points, f)
        if a > 1e-30:
            face_normal[fi] = n

    # edge → 공유 face pair
    edge_to_face: dict[tuple[int, int], list[int]] = {}
    for fi in wall_face_indices:
        f = faces[fi]
        if len(f) != 3:
            continue
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            key = (a, b) if a < b else (b, a)
            edge_to_face.setdefault(key, []).append(fi)

    cos_thresh = float(np.cos(np.deg2rad(feature_angle_deg)))
    feature_verts: set[int] = set()
    for (a, b), fl in edge_to_face.items():
        if len(fl) != 2:
            continue
        n1 = face_normal.get(fl[0])
        n2 = face_normal.get(fl[1])
        if n1 is None or n2 is None:
            continue
        cos_a = float(np.clip(np.dot(n1, n2), -1.0, 1.0))
        # feature = bending > threshold → cos < cos_thresh
        if cos_a < cos_thresh:
            feature_verts.add(int(a))
            feature_verts.add(int(b))
    return feature_verts


def _compute_collision_distance(
    points: np.ndarray,
    faces: list[list[int]],
    wall_face_indices: list[int],
    wall_vert_indices: list[int],
    vnorm: dict[int, np.ndarray],
    *,
    max_tris: int = 20000,
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
    # beta85: numpy → string 변환 (for-loop 대비 ~5× 빠름)
    data = "\n".join(map(str, labels.tolist())) + "\n"
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
    edge_map: dict[tuple[int, int], list[int]] = {}
    for fi in wall_face_indices:
        v = faces[fi]
        if len(v) != 3:
            continue
        for a, b in ((v[0], v[1]), (v[1], v[2]), (v[2], v[0])):
            key = (a, b) if a < b else (b, a)
            edge_map.setdefault(key, []).append(fi)
    return edge_map


def generate_native_bl(
    case_dir: Path,
    config: BLConfig | None = None,
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
    thicknesses = np.array(
        [cfg.first_thickness * (cfg.growth_ratio ** i) for i in range(cfg.num_layers)],
        dtype=np.float64,
    )
    total = float(thicknesses.sum())
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
    vert_to_cells: dict[int, list[int]] = {v: [] for v in wall_vert_indices}
    for fi in wall_face_indices:
        own = int(owner[fi])
        for v in faces[fi]:
            if int(v) in vert_to_cells:
                vert_to_cells[int(v)].append(own)
    vert_min_cell_dist: dict[int, float] = {}
    for v, clist in vert_to_cells.items():
        if not clist:
            continue
        dists = [float(np.linalg.norm(points[v] - cell_centres[c])) for c in clist]
        vert_min_cell_dist[v] = min(dists)
    if vert_min_cell_dist:
        min_local = float(min(vert_min_cell_dist.values()))
        local_cap = max(min_local * 0.8, cfg.first_thickness)
        if total > local_cap:
            scale = local_cap / total
            thicknesses *= scale
            total = float(thicknesses.sum())
            log.info(
                "native_bl_local_safety_scaled", component="native_bl",
                factor=scale, min_local=min_local, new_total=total,
            )
            cum = np.concatenate(([0.0], np.cumsum(thicknesses)))

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
    collision_dist: dict[int, float] = {}
    if cfg.collision_safety:
        collision_dist = _compute_collision_distance(
            points, faces, wall_face_indices, wall_vert_indices, vnorm,
        )
        if collision_dist:
            safety = float(cfg.collision_safety_factor)
            # beta90: 전역 cap (기존) + per-vertex cap (신규).
            # 전역 cap: global min collision distance → global thickness 축소.
            min_collision = float(min(collision_dist.values()))
            collision_cap = max(min_collision * safety, cfg.first_thickness)
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
        if collision_dist and v in collision_dist and total > 1e-30:
            v_cap = collision_dist[v] * float(cfg.collision_safety_factor)
            v_cap = max(v_cap, cfg.first_thickness)
            v_scale_coll = min(v_cap / total, 1.0)
            s = min(s, v_scale_coll)  # 두 제약 중 더 엄격한 쪽
        vertex_scale[v] = s
    if any(s < 1.0 for s in vertex_scale.values()):
        n_limited = sum(1 for s in vertex_scale.values() if s < 1.0)
        log.info(
            "native_bl_per_vertex_scale", component="native_bl", phase="beta90",
            n_limited_verts=n_limited,
            min_scale=float(min(vertex_scale.values())),
        )

    # 공유 캐시: wall_face_indices 기반 topology (loop 밖에서 한 번만 계산)
    n_wall_faces = len(wall_face_indices)
    n_prism_per_face = cfg.num_layers
    n_prism_total = n_wall_faces * n_prism_per_face
    prism_cell_id_start = n_cells  # prism cell IDs: [n_cells, n_cells + n_prism_total)

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
        # 5) 새 point 배열 구성
        new_pts = points.copy()
        wall_idx_arr_p = np.array(wall_vert_indices, dtype=np.int64)

        if use_per_v_cum_pass and vertex_cum_map_pass:
            # per-vertex total thickness = vertex_cum_map_pass[v][-1]
            for vi_idx, v in enumerate(wall_vert_indices):
                v_total = float(vertex_cum_map_pass[v][-1]) if v in vertex_cum_map_pass else (
                    total * vertex_scale_pass.get(v, 1.0)
                )
                new_pts[v] = points[v] + (-vnorm[v]) * v_total
        else:
            inward_v = np.array([-vnorm[v] for v in wall_vert_indices])
            scales_v = np.array(
                [vertex_scale_pass.get(v, 1.0) for v in wall_vert_indices], dtype=np.float64,
            )[:, None]
            new_pts[wall_idx_arr_p] = points[wall_idx_arr_p] + inward_v * (total * scales_v)

        lp_ids: list[dict[int, int]] = [{} for _ in range(cfg.num_layers + 1)]
        extra_pts: list[np.ndarray] = []
        cursor_p = len(points)
        for layer_i in range(cfg.num_layers + 1):
            if layer_i == cfg.num_layers:
                for v in wall_vert_indices:
                    lp_ids[layer_i][v] = int(v)
            else:
                for v in wall_vert_indices:
                    # beta95: per-vertex cum 있으면 그걸 사용, 없으면 기존 방식
                    if use_per_v_cum_pass and vertex_cum_map_pass and v in vertex_cum_map_pass:
                        offset_v = float(vertex_cum_map_pass[v][layer_i])
                        # 이미 scale 포함됨 → 추가 v_scale 불필요
                    else:
                        offset_v = float(cum_pass[layer_i]) * vertex_scale_pass.get(v, 1.0)
                    p_new = points[v] - vnorm[v] * offset_v
                    extra_pts.append(p_new)
                    lp_ids[layer_i][v] = cursor_p
                    cursor_p += 1

        if extra_pts:
            fp = np.vstack([new_pts, np.array(extra_pts)])
        else:
            fp = new_pts

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
            out_bnd_entries.append({
                "name": "bl_side",
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
            e["nFaces"] for e in out_bnd_entries if e.get("name") == "bl_side"
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

    # backup
    if cfg.backup_original:
        bak = case_dir / "constant" / "polyMesh_pre_bl"
        if bak.exists():
            shutil.rmtree(bak)
        shutil.copytree(poly_dir, bak)

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
        message=(
            f"native_bl Phase 2 OK — {n_prism_total} prism cells inserted "
            f"({cfg.num_layers} layers × {n_wall_faces} wall triangles). "
            f"total_thickness={total:.4g}, bbox={bbox_diag:.3g}, "
            f"bl_side_faces={bl_side_count}, "
            f"degenerate={n_degen}/{n_prism_total}, max_ar={max_ar:.1f}."
        ),
    )
