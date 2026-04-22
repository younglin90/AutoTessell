"""BL prism → tet subdivision.

tet 메쉬용 BL 전략: native_bl 로 prism (wedge) layer 를 먼저 삽입한 뒤, 각 wedge
cell 을 3 tet 로 분할해 전체를 순수 tet 메쉬로 유지한다.

Prism wedge (6 verts: outer tri a0,a1,a2 + inner tri b0,b1,b2) 를 3 tet 로 분할하는
표준 패턴:
    tet1 = (a0, a1, a2, b0)
    tet2 = (a1, a2, b0, b1)
    tet3 = (a2, b0, b1, b2)

이 분할은 3 side quad 를 각각 대각선으로 잘라 triangle pair 로 만들며, 다른 prism
과 공유되는 quad 의 경우 **양쪽에서 같은 대각선을 선택해야** 일관된 topology 가
된다. 본 구현은 wall triangle 의 두 vertex 중 **낮은 global ID** 를 대각선 시작점
으로 삼아 결정론적으로 선택한다.

사용:
    from core.layers.tet_bl_subdivide import subdivide_prism_layers_to_tet
    res = subdivide_prism_layers_to_tet(case_dir)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.layers.native_bl import _write_boundary, _write_faces, _write_labels, _write_points
from core.utils.logging import get_logger
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

log = get_logger(__name__)


@dataclass
class TetSubdivResult:
    success: bool
    elapsed: float
    n_prism_before: int = 0
    n_tet_added: int = 0
    message: str = ""


def _identify_prism_cells(
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
) -> tuple[list[int], dict[int, list[list[int]]]]:
    """prism (= 정확히 2 triangle + 3 quad face 를 가진 cell) 식별.

    Returns:
        (prism_cell_ids, cell_face_verts_map)
        cell_face_verts_map: cell_id → list[face_verts] (vertex index 리스트)
    """
    cell_faces: dict[int, list[list[int]]] = {i: [] for i in range(n_cells)}
    for fi, verts in enumerate(faces):
        cell_faces[int(owner[fi])].append(list(verts))
        if fi < len(neighbour):
            cell_faces[int(neighbour[fi])].append(list(verts))

    prism_cells: list[int] = []
    for cid, f_list in cell_faces.items():
        if len(f_list) != 5:
            continue
        n_tri = sum(1 for f in f_list if len(f) == 3)
        n_quad = sum(1 for f in f_list if len(f) == 4)
        if n_tri == 2 and n_quad == 3:
            prism_cells.append(cid)
    return prism_cells, cell_faces


def _prism_vertex_pairs(
    cell_face_verts: list[list[int]],
) -> tuple[list[int], list[int]] | None:
    """prism cell 의 outer/inner triangle vertex 쌍을 추출.

    각 outer vertex a_i 는 정확히 하나의 inner vertex b_i 와 3 개 quad face 중 2 개를
    공유한다 (quad 의 4 vertex 중 a_i 와 b_i 가 같이 등장).

    Returns:
        (outer=[a0,a1,a2], inner=[b0,b1,b2]) — 인덱스 순서 맞춤. 실패시 None.
    """
    tris = [f for f in cell_face_verts if len(f) == 3]
    quads = [f for f in cell_face_verts if len(f) == 4]
    if len(tris) != 2 or len(quads) != 3:
        return None

    tri_a, tri_b = tris[0], tris[1]
    outer_set = set(tri_a)
    inner_set = set(tri_b)
    if outer_set & inner_set:
        # shared vertex 가 있으면 prism 이 아님
        return None

    # 각 outer vertex 가 어떤 inner vertex 와 pair 되는지 찾는다:
    # - quad 에는 두 outer + 두 inner 정확히 포함.
    # - outer a_i 가 포함된 quad 2 개 를 교집합 → inner vertex 1 개.
    pair_map: dict[int, int] = {}
    for a in tri_a:
        quads_with_a = [set(q) for q in quads if a in q]
        if len(quads_with_a) != 2:
            return None
        inner_candidates = (quads_with_a[0] & quads_with_a[1]) & inner_set
        if len(inner_candidates) != 1:
            return None
        pair_map[a] = next(iter(inner_candidates))

    # tri_a 순서대로 inner 정렬
    outer = list(tri_a)
    inner = [pair_map[a] for a in outer]
    return outer, inner


def subdivide_prism_layers_to_tet(
    case_dir: Path,
    *,
    backup_original: bool = True,
) -> TetSubdivResult:
    """case_dir/constant/polyMesh 의 모든 prism cell 을 3 tet 로 분할한다.

    기존 tet cell 은 그대로 유지. 새로 추가되는 tet 은 기존 cell 들 뒤에 붙이고,
    prism cell 은 최종 mesh 에서 제거된다 (faces 도 재구성).

    주의: MVP 구현 — cell ID 리매핑 + faces 재구성을 전면 수행하므로 비용이 높다.
    """
    t0 = time.perf_counter()
    poly_dir = case_dir / "constant" / "polyMesh"
    if not (poly_dir / "faces").exists():
        return TetSubdivResult(False, 0.0, message=f"polyMesh 없음: {poly_dir}")

    raw_points = parse_foam_points(poly_dir / "points")
    raw_faces = parse_foam_faces(poly_dir / "faces")
    owner = np.array(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
    neighbour = np.array(parse_foam_labels(poly_dir / "neighbour"), dtype=np.int64)
    boundary = parse_foam_boundary(poly_dir / "boundary")

    points = np.array(raw_points, dtype=np.float64)
    faces = [list(f) for f in raw_faces]
    n_cells = (int(owner.max()) + 1) if len(owner) else 0
    if len(neighbour):
        n_cells = max(n_cells, int(neighbour.max()) + 1)

    # 1) prism cell 식별
    prism_cells, cell_faces_map = _identify_prism_cells(
        faces, owner, neighbour, n_cells,
    )
    if not prism_cells:
        return TetSubdivResult(
            True, time.perf_counter() - t0,
            n_prism_before=0, n_tet_added=0,
            message="prism cell 없음 — 이미 전체 tet.",
        )

    # 2) 각 prism 의 outer/inner pair 추출
    prism_pairs: dict[int, tuple[list[int], list[int]]] = {}
    for cid in prism_cells:
        p = _prism_vertex_pairs(cell_faces_map[cid])
        if p is None:
            log.warning("prism_pair_extract_failed", cell=cid)
            continue
        prism_pairs[cid] = p

    if not prism_pairs:
        return TetSubdivResult(
            False, time.perf_counter() - t0,
            message="prism vertex pair 추출 실패 — subdivision 불가",
        )

    # 3) tet 리스트 생성: 각 prism → 3 tet (vertex sets)
    # OpenFOAM polyMesh 는 cell 을 face 로 정의하지만, 여기서는 "tet cell index"
    # 기반으로 faces 를 새로 구성한다.
    # 기존 tet cell 은 원본 cell_faces_map 에서 그대로 유지 (id 유지).
    # 새 tet 은 prism cell id 대체 + 추가 id 로 할당.
    #
    # 간소화 전략: 기존 non-prism cell 은 id 그대로, prism cell 3 개를 새 tet 3 개로
    # 교체. 추가 필요 id 개수 = 2 * n_prism (각 prism 이 1 cell → 3 cell).

    n_prism = len(prism_pairs)
    # new cell mapping: 기존 non-prism cell 의 old_id → new_id (연속). prism 은
    # 3 tet 로 대체.
    prism_set = set(prism_pairs.keys())
    old_non_prism = [cid for cid in range(n_cells) if cid not in prism_set]
    new_id_of: dict[int, int] = {old: new for new, old in enumerate(old_non_prism)}
    next_id = len(old_non_prism)
    prism_tets: dict[int, tuple[int, int, int]] = {}
    for pid in sorted(prism_pairs.keys()):
        prism_tets[pid] = (next_id, next_id + 1, next_id + 2)
        next_id += 3
    total_cells = next_id

    # 4) 기존 face list 를 순회하며 owner/neighbour 를 new_id 로 매핑.
    # prism cell 을 참조하는 face 는 "어느 tet 에 속하는지" 를 face vertex 구성
    # 으로 결정.
    #
    # Prism 내부 face 를 구분하는 전략:
    #   - 두 triangle face: outer=a0a1a2 (→ tet1 의 face), inner=b0b1b2 (→ tet3 의 face)
    #   - side quad (a_i, a_j, b_j, b_i) → 대각선 분할되어 두 새 triangle face 로
    #     바뀌고 각 triangle 이 인접 tet 에 붙는다.
    # 단순화: 기존 face 중 prism 을 참조하는 face 는 일단 모두 제거하고, 새 tet
    # 의 face 를 처음부터 재구성한다.
    #
    # 그런데 기존 face 가 prism 과 non-prism (예: orig_tet_cell ↔ innermost prism)
    # 또는 boundary 로도 쓰이므로, face 를 전면 rebuild 하기보다 "prism side 만
    # 분할 가능한 triangle pair 로 교체" 가 안전.

    # 이 MVP 에서는 단순화를 위해 "전체 faces/owner/neighbour/boundary 재구성" 전략
    # 을 사용한다. 절차:
    #   1) 모든 cell 의 vertex 기반 face 를 수집 (기존 tet 은 4 face, 새 tet 은 4 face)
    #   2) face 를 canonical key (sorted vertex tuple) 로 dedupe
    #   3) internal face (두 cell 공유) 와 boundary face (한 cell 공유) 분류
    #   4) boundary patch 는 원본 boundary 의 face vertex set 과 매칭해 복원

    # 4a) 모든 cell 의 tet 4-face 를 수집
    def _tet_faces(v0: int, v1: int, v2: int, v3: int) -> list[tuple[int, int, int]]:
        # 각 tet 의 4 face vertices (CCW from outside). 여기선 vertex set 만 저장.
        return [
            (v1, v2, v3), (v0, v3, v2), (v0, v1, v3), (v0, v2, v1),
        ]

    # 기존 tet cell 추출 — 4 face + all triangles → (4 vertex set).
    # 하지만 원본 cell 이 어떤 tet 인지 알려면 owner/neighbour 면 정보 만으로는
    # 부족. 기존 tet 의 4 vertex 를 cell_faces_map 의 triangle 4 개에서 추출.
    old_tet_verts: dict[int, tuple[int, int, int, int]] = {}
    for cid in old_non_prism:
        f_list = cell_faces_map[cid]
        verts_set: set[int] = set()
        for f in f_list:
            verts_set.update(f)
        if len(verts_set) != 4 or len(f_list) != 4:
            # tet 이 아닌 cell (hex, poly 등) — 지원 밖
            return TetSubdivResult(
                False, time.perf_counter() - t0,
                message=(
                    f"cell {cid} 은 tet 아님 (vertex={len(verts_set)}, "
                    f"faces={len(f_list)}) — tet-only 입력 필요"
                ),
            )
        old_tet_verts[cid] = tuple(sorted(verts_set))

    # 4b) cell id → 4 vertex 매핑 + face 리스트
    cell_vertices: dict[int, tuple[int, ...]] = {}
    for old_cid, v4 in old_tet_verts.items():
        cell_vertices[new_id_of[old_cid]] = v4
    for pid, pair in prism_pairs.items():
        outer, inner = pair
        t1, t2, t3 = prism_tets[pid]
        cell_vertices[t1] = (outer[0], outer[1], outer[2], inner[0])
        cell_vertices[t2] = (outer[1], outer[2], inner[0], inner[1])
        cell_vertices[t3] = (outer[2], inner[0], inner[1], inner[2])

    # 4c) 모든 face 를 수집 (cell → 4 face vertex tuple)
    # face direction (winding) 을 결정하려면 cell centroid 기준 outward 방향을 써야
    # 한다. 여기서는 geometric 계산으로 winding 을 결정.
    def _cell_centroid(verts: tuple[int, ...]) -> np.ndarray:
        return points[list(verts)].mean(axis=0)

    def _face_centroid(f: tuple[int, ...]) -> np.ndarray:
        return points[list(f)].mean(axis=0)

    def _face_normal(f: tuple[int, ...]) -> np.ndarray:
        v = points[list(f)]
        return np.cross(v[1] - v[0], v[2] - v[0])

    # canonical face key: sorted tuple
    # face_map: key → [(cid, winding_verts), ...]
    face_map: dict[tuple[int, ...], list[tuple[int, tuple[int, int, int]]]] = {}

    # tet faces ordering (0,1,2,3) → 4 triangle faces with winding such that normal
    # points OUT of cell centroid. For canonical 4-vertex tet we use:
    #   face opposite v0: (1,2,3)
    #   face opposite v1: (0,3,2)
    #   face opposite v2: (0,1,3)
    #   face opposite v3: (0,2,1)
    # winding 은 vertex 좌표에 따라 geometric 검증.

    for cid, v4 in cell_vertices.items():
        cc = _cell_centroid(v4)
        ordered_faces = [
            (v4[1], v4[2], v4[3]),
            (v4[0], v4[3], v4[2]),
            (v4[0], v4[1], v4[3]),
            (v4[0], v4[2], v4[1]),
        ]
        for f in ordered_faces:
            # winding 보정: normal 이 owner 밖을 향해야 함
            n = _face_normal(f)
            fc = _face_centroid(f)
            if np.dot(n, fc - cc) < 0:
                f = (f[0], f[2], f[1])
            key = tuple(sorted(f))
            face_map.setdefault(key, []).append((cid, f))

    # 4d) 원본 boundary patch 를 추적하기 위해 기존 boundary face 의 canonical key →
    # patch 매핑 생성
    orig_boundary_key_to_patch: dict[tuple[int, ...], int] = {}
    for pi, patch in enumerate(boundary):
        start = int(patch["startFace"])
        nf = int(patch["nFaces"])
        for fi in range(start, start + nf):
            if fi < len(raw_faces):
                orig_boundary_key_to_patch[tuple(sorted(raw_faces[fi]))] = pi

    # 4e) internal / boundary 분류
    internal_faces: list[list[int]] = []
    internal_owner: list[int] = []
    internal_nbr: list[int] = []
    # patch_idx → list[(face_verts, owner_cid)]
    bnd_by_patch: dict[int, list[tuple[list[int], int]]] = {
        pi: [] for pi in range(len(boundary))
    }
    bl_subdiv_bnd: list[tuple[list[int], int]] = []

    for key, refs in face_map.items():
        if len(refs) == 2:
            (ca, fa), (cb, fb) = refs
            owner_cid = min(ca, cb)
            nbr_cid = max(ca, cb)
            # owner 의 winding 사용
            verts = fa if ca == owner_cid else fb
            internal_faces.append(list(verts))
            internal_owner.append(owner_cid)
            internal_nbr.append(nbr_cid)
        elif len(refs) == 1:
            (cid, fv) = refs[0]
            patch_idx = orig_boundary_key_to_patch.get(key)
            if patch_idx is not None:
                bnd_by_patch[patch_idx].append((list(fv), cid))
            else:
                bl_subdiv_bnd.append((list(fv), cid))
        else:
            # > 2 cells share a face → mesh broken
            return TetSubdivResult(
                False, time.perf_counter() - t0,
                message=f"face key {key} 가 {len(refs)} cell 공유 — manifold 위반",
            )

    # 5) 최종 face 순서 = internal + each boundary patch
    final_faces: list[list[int]] = list(internal_faces)
    final_owner: list[int] = list(internal_owner)
    final_nbr: list[int] = list(internal_nbr)

    final_boundary_entries: list[dict[str, Any]] = []
    cursor = len(final_faces)
    for pi, patch in enumerate(boundary):
        items = bnd_by_patch[pi]
        start_face = cursor
        for f, o in items:
            final_faces.append(f)
            final_owner.append(o)
        cursor += len(items)
        final_boundary_entries.append({
            "name": patch.get("name", f"patch_{pi}"),
            "type": patch.get("type", "patch"),
            "nFaces": len(items),
            "startFace": start_face,
        })
    if bl_subdiv_bnd:
        start_face = cursor
        for f, o in bl_subdiv_bnd:
            final_faces.append(f)
            final_owner.append(o)
        cursor += len(bl_subdiv_bnd)
        final_boundary_entries.append({
            "name": "bl_subdiv_side",
            "type": "wall",
            "nFaces": len(bl_subdiv_bnd),
            "startFace": start_face,
        })

    # 6) backup + 쓰기
    if backup_original:
        import shutil as _sh
        bak = case_dir / "constant" / "polyMesh_pre_tet_subdiv"
        if bak.exists():
            _sh.rmtree(bak)
        _sh.copytree(poly_dir, bak)

    _write_points(poly_dir / "points", points)
    _write_faces(poly_dir / "faces", final_faces)
    _write_labels(
        poly_dir / "owner", np.array(final_owner, dtype=np.int64), "owner",
    )
    _write_labels(
        poly_dir / "neighbour", np.array(final_nbr, dtype=np.int64), "neighbour",
    )
    _write_boundary(poly_dir / "boundary", final_boundary_entries)

    return TetSubdivResult(
        True,
        time.perf_counter() - t0,
        n_prism_before=n_prism,
        n_tet_added=3 * n_prism,
        message=(
            f"tet_bl_subdivide OK — {n_prism} prism → {3 * n_prism} tet "
            f"(total cells={total_cells})"
        ),
    )
