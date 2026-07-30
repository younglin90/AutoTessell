"""OpenFOAM polyMesh writer.

Converts numpy mesh arrays into the five files that OpenFOAM expects under
``constant/polyMesh/``:
    points, faces, owner, neighbour, boundary

두 경로 제공:
    - ``write_generic_polymesh``: **primary** — 임의 cell (tet/hex/poly 공용) writer.
      호출 측이 각 cell 의 외향 face vertex list 를 넘기면 face dedup + owner/
      neighbour 정렬 + FoamFile 쓰기 (via native_bl helpers) 수행. beta12+.
    - ``PolyMeshWriter``: tet 전용 thin wrapper (하위 호환). tet winding 정규화 +
      tet solver 용 상세 system/ 파일 생성까지 포함.

beta18 에서 PolyMeshWriter 내부의 file-writer staticmethod (``_write_points`` /
``_write_faces`` / ``_write_owner`` / ``_write_neighbour`` / ``_write_boundary``)
와 ``_FaceRecord`` / ``_canonical`` 헬퍼는 dead code 로 제거됨 — 모두 native_bl
의 공용 writer 가 generic 경로에서 사용된다.

No external tools (OpenFOAM, meshio) are required.
"""

from __future__ import annotations

import os
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from core.utils.logging import get_logger
from core.utils.native_extensions import import_native_extension

logger = get_logger(__name__)

_NATIVE_POLYMESH: Any | None = None
_NATIVE_POLYMESH_IMPORT_ATTEMPTED = False


def _load_native_polymesh() -> Any | None:
    """Load the optional writer topology kernel."""
    global _NATIVE_POLYMESH, _NATIVE_POLYMESH_IMPORT_ATTEMPTED
    if _NATIVE_POLYMESH_IMPORT_ATTEMPTED:
        return _NATIVE_POLYMESH
    _NATIVE_POLYMESH_IMPORT_ATTEMPTED = True

    try:
        _NATIVE_POLYMESH = import_native_extension("native_polymesh")
    except Exception:  # noqa: BLE001
        _NATIVE_POLYMESH = None
    return _NATIVE_POLYMESH


# ---------------------------------------------------------------------------
# PMW1 — coplanar internal-face merge
# ---------------------------------------------------------------------------
_PMW1_OFF = os.environ.get("AUTO_TESSELL_PMW1_OFF", "").strip().lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# PMW2 — automatic boundary patch labeling by feature dihedral
# ---------------------------------------------------------------------------
_PMW2_OFF = os.environ.get("AUTO_TESSELL_PMW2_OFF", "").strip().lower() in ("1", "true", "yes")


def _segment_boundary_by_features(
    all_faces: list[list[int]],
    pts: np.ndarray,
    n_internal: int,
    *,
    dihedral_deg: float = 30.0,
) -> list[tuple[str, list[int]]]:
    """BFS flood-fill boundary patches separated by feature dihedral angle.

    Boundary faces are those at indices n_internal..len(all_faces)-1.
    Adjacent boundary faces (sharing an edge) with dihedral < dihedral_deg
    are grouped into the same patch.

    Returns list of (patch_name, [absolute_face_indices]) sorted by first index.
    Naming: wall_0, wall_1, ... (wall_0 is the largest group).
    """
    n_bnd = len(all_faces) - n_internal
    if n_bnd <= 0:
        return []

    cos_tol = np.cos(np.radians(dihedral_deg))

    # Precompute normals for boundary faces
    bnd_normals: list[np.ndarray] = []
    for fi in range(n_internal, len(all_faces)):
        bnd_normals.append(_face_normal(all_faces[fi], pts))

    # Build edge → boundary face local indices adjacency
    # edge key: frozenset of two vertex indices (undirected)
    edge_to_bfaces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for li in range(n_bnd):
        verts = all_faces[n_internal + li]
        nv = len(verts)
        for k in range(nv):
            u, v = verts[k], verts[(k + 1) % nv]
            edge_key = (min(u, v), max(u, v))
            edge_to_bfaces[edge_key].append(li)

    # Build adjacency list (local indices within boundary faces)
    adj: list[list[int]] = [[] for _ in range(n_bnd)]
    for edge_key, bfaces in edge_to_bfaces.items():
        if len(bfaces) == 2:
            la, lb = bfaces[0], bfaces[1]
            dot = float(np.dot(bnd_normals[la], bnd_normals[lb]))
            # same patch if normals nearly parallel (small dihedral = close to 180 face angle)
            if dot > cos_tol:
                adj[la].append(lb)
                adj[lb].append(la)

    # BFS flood-fill
    visited = [False] * n_bnd
    groups: list[list[int]] = []
    for start in range(n_bnd):
        if visited[start]:
            continue
        group: list[int] = []
        q: deque[int] = deque([start])
        visited[start] = True
        while q:
            li = q.popleft()
            group.append(li)
            for nb in adj[li]:
                if not visited[nb]:
                    visited[nb] = True
                    q.append(nb)
        groups.append(group)

    # Sort groups by first absolute face index
    groups.sort(key=lambda g: n_internal + min(g))

    # C-PERF-5 / beta2393 — patch count cap (perf + ergonomics).
    # validator 발견: hard mesh 의 fragmented patches (n_patches=2187) 가
    # boundary 작성 시간 + CFD setup 부담. AUTO_TESSELL_PATCH_CAP env (default
    # 64) 초과 시 작은 patches 들을 'wall_misc' 단일 patch 로 병합.
    import os as _os_pwc

    _patch_cap = int(_os_pwc.environ.get("AUTO_TESSELL_PATCH_CAP", "64"))
    patches: list[tuple[str, list[int]]] = []
    if len(groups) > _patch_cap:
        # 큰 patch 부터 _patch_cap-1 개까지 분리, 나머지는 wall_misc 로 합병.
        groups_by_size = sorted(groups, key=lambda g: -len(g))
        kept = groups_by_size[: _patch_cap - 1]
        merged_misc: list[int] = [
            n_internal + li for g in groups_by_size[_patch_cap - 1 :] for li in g
        ]
        # restore stable ordering of kept by first abs idx.
        kept.sort(key=lambda g: n_internal + min(g))
        for idx, group in enumerate(kept):
            abs_indices = [n_internal + li for li in group]
            patches.append((f"wall_{idx}", abs_indices))
        if merged_misc:
            patches.append(("wall_misc", merged_misc))
        logger.info(
            "polymesh_writer_patches_capped",
            n_boundary_faces=n_bnd,
            n_groups=len(groups),
            n_kept=len(kept),
            n_misc=len(merged_misc),
            cap=_patch_cap,
        )
    else:
        for idx, group in enumerate(groups):
            abs_indices = [n_internal + li for li in group]
            patches.append((f"wall_{idx}", abs_indices))

    logger.info(
        "polymesh_writer_patches",
        n_boundary_faces=n_bnd,
        n_patches=len(patches),
        patch_sizes=[len(p[1]) for p in patches],
    )
    return patches


def _face_normal(verts: list[int], pts: np.ndarray) -> np.ndarray:
    """Newell normal for polygon (robust for n-gons)."""
    n = np.zeros(3, dtype=np.float64)
    nv = len(verts)
    for i in range(nv):
        a = pts[verts[i]]
        b = pts[verts[(i + 1) % nv]]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    norm = np.linalg.norm(n)
    if norm < 1e-30:
        return n
    return n / norm


def _merge_two_faces(fa: list[int], fb: list[int]) -> list[int] | None:
    """Merge two polygons sharing exactly one edge into one polygon.

    Returns the merged vertex loop or None if they don't share a suitable edge.
    The shared edge must appear in opposite orientations (fa: u→v, fb: v→u).
    """
    # Build edge sets for fast lookup
    edges_b: dict[tuple[int, int], int] = {}
    nb = len(fb)
    for i in range(nb):
        u, v = fb[i], fb[(i + 1) % nb]
        edges_b[(u, v)] = i

    na = len(fa)
    for ia in range(na):
        u, v = fa[ia], fa[(ia + 1) % na]
        # Shared edge in fb must appear reversed: (v, u)
        if (v, u) in edges_b:
            ib = edges_b[(v, u)]
            # Build merged polygon:
            # fa: ..., fa[ia], (shared u), fa[ia+1], ...
            # fb: ..., fb[ib+1], ... (skip shared v→u edge)
            merged: list[int] = []
            # Add all of fa except the edge u→v (skip v = fa[(ia+1)%na])
            for k in range(na - 1):
                merged.append(fa[(ia + 1 + k) % na])
            # Add all of fb except the reverse edge v→u (skip u = fb[ib])
            for k in range(nb - 1):
                merged.append(fb[(ib + 1 + k) % nb])
            # Remove consecutive duplicates
            result: list[int] = []
            for vtx in merged:
                if not result or result[-1] != vtx:
                    result.append(vtx)
            if result and result[0] == result[-1]:
                result.pop()
            if len(result) < 3:
                return None
            return result
    return None


def _merge_coplanar_faces(
    faces: list[list[int]],
    owner: list[int],
    neighbour: list[int],
    pts: np.ndarray,
    *,
    normal_tol_deg: float = 2.0,
) -> tuple[list[list[int]], list[int], list[int]]:
    """Merge coplanar internal faces sharing an edge within the same (owner, neighbour) pair.

    Only touches internal faces (those with a neighbour). Boundary faces (appended
    after) are not passed to this function.

    Returns updated (faces, owner, neighbour) lists (same length or shorter).
    """
    cos_tol = np.cos(np.radians(normal_tol_deg))
    n_int = len(owner)  # == len(neighbour) == number of internal faces

    # Group internal faces by (owner, neighbour) cell pair
    pair_groups: dict[tuple[int, int], list[int]] = defaultdict(list)
    for fi in range(n_int):
        pair_groups[(owner[fi], neighbour[fi])].append(fi)

    keep: list[bool] = [True] * n_int
    merged_faces: dict[int, list[int]] = {}  # fi → new face verts (replaces faces[fi])

    for (ow, nb_), fi_list in pair_groups.items():
        if len(fi_list) < 2:
            continue
        # Compute normals once
        normals = {fi: _face_normal(faces[fi], pts) for fi in fi_list}
        # Greedy merge: try to merge pairs with similar normals
        changed = True
        active = list(fi_list)
        # We work on a local list; merged faces replace index of first face
        local_faces: dict[int, list[int]] = {fi: list(faces[fi]) for fi in active}
        local_normals: dict[int, np.ndarray] = {fi: normals[fi] for fi in active}

        while changed:
            changed = False
            for i in range(len(active)):
                fi = active[i]
                if not keep[fi]:
                    continue
                for j in range(i + 1, len(active)):
                    fj = active[j]
                    if not keep[fj]:
                        continue
                    ni = local_normals[fi]
                    nj = local_normals[fj]
                    dot = float(np.dot(ni, nj))
                    if dot < cos_tol:
                        continue
                    merged = _merge_two_faces(local_faces[fi], local_faces[fj])
                    if merged is None:
                        continue
                    # Accept merge: fi absorbs fj
                    local_faces[fi] = merged
                    local_normals[fi] = _face_normal(merged, pts)
                    keep[fj] = False
                    merged_faces[fi] = merged
                    changed = True
                    break
                if changed:
                    break

    # Rebuild output lists
    out_faces: list[list[int]] = []
    out_owner: list[int] = []
    out_nbr: list[int] = []
    for fi in range(n_int):
        if not keep[fi]:
            continue
        out_faces.append(merged_faces.get(fi, faces[fi]))
        out_owner.append(owner[fi])
        out_nbr.append(neighbour[fi])
    return out_faces, out_owner, out_nbr


# FoamFile header template
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
    class       {foam_class};
    location    "{location}";
    object      {object_name};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

"""

_FOOTER = "\n// ************************************************************************* //\n"


def _header(foam_class: str, location: str, object_name: str) -> str:
    return _FOAM_HEADER.format(
        foam_class=foam_class,
        location=location,
        object_name=object_name,
    )


# Each tet has 4 faces; the local vertex indices for each face follow
# OpenFOAM right-hand rule so the face normal points *outward* from the tet.
# For a tet with vertices (0,1,2,3) the outward-facing triangles are:
#   face 0: opposite vertex 3  → (0, 2, 1)
#   face 1: opposite vertex 2  → (0, 1, 3)
#   face 2: opposite vertex 1  → (0, 3, 2)
#   face 3: opposite vertex 0  → (1, 2, 3)
_TET_FACES: tuple[tuple[int, int, int], ...] = (
    (0, 2, 1),
    (0, 1, 3),
    (0, 3, 2),
    (1, 2, 3),
)


def _normalize_tet_winding(vertices: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """Return a copy of *tets* where every tetrahedron has positive volume.

    The signed volume of a tet (a, b, c, d) is::

        V = dot(b-a, cross(c-a, d-a)) / 6

    If V < 0 the vertex ordering is "left-handed" (the ``_TET_FACES`` outward
    convention will produce inward normals).  We fix this by swapping the first
    two vertex indices so the tet becomes right-handed.  Swapping any two
    indices negates the volume, so the resulting tet has V > 0.
    """
    tets = tets.copy()
    a = vertices[tets[:, 0]]
    b = vertices[tets[:, 1]]
    c = vertices[tets[:, 2]]
    d = vertices[tets[:, 3]]
    # signed volume (without /6 — only the sign matters)
    ab = b - a
    ac = c - a
    ad = d - a
    signed_vol = np.einsum("ij,ij->i", ab, np.cross(ac, ad))
    negative = signed_vol < 0
    n_flipped = int(negative.sum())
    if n_flipped:
        logger.debug(
            "normalize_tet_winding",
            n_negative=n_flipped,
            n_total=len(tets),
        )
        # Swap indices 0 and 1 on negative tets to flip the sign
        tets[negative, 0], tets[negative, 1] = (
            tets[negative, 1].copy(),
            tets[negative, 0].copy(),
        )
    return tets


def write_generic_polymesh(
    vertices: np.ndarray,
    cell_faces: Sequence[Sequence[Sequence[int]]],
    case_dir: Path,
    *,
    patch_name: str = "defaultWall",
    patch_type: str = "wall",
    boundary_patch_classifier: (
        Callable[[list[int], np.ndarray], str | tuple[str, str] | None] | None
    ) = None,
    strict: bool = False,
) -> dict[str, int]:
    """Generic polyMesh writer — cell → list of face vertex lists.

    Args:
        vertices: (N, 3) float 좌표 배열.
        cell_faces: ``cell_faces[i]`` = cell i 를 구성하는 face 목록. 각 face 는
            vertex index 시퀀스 (길이 가변: 삼각형 3, 사각형 4, n-gon n).
            **각 face 는 소유 cell 외향 (CCW from outside) 으로 기록되어야 한다.**
        case_dir: 결과 case 디렉터리 — ``constant/polyMesh/`` 하위에 쓰기.
        patch_name / patch_type: 단일 boundary patch 설정 (기본 defaultWall/wall).
        strict: reject any cell/face loss or non-manifold face before writing.

    Returns:
        ``{num_cells, num_points, num_faces, num_internal_faces}``.

    Algorithm:
        1. canonical key = tuple(sorted(face_verts)) 로 face dedup.
        2. 공유 2 cells → internal, 1 cell → boundary.
        3. internal face 의 orientation 은 owner cell 측 기록 그대로 사용 (owner
           외향 = owner→neighbour normal).
        4. internal sort by (owner, neighbour); boundary sort by owner.
        5. points/faces/owner/neighbour/boundary 파일 + 최소 system/ 쓰기.

    Non-manifold (3+ cells 공유) face 는 기본 모드에서 첫 2 cell 을 internal 로
    선택하고 나머지는 무시한다 (경고 로그 포함). ``strict=True`` 는 이를 쓰기
    전에 거부한다.
    """
    # Lazy imports — 순환 import 회피
    from core.generator.tier_layers_post import (  # noqa: PLC0415
        _ensure_minimal_controldict,
        _write_minimal_fv_dicts,
    )
    from core.layers.native_bl import (  # noqa: PLC0415
        _write_boundary,
        _write_faces,
        _write_labels,
        _write_points,
    )

    vertices_arr = np.asarray(vertices, dtype=np.float64)
    n_cells_in = len(cell_faces)
    bbox_diag = (
        float(np.linalg.norm(vertices_arr.max(axis=0) - vertices_arr.min(axis=0)))
        if len(vertices_arr)
        else 0.0
    )
    area_eps = max((bbox_diag * 1e-12) ** 2, 1e-30)

    native_used = False
    non_manifold_faces: list[tuple[int, int]] = []
    native_polymesh = _load_native_polymesh()
    if native_polymesh is not None:
        try:
            (
                internal_faces,
                internal_owner,
                internal_nbr,
                boundary_faces,
                boundary_owner,
                n_cells_out,
                n_cells_dropped,
                n_faces_dropped,
                non_manifold_faces,
            ) = native_polymesh.build_topology(vertices_arr, cell_faces, area_eps)
        except Exception:  # noqa: BLE001
            pass
        else:
            native_used = True

    if not native_used:

        def _clean_face_for_write(face: Sequence[int]) -> list[int] | None:
            cleaned: list[int] = []
            seen: set[int] = set()
            for raw_v in face:
                v = int(raw_v)
                if cleaned and cleaned[-1] == v:
                    continue
                if v in seen:
                    continue
                cleaned.append(v)
                seen.add(v)
            if len(cleaned) >= 2 and cleaned[-1] == cleaned[0]:
                cleaned.pop()
            if len(cleaned) < 3:
                return None
            pts = vertices_arr[np.asarray(cleaned, dtype=np.int64)]
            base = pts[0]
            area = 0.0
            for i in range(1, len(cleaned) - 1):
                area += 0.5 * float(
                    np.linalg.norm(
                        np.cross(
                            pts[i] - base,
                            pts[i + 1] - base,
                        )
                    )
                )
            if area <= area_eps:
                return None
            return cleaned

        cleaned_cells: list[list[list[int]]] = []
        n_cells_dropped = 0
        n_faces_dropped = 0
        for faces_of_cell in cell_faces:
            out_faces: list[list[int]] = []
            drop_cell = False
            for f in faces_of_cell:
                cf = _clean_face_for_write(f)
                if cf is None:
                    drop_cell = True
                    n_faces_dropped += 1
                    break
                out_faces.append(cf)
            if drop_cell or len(out_faces) < 4:
                n_cells_dropped += 1
                continue
            cleaned_cells.append(out_faces)
        if n_cells_dropped or n_faces_dropped:
            logger.info(
                "generic_polymesh_degenerate_cells_dropped",
                n_cells_in=len(cell_faces),
                n_cells_out=len(cleaned_cells),
                n_cells_dropped=int(n_cells_dropped),
                n_faces_dropped=int(n_faces_dropped),
            )
        cell_faces = cleaned_cells
        n_cells_out = len(cell_faces)
    else:
        n_cells_out = int(n_cells_out)
        if n_cells_dropped or n_faces_dropped:
            logger.info(
                "generic_polymesh_degenerate_cells_dropped",
                n_cells_in=len(cell_faces),
                n_cells_out=n_cells_out,
                n_cells_dropped=int(n_cells_dropped),
                n_faces_dropped=int(n_faces_dropped),
            )
        for n_refs, key_len in non_manifold_faces:
            logger.warning(
                "generic_polymesh_non_manifold_face",
                n_refs=int(n_refs),
                key_len=int(key_len),
            )

    if strict and (n_cells_dropped or n_faces_dropped):
        raise ValueError(
            "strict polyMesh contract rejected silent topology loss: "
            f"cells_in={n_cells_in}, "
            f"cells_out={n_cells_out}, cells_dropped={int(n_cells_dropped)}, "
            f"faces_dropped={int(n_faces_dropped)}"
        )
    if strict and native_used and non_manifold_faces:
        raise ValueError(
            "strict polyMesh contract rejected non-manifold face references: "
            f"count={len(non_manifold_faces)}"
        )

    if not native_used:
        # face_map: canonical key → [(cell_id, ordered_verts), ...]
        face_map: dict[tuple[int, ...], list[tuple[int, list[int]]]] = defaultdict(list)
        for ci, faces_of_cell in enumerate(cell_faces):
            for f in faces_of_cell:
                verts = [int(v) for v in f]
                key = tuple(sorted(verts))
                face_map[key].append((ci, verts))

        internal_faces = []
        internal_owner = []
        internal_nbr = []
        boundary_faces = []
        boundary_owner = []

        for key, refs in face_map.items():
            n_refs = len(refs)
            if n_refs == 2:
                (ca, fa), (cb, fb) = refs
            elif n_refs == 1:
                ci, fv = refs[0]
                boundary_faces.append(fv)
                boundary_owner.append(ci)
                continue
            else:
                # non-manifold: 첫 2 cell 만 internal 로 사용, 나머지 무시.
                non_manifold_faces.append((n_refs, len(key)))
                logger.warning(
                    "generic_polymesh_non_manifold_face",
                    n_refs=n_refs,
                    key_len=len(key),
                )
                (ca, fa), (cb, fb) = refs[0], refs[1]

            owner_c = min(ca, cb)
            nbr_c = max(ca, cb)
            f_use = fa if ca == owner_c else fb
            internal_faces.append(f_use)
            internal_owner.append(owner_c)
            internal_nbr.append(nbr_c)

    if strict and non_manifold_faces:
        raise ValueError(
            "strict polyMesh contract rejected non-manifold face references: "
            f"count={len(non_manifold_faces)}"
        )

    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True, exist_ok=True)
    _ensure_minimal_controldict(case_dir)
    _write_minimal_fv_dicts(case_dir)

    # Vectorized sort: np.lexsort on owner/neighbour arrays (secondary key first)
    _int_owner_arr = np.array(internal_owner, dtype=np.int64)
    _int_nbr_arr = np.array(internal_nbr, dtype=np.int64)
    int_order = np.lexsort((_int_nbr_arr, _int_owner_arr)).tolist() if len(internal_owner) else []

    _bnd_owner_arr = np.array(boundary_owner, dtype=np.int64)
    bnd_order = np.argsort(_bnd_owner_arr, kind="stable").tolist() if len(boundary_owner) else []

    # PMW1 — coplanar internal-face merge (before write)
    sorted_int_faces = [internal_faces[i] for i in int_order]
    sorted_int_owner = _int_owner_arr[int_order].tolist() if int_order else []
    sorted_int_nbr = _int_nbr_arr[int_order].tolist() if int_order else []

    _n_int_before = len(sorted_int_faces)
    if not _PMW1_OFF and _n_int_before >= 100:
        sorted_int_faces, sorted_int_owner, sorted_int_nbr = _merge_coplanar_faces(
            sorted_int_faces, sorted_int_owner, sorted_int_nbr, vertices_arr
        )
        _n_int_after = len(sorted_int_faces)
        logger.info(
            "polymesh_writer_face_merge",
            before=_n_int_before,
            after=_n_int_after,
            reduced=_n_int_before - _n_int_after,
        )

    n_internal = len(sorted_int_faces)
    sorted_bnd_faces = [boundary_faces[i] for i in bnd_order]
    sorted_bnd_owner = [boundary_owner[i] for i in bnd_order]
    final_faces = sorted_int_faces + sorted_bnd_faces
    final_owner = sorted_int_owner + sorted_bnd_owner
    final_nbr = sorted_int_nbr

    # PMW2 — auto boundary patch segmentation by feature dihedral.
    # 패치 그룹화 결과는 BFS 순서로 face index 가 scattered. OpenFOAM polyMesh 는
    # patch[i].startFace + nFaces == patch[i+1].startFace 의 contiguous 제약이
    # 있으므로, 그룹화 후 boundary 영역을 patch 별로 재정렬해야 한다.
    n_bnd = len(final_faces) - n_internal
    _pmw2_active = not _PMW2_OFF and n_bnd > 100
    boundary_entries: list[dict[str, Any]]
    if boundary_patch_classifier is not None and n_bnd > 0:
        classifications: list[Any] | None = None
        classify_many = getattr(boundary_patch_classifier, "classify_many", None)
        if callable(classify_many):
            try:
                batch_result = list(classify_many(sorted_bnd_faces, vertices_arr))
                if len(batch_result) != len(sorted_bnd_faces):
                    raise ValueError(
                        "batch classifier returned "
                        f"{len(batch_result)} labels for "
                        f"{len(sorted_bnd_faces)} boundary faces"
                    )
                classifications = batch_result
            except Exception as exc:
                logger.debug(
                    "polymesh_writer_batch_patch_classifier_failed",
                    error=str(exc)[:120],
                )

        if classifications is None:
            classifications = []
            for rel_idx, face in enumerate(sorted_bnd_faces):
                try:
                    cls = boundary_patch_classifier(face, vertices_arr)
                except Exception as exc:
                    logger.debug(
                        "polymesh_writer_patch_classifier_failed",
                        rel_face=rel_idx,
                        error=str(exc)[:120],
                    )
                    cls = None
                classifications.append(cls)

        patch_groups: dict[tuple[str, str], list[int]] = {}
        for rel_idx, cls in enumerate(classifications):
            if isinstance(cls, tuple):
                pname = str(cls[0] or patch_name)
                ptype = str(cls[1] or patch_type)
            elif isinstance(cls, str) and cls:
                pname = cls
                ptype = patch_type
            else:
                pname = patch_name
                ptype = patch_type
            patch_groups.setdefault((pname, ptype), []).append(rel_idx)

        new_bnd_faces = []
        new_bnd_owner = []
        boundary_entries = []
        cursor = n_internal
        for (pname, ptype), rel_indices in patch_groups.items():
            start = cursor
            for rel in rel_indices:
                new_bnd_faces.append(sorted_bnd_faces[rel])
                new_bnd_owner.append(sorted_bnd_owner[rel])
            cursor += len(rel_indices)
            boundary_entries.append(
                {
                    "name": pname,
                    "type": ptype,
                    "nFaces": len(rel_indices),
                    "startFace": start,
                }
            )
        final_faces = sorted_int_faces + new_bnd_faces
        final_owner = sorted_int_owner + new_bnd_owner
        logger.info(
            "polymesh_writer_patch_classifier",
            n_boundary_faces=n_bnd,
            patches=[
                {"name": e["name"], "type": e["type"], "nFaces": e["nFaces"]}
                for e in boundary_entries
            ],
        )
    elif _pmw2_active:
        patches = _segment_boundary_by_features(
            final_faces, vertices_arr, n_internal, dihedral_deg=30.0
        )
        if len(patches) > 1:
            # BETA2881 — patch 별 face indices 를 contiguous 위치로 재배치.
            # 기존 코드는 startFace=pidxs[0] 만 기록했고 face 자체는 그대로 두어
            # PyVista/OpenFOAMReader 가 "inconsistent start face" 로 거부.
            new_bnd_faces: list[list[int]] = []
            new_bnd_owner: list[int] = []
            new_bnd_starts: list[int] = []
            cursor = n_internal
            for _pname, pidxs in patches:
                new_bnd_starts.append(cursor)
                for abs_fi in pidxs:
                    rel = abs_fi - n_internal
                    new_bnd_faces.append(sorted_bnd_faces[rel])
                    new_bnd_owner.append(sorted_bnd_owner[rel])
                cursor += len(pidxs)
            # 재정렬된 boundary 적용.
            final_faces = sorted_int_faces + new_bnd_faces
            final_owner = sorted_int_owner + new_bnd_owner
            boundary_entries = [
                {
                    "name": pname,
                    "type": patch_type,
                    "nFaces": len(pidxs),
                    "startFace": st,
                }
                for (pname, pidxs), st in zip(patches, new_bnd_starts)
            ]
        else:
            boundary_entries = [
                {"name": patch_name, "type": patch_type, "nFaces": n_bnd, "startFace": n_internal}
            ]
    else:
        boundary_entries = [
            {"name": patch_name, "type": patch_type, "nFaces": n_bnd, "startFace": n_internal}
        ]

    n_faces = len(final_faces)
    owner_note = (
        f"nPoints:{int(vertices_arr.shape[0])}  nCells:{n_cells_out}  "
        f"nFaces:{n_faces}  nInternalFaces:{n_internal}"
    )

    _write_points(poly_dir / "points", vertices_arr)
    _write_faces(poly_dir / "faces", final_faces)
    _write_labels(
        poly_dir / "owner",
        np.array(final_owner, dtype=np.int64),
        "owner",
        note=owner_note,
    )
    _write_labels(
        poly_dir / "neighbour",
        np.array(final_nbr, dtype=np.int64),
        "neighbour",
    )
    _write_boundary(poly_dir / "boundary", boundary_entries)

    return {
        "num_cells": n_cells_out,
        "num_points": int(vertices_arr.shape[0]),
        "num_faces": len(final_faces),
        "num_internal_faces": n_internal,
    }


class PolyMeshWriter:
    """Tet polyMesh writer — ``write_generic_polymesh`` 의 얇은 wrapper.

    v0.4.0-beta12 부터 실제 face dedup / owner-neighbour 정렬 / FoamFile 쓰기는
    공용 ``write_generic_polymesh`` 로 위임. 이 wrapper 가 추가로 하는 것:

    1. ``_normalize_tet_winding`` — 음수 부피 tet 을 swap 으로 right-handed 화.
       외부 tool (pytetwild / Netgen 등) 출력의 inconsistent winding 을 보정.
    2. ``_TET_FACES`` 외향 convention 에 맞춰 각 tet cell 의 4 개 triangle face
       (cell → list of face vertex lists) 를 만들어 generic writer 에 전달.
    3. ``_ensure_system_files`` — tet solver 용 `system/{controlDict, fvSchemes,
       fvSolution}` (GAMG 등) 자동 생성. generic writer 의 "최소" 설정보다 상세.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(
        self,
        vertices: np.ndarray,
        tets: np.ndarray,
        case_dir: Path,
        *,
        boundary_patch_classifier: (
            Callable[[list[int], np.ndarray], str | tuple[str, str] | None] | None
        ) = None,
    ) -> dict[str, int]:
        """Write OpenFOAM polyMesh from tet mesh arrays.

        Parameters
        ----------
        vertices:
            Shape ``(N, 3)`` float array of point coordinates.
        tets:
            Shape ``(M, 4)`` int array of tet connectivity (zero-based).
        case_dir:
            OpenFOAM case directory.  The ``constant/polyMesh`` sub-directory
            is created automatically.

        Returns
        -------
        dict
            Keys: ``num_cells``, ``num_points``, ``num_faces``,
            ``num_internal_faces``.
        """
        vertices = np.asarray(vertices, dtype=np.float64)
        tets = np.asarray(tets, dtype=np.int64)

        # Step 0: normalise tet winding so all cells have positive volume.
        # Tets from external tools (pytetwild, Netgen …) may have inconsistent
        # vertex ordering; negative-volume tets cause inward face normals which
        # lead to checkMesh "incorrectly oriented" and "negative volume" errors.
        tets = _normalize_tet_winding(vertices, tets)

        logger.info(
            "polymesh_writer_start",
            num_points=len(vertices),
            num_cells=len(tets),
            case_dir=str(case_dir),
        )

        # Step 1: build cell_faces (각 cell 의 외향 face 4 개) — generic writer 위임.
        # Vectorized: build all 4*M triangle faces at once via numpy index selection.
        _tf = np.array(_TET_FACES, dtype=np.int64)  # (4, 3)
        # tets[:, _tf] → shape (M, 4, 3) — all face vertex indices in one op
        _all_face_verts: np.ndarray = tets[:, _tf]  # (M, 4, 3)
        # _all_face_verts.tolist() 가 이미 list[list[list[int]]] 반환.
        # 직전 vectorize 카드의 잔존 회귀 (row.tolist() — row 가 list 라 AttributeError).
        cell_faces: list[list[list[int]]] = _all_face_verts.tolist()

        # A tetrahedral output cannot represent a 3+-cell face in OpenFOAM's
        # owner/neighbour model.  Keep the generic writer permissive for its
        # existing poly/hex compatibility callers, but reject such input for
        # the native-tet contract before any polyMesh files are created.
        stats = write_generic_polymesh(
            vertices,
            cell_faces,
            case_dir,
            boundary_patch_classifier=boundary_patch_classifier,
            strict=True,
        )

        # Writer-specific system files (GAMG solver 등 tet 솔루션 설정) 덮어쓰기.
        # generic writer 의 최소 controlDict 는 generic 솔루션이므로, tet 전용
        # PolyMeshWriter 는 자체 고정 스펙을 유지해 하위 호환 보장.
        self._ensure_system_files(case_dir)

        logger.info("polymesh_writer_done", **stats)
        return stats

    # ------------------------------------------------------------------
    # System files (minimal, for checkMesh compatibility)
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_system_files(case_dir: Path) -> None:
        """Create minimal system/ files if they don't already exist."""
        system_dir = case_dir / "system"
        system_dir.mkdir(parents=True, exist_ok=True)

        control_dict = system_dir / "controlDict"
        if not control_dict.exists():
            control_dict.write_text(
                _header("dictionary", "system", "controlDict")
                + "application     simpleFoam;\n"
                + "startFrom       latestTime;\n"
                + "stopAt          endTime;\n"
                + "endTime         1000;\n"
                + "deltaT          1;\n"
                + "writeControl    timeStep;\n"
                + "writeInterval   100;\n"
                + _FOOTER
            )

        fv_schemes = system_dir / "fvSchemes"
        if not fv_schemes.exists():
            fv_schemes.write_text(
                _header("dictionary", "system", "fvSchemes")
                + "ddtSchemes { default steadyState; }\n"
                + "gradSchemes { default Gauss linear; }\n"
                + "divSchemes\n{\n"
                + "    default none;\n"
                + "    div(phi,U) bounded Gauss linearUpwind grad(U);\n"
                + "    div(phi,k) bounded Gauss upwind;\n"
                + "    div(phi,omega) bounded Gauss upwind;\n"
                + '    "div((nuEff*dev2(T(grad(U)))))" Gauss linear;\n'
                + "}\n"
                + "laplacianSchemes { default Gauss linear corrected; }\n"
                + "interpolationSchemes { default linear; }\n"
                + "snGradSchemes { default corrected; }\n"
                + "wallDist { method meshWave; }\n"
                + _FOOTER
            )

        fv_solution = system_dir / "fvSolution"
        if not fv_solution.exists():
            fv_solution.write_text(
                _header("dictionary", "system", "fvSolution")
                + "solvers\n{\n"
                + "    p { solver GAMG; smoother GaussSeidel; tolerance 1e-06; relTol 0.1; }\n"
                + "    U { solver smoothSolver; smoother GaussSeidel; "
                + "tolerance 1e-06; relTol 0.1; }\n"
                + "    k { solver smoothSolver; smoother GaussSeidel; "
                + "tolerance 1e-06; relTol 0.1; }\n"
                + "    omega { solver smoothSolver; smoother GaussSeidel; "
                + "tolerance 1e-06; relTol 0.1; }\n"
                + "}\n\n"
                + "SIMPLE\n{\n"
                + "    nNonOrthogonalCorrectors 1;\n"
                + "    consistent yes;\n"
                + "    pRefCell 0;\n"
                + "    pRefValue 0;\n"
                + "}\n\n"
                + "relaxationFactors\n{\n"
                + "    fields { p 0.3; }\n"
                + "    equations { U 0.7; k 0.7; omega 0.7; }\n"
                + "}\n"
                + _FOOTER
            )
