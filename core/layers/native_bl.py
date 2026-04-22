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

Phase 1 한계:
  - Wall 모든 vertex 에 동일 total thickness (collision check 없음 — convex wall 가정)
  - Feature edge 보존 없음
  - Quality check 없음 (degenerate prism 가능성 있음)

Phase 2 예정: collision, shrinkage, feature lock.

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
    lines = [_FOAM_HEADER.format(cls="vectorField", obj="points")]
    lines.append(f"{len(points)}\n(")
    for p in points:
        lines.append(f"({p[0]:.9g} {p[1]:.9g} {p[2]:.9g})")
    lines.append(")")
    lines.append(_FOAM_FOOTER)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_faces(path: Path, faces: list[list[int]]) -> None:
    lines = [_FOAM_HEADER.format(cls="faceList", obj="faces")]
    lines.append(f"{len(faces)}\n(")
    for f in faces:
        lines.append(f"{len(f)}(" + " ".join(str(v) for v in f) + ")")
    lines.append(")")
    lines.append(_FOAM_FOOTER)
    path.write_text("\n".join(lines), encoding="utf-8")


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
    lines = [header]
    lines.append(f"{len(labels)}\n(")
    for v in labels:
        lines.append(str(int(v)))
    lines.append(")")
    lines.append(_FOAM_FOOTER)
    path.write_text("\n".join(lines), encoding="utf-8")


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
    log.info("native_bl_read", n_cells=n_cells, n_faces=n_faces_orig,
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

    # Wall face 가 모두 triangle 인지 체크 (MVP 제약)
    non_tri = [fi for fi in wall_face_indices if len(faces[fi]) != 3]
    if non_tri:
        log.warning("native_bl_non_triangle_wall", count=len(non_tri))
        # triangle 만 처리, non-tri 는 skip
        wall_face_indices = [fi for fi in wall_face_indices if len(faces[fi]) == 3]

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
        log.warning("native_bl_thickness_scaled", factor=scale, new_total=total)
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
                "native_bl_local_safety_scaled",
                factor=scale, min_local=min_local, new_total=total,
            )
            cum = np.concatenate(([0.0], np.cumsum(thicknesses)))

    # 5) 새 point 배열 구성
    # - original points 배열에서 wall vertex 를 inward total 만큼 이동 (기존 cell 이 따라 축소)
    # - 각 layer 경계의 wall vertex copy 를 추가 (N+1 층)
    # - layer[0] = 원래 wall 위치 (boundary 최외곽)
    # - layer[N] = shrunk 위치 (기존 cell 과 공유)
    # 기존 cells 의 wall vertex 들은 shrunk points 사용 → 원래 위치는 layer 0 에서만
    new_points_list: list[np.ndarray] = [points.copy()]
    # 원래 points 의 wall vertex 들을 shrunk 위치로 변경 (in-place)
    inward = np.array([-vnorm[v] for v in wall_vert_indices])
    wall_idx_arr = np.array(wall_vert_indices, dtype=np.int64)
    new_points_list[0][wall_idx_arr] = points[wall_idx_arr] + inward * total

    # 각 layer 의 wall vertex copy — global id 매핑
    # layer_point_ids[i][v] = layer i 에 해당하는 wall vertex v 의 new global id
    # layer 0 = 원래 wall 위치 (추가 point 로)
    # layer 1 = 원래 - t1*normal
    # ...
    # layer N = shrunk (== new_points[wall_idx] — 이미 있음)
    layer_point_ids: list[dict[int, int]] = [{} for _ in range(cfg.num_layers + 1)]
    extra_points_list: list[np.ndarray] = []
    cursor = len(points)  # next new point id
    for layer_i in range(cfg.num_layers + 1):
        if layer_i == cfg.num_layers:
            # 최내곽: shrunk wall == 이미 new_points 에 있음 (원 index 재사용)
            for v in wall_vert_indices:
                layer_point_ids[layer_i][v] = int(v)
        else:
            offset = cum[layer_i]  # 0 for layer 0, t1 for layer 1, ...
            for v in wall_vert_indices:
                p_new = points[v] - vnorm[v] * offset
                extra_points_list.append(p_new)
                layer_point_ids[layer_i][v] = cursor
                cursor += 1

    # 최종 points 배열
    if extra_points_list:
        final_points = np.vstack([new_points_list[0], np.array(extra_points_list)])
    else:
        final_points = new_points_list[0]
    n_new_points = len(final_points) - len(points)

    # 6) Prism cell 위상 구성 — Phase 2 완성 구현
    n_wall_faces = len(wall_face_indices)
    n_prism_per_face = cfg.num_layers
    n_prism_total = n_wall_faces * n_prism_per_face
    prism_cell_id_start = n_cells  # prism cell IDs: [n_cells, n_cells + n_prism_total)

    # wall triangle 의 edge → 이웃 wall triangle 매핑
    edge_to_walls = _build_edge_to_wall_faces(wall_face_indices, faces)

    # wall_face_indices 를 순회하며 (wi) 값 = prism block index
    wall_fi_to_wi: dict[int, int] = {fi: wi for wi, fi in enumerate(wall_face_indices)}

    # 각 wall face 당 orig_owner / patch_idx / triangle vertices 캐시
    wall_tri_verts: dict[int, tuple[int, int, int]] = {}
    wall_orig_owner: dict[int, int] = {}
    wall_orig_patch: dict[int, int] = {}
    for fi in wall_face_indices:
        v = faces[fi]
        wall_tri_verts[fi] = (v[0], v[1], v[2])
        wall_orig_owner[fi] = int(owner[fi])
        wall_orig_patch[fi] = face_to_patch[fi][0]

    # 결과 face 컨테이너
    # internal faces (순서 유지)
    out_int_faces: list[list[int]] = []
    out_int_owner: list[int] = []
    out_int_nbr: list[int] = []
    # boundary faces — patch 별 리스트 (vertices only, owner 는 별도)
    out_bnd_faces_by_patch: dict[int, list[list[int]]] = {pi: [] for pi in range(len(boundary))}
    out_bnd_owner_by_patch: dict[int, list[int]] = {pi: [] for pi in range(len(boundary))}
    # bl_side 신규 patch (wall 의 edge-of-wall 부분만, manifold 내부는 internal)
    bl_side_faces: list[list[int]] = []
    bl_side_owner: list[int] = []

    # 6a) 기존 internal face 유지 (wall 아닌 것만; wall 은 internal 이 아니므로 실제론 전부 유지됨)
    wall_set = set(wall_face_indices)
    for fi in range(n_internal_orig):
        if fi in wall_set:
            # 이론상 wall 은 boundary 이므로 internal 에 올 수 없지만 안전장치
            continue
        out_int_faces.append(list(faces[fi]))
        out_int_owner.append(int(owner[fi]))
        out_int_nbr.append(int(neighbour[fi]))

    # 6b) 기존 boundary faces 중 wall 이 아닌 것들 유지 (patch 순서)
    for pi, patch in enumerate(boundary):
        start = int(patch["startFace"])
        nf = int(patch["nFaces"])
        for k in range(nf):
            fi = start + k
            if fi in wall_set:
                continue
            out_bnd_faces_by_patch[pi].append(list(faces[fi]))
            out_bnd_owner_by_patch[pi].append(int(owner[fi]))

    # 6c) Prism block 처리
    # 중복 생성을 막기 위한 set:
    #   - layer k (outer) triangle 을 이웃 prism 과 공유할 때 한 쪽에서만 생성
    #   - side quad 는 edge 쌍에서 한 쪽에서만 생성
    # 여기선 모든 내부 face 에 대해 "owner cell ID 가 더 작은 쪽" 이 생성 책임.

    def _layer_triangle(fi: int, layer: int) -> tuple[int, int, int]:
        v0, v1, v2 = wall_tri_verts[fi]
        m = layer_point_ids[layer]
        return (m[v0], m[v1], m[v2])

    def _prism_cell_id(wi_: int, k_: int) -> int:
        return prism_cell_id_start + wi_ * cfg.num_layers + k_

    for wi, fi in enumerate(wall_face_indices):
        patch_idx = wall_orig_patch[fi]
        orig_own = wall_orig_owner[fi]
        v0, v1, v2 = wall_tri_verts[fi]

        for k in range(cfg.num_layers):
            prism_cell = _prism_cell_id(wi, k)
            outer_tri = _layer_triangle(fi, k)
            inner_tri = _layer_triangle(fi, k + 1)

            # --- triangle face (outer / inner) ---
            if k == 0:
                # layer 0 outer = 새 wall boundary. winding = 원본 wall face 와 동일
                # (원래 tet owner 바깥 방향이었으므로, prism_cell 바깥 방향과 일치).
                out_bnd_faces_by_patch[patch_idx].append(list(outer_tri))
                out_bnd_owner_by_patch[patch_idx].append(prism_cell)
            # layer k (>=1) outer = 이전 prism (k-1) 과 공유. "outer" side 는 이미
            # prism(k-1) 입장에서 inner_tri 로서 생성되므로 여기선 skip.

            if k == cfg.num_layers - 1:
                # 최내곽 → 원래 tet cell 과 internal
                # OpenFOAM: owner < neighbour, normal points owner → neighbour.
                # prism_cell > orig_own (prism 이 나중에 추가되므로). owner = orig_own,
                # neighbour = prism_cell. normal 은 orig_own → prism_cell 방향.
                # inner_tri winding 은 원본 wall 과 같은 방향 (prism 바깥 = shrunk 외부 =
                # 원본 tet 안쪽). 원본 tet 기준으로는 inner_tri 가 "outward from
                # orig_own" 이 되려면 → prism 의 inner_tri 그대로 사용 시 tet→prism 방향.
                #
                # 원본 wall face 는 owner=orig_own 에서 바깥 (+normal) 방향이었고,
                # inner_tri 는 원본 wall 에서 inward (-normal) 로 이동한 위치. 원본
                # winding 유지 시 normal 여전히 +normal 방향 → orig_own 외부 → prism 방향.
                # 이는 orig_own(owner) → prism(neighbour) 로 정확히 일치.
                out_int_faces.append(list(inner_tri))
                out_int_owner.append(orig_own)
                out_int_nbr.append(prism_cell)
            else:
                # layer k 와 layer k+1 사이 prism↔prism internal.
                # owner = prism_cell (k, outer), neighbour = prism_next (k+1, inner).
                # owner → neighbour 방향은 outer → inner = -normal (안쪽).
                # inner_tri 의 원본 winding 은 +normal (wall 바깥 방향) 이므로 반전
                # 해야 -normal 방향 = owner→neighbour 이 된다.
                prism_next = _prism_cell_id(wi, k + 1)
                owner_cell = prism_cell   # prism_cell < prism_next 이므로
                nbr_cell = prism_next
                out_int_faces.append(list(reversed(inner_tri)))
                out_int_owner.append(owner_cell)
                out_int_nbr.append(nbr_cell)

            # --- side quad face (3 edges) ---
            tri_idx = [(0, 1), (1, 2), (2, 0)]
            for ei, (a, b) in enumerate(tri_idx):
                va, vb = wall_tri_verts[fi][a], wall_tri_verts[fi][b]
                edge_key = (va, vb) if va < vb else (vb, va)
                neighbours = edge_to_walls.get(edge_key, [fi])
                # 이웃 wall face (fi 자신 포함). manifold 이면 길이 2, boundary of
                # wall 이면 1.
                other = [g for g in neighbours if g != fi]
                ov_a = layer_point_ids[k][va]
                ov_b = layer_point_ids[k][vb]
                iv_a = layer_point_ids[k + 1][va]
                iv_b = layer_point_ids[k + 1][vb]
                # quad winding 분석:
                #   [ov_a, ov_b, iv_b, iv_a] 순서 시 n = (edge × -normal) = triangle
                #   내부 방향 → prism_cell "inward" → owner outward 반대 → 부호 틀림.
                #   [ov_a, iv_a, iv_b, ov_b] 로 반전하면 n = (-normal × edge_backward)
                #   = edge × normal = triangle 바깥 방향 → prism_cell outward ✓.
                quad = [ov_a, iv_a, iv_b, ov_b]

                if not other:
                    # wall 의 경계 edge — bl_side 신규 boundary patch
                    bl_side_faces.append(quad)
                    bl_side_owner.append(prism_cell)
                else:
                    # 이웃 prism 과 internal (두 prism 이 같은 quad 를 공유)
                    other_fi = other[0]
                    other_wi = wall_fi_to_wi.get(other_fi, -1)
                    if other_wi < 0:
                        bl_side_faces.append(quad)
                        bl_side_owner.append(prism_cell)
                        continue
                    neighbour_prism = _prism_cell_id(other_wi, k)
                    if prism_cell < neighbour_prism:
                        # 내가 owner — 이 quad 를 internal 로 추가
                        owner_cell = prism_cell
                        nbr_cell = neighbour_prism
                        # 현재 winding 기준으로 normal 방향이 prism_cell 외부
                        # = neighbour_prism 쪽이 됨 → owner→neighbour ✓
                        out_int_faces.append(quad)
                        out_int_owner.append(owner_cell)
                        out_int_nbr.append(nbr_cell)
                    # else: 반대쪽 prism 이 owner — 그쪽이 나중에 생성할 것이므로 skip

    # 7) polyMesh 쓰기
    # 기존 boundary 의 patch 정의 유지 + 새 face 들로 nFaces/startFace 재구성.
    # 최종 face 순서 = [internal...] + [boundary patch 0 faces...] + [patch 1...] + ... + [bl_side...]
    # 각 patch 에 대한 face 수: out_bnd_faces_by_patch[pi] + wall patch 의 경우 새 wall faces 포함
    final_faces: list[list[int]] = []
    final_owner: list[int] = []
    final_nbr: list[int] = []
    # 7a) internal faces
    final_faces.extend(out_int_faces)
    final_owner.extend(out_int_owner)
    final_nbr.extend(out_int_nbr)

    # 7b) boundary faces — patch 순서 유지
    final_boundary_entries: list[dict[str, Any]] = []
    face_cursor = len(final_faces)
    for pi, patch in enumerate(boundary):
        p_faces = out_bnd_faces_by_patch.get(pi, [])
        p_owner = out_bnd_owner_by_patch.get(pi, [])
        start_face = face_cursor
        for f, o in zip(p_faces, p_owner, strict=False):
            final_faces.append(f)
            final_owner.append(o)
        face_cursor += len(p_faces)
        final_boundary_entries.append({
            "name": patch.get("name", f"patch_{pi}"),
            "type": patch.get("type", "patch"),
            "nFaces": len(p_faces),
            "startFace": start_face,
        })

    # 7c) bl_side patch (있는 경우에만)
    if bl_side_faces:
        start_face = face_cursor
        for f, o in zip(bl_side_faces, bl_side_owner, strict=False):
            final_faces.append(f)
            final_owner.append(o)
        face_cursor += len(bl_side_faces)
        final_boundary_entries.append({
            "name": "bl_side",
            "type": "wall",
            "nFaces": len(bl_side_faces),
            "startFace": start_face,
        })

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

    elapsed = time.perf_counter() - t_start
    return NativeBLResult(
        success=True,
        elapsed=elapsed,
        n_wall_faces=n_wall_faces,
        n_wall_verts=len(wall_vert_indices),
        n_prism_cells=n_prism_total,
        n_new_points=n_new_points,
        total_thickness=total,
        message=(
            f"native_bl Phase 2 OK — {n_prism_total} prism cells inserted "
            f"({cfg.num_layers} layers × {n_wall_faces} wall triangles). "
            f"total_thickness={total:.4g}, bbox={bbox_diag:.3g}, "
            f"bl_side_faces={len(bl_side_faces)}."
        ),
    )
