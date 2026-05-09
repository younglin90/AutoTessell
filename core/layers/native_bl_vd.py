"""Vertex Duplication BL extrusion utilities.

Solves multi-patch junction skew problem documented in
.autoresearch/tet_bl_full/vd_refactor_plan.md.

Per-vertex extrusion (current native_bl) averages adjacent face normals → at
multi-patch junctions, avg_vnorm can be ~90° from any adjacent face_normal,
producing boundary skew = tan(θ) → 100s. Vertex duplication uses per-face
inner verts → cap on face_normal axis → boundary skew = 0 for each prism.

This module provides:
- detect_junction_verts: identify verts where face_normal divergence is high
- detect_junction_edges: identify wall edges across feature edges
- compute_face_normals: per-face outward normal (vectorized)

Future steps (VD-3..VD-8) will add:
- per-face inner vert generator
- prism cell topology with duplications
- gap-filling cells at junction edges
- faces/owner/neighbour rebuild
- multi-layer BL with dup support
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import os

import numpy as np


@dataclass
class JunctionInfo:
    """Result of junction detection.

    junction_verts: vertex ids where adjacent face_normals diverge
        (any pair of adj face normals has cos < cos_thresh).
    junction_edges: (v_min, v_max) tuples where the two adjacent faces'
        normals diverge above threshold.
    face_normals: per-face unit outward normal (face_id -> ndarray(3)).
    """

    junction_verts: set[int]
    junction_edges: set[tuple[int, int]]
    face_normals: dict[int, np.ndarray]


def compute_face_normals(
    faces: list[list[int]],
    points: np.ndarray,
    face_indices: list[int] | None = None,
) -> dict[int, np.ndarray]:
    """Per-face outward unit normal (cross of two edges from vertex 0).

    Faces with degenerate area (mag < 1e-30) get omitted from result.
    """
    out: dict[int, np.ndarray] = {}
    if face_indices is None:
        face_indices = list(range(len(faces)))
    for fi in face_indices:
        f = faces[fi]
        if len(f) < 3:
            continue
        p0 = points[f[0]]
        p1 = points[f[1]]
        p2 = points[f[2]]
        n_raw = np.cross(p1 - p0, p2 - p0)
        m = float(np.linalg.norm(n_raw))
        if m < 1e-30:
            continue
        out[fi] = n_raw / m
    return out


def detect_junction_verts(
    wall_face_indices: list[int],
    faces: list[list[int]],
    points: np.ndarray,
    *,
    cos_thresh: float = 0.9,
) -> JunctionInfo:
    """Find junction verts/edges across multi-patch wall surface.

    A junction vert v is one where any pair of adjacent wall face normals has
    cosine < cos_thresh (default 0.9 ≈ 25° divergence).

    A junction edge (v, w) is a wall edge whose two adjacent faces have
    normals with cosine < cos_thresh.

    Args:
        wall_face_indices: indices of wall faces in `faces`.
        faces: list of face vertex lists (polyMesh-style).
        points: (N, 3) vertex coordinates.
        cos_thresh: junction threshold. cos < thresh = junction (default 0.9).

    Returns:
        JunctionInfo with junction_verts, junction_edges, face_normals.
    """
    face_normals = compute_face_normals(faces, points, wall_face_indices)

    # Per-vert: list of adjacent (face_id, face_normal)
    v_to_faces: dict[int, list[int]] = defaultdict(list)
    for fi in wall_face_indices:
        if fi not in face_normals:
            continue
        for v in faces[fi]:
            v_to_faces[int(v)].append(fi)

    junction_verts: set[int] = set()
    for v, f_list in v_to_faces.items():
        if len(f_list) < 2:
            continue
        normals = np.stack([face_normals[fi] for fi in f_list], axis=0)
        # pairwise cosine matrix
        coss = normals @ normals.T
        np.fill_diagonal(coss, 1.0)
        if float(coss.min()) < cos_thresh:
            junction_verts.add(v)

    # Edge → list of adjacent faces (use sorted vert ids as key)
    edge_to_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for fi in wall_face_indices:
        if fi not in face_normals:
            continue
        f = faces[fi]
        n_v = len(f)
        for i in range(n_v):
            v0 = int(f[i])
            v1 = int(f[(i + 1) % n_v])
            key = (min(v0, v1), max(v0, v1))
            edge_to_faces[key].append(fi)

    junction_edges: set[tuple[int, int]] = set()
    for edge, f_list in edge_to_faces.items():
        if len(f_list) != 2:
            continue
        n0 = face_normals[f_list[0]]
        n1 = face_normals[f_list[1]]
        if float(np.dot(n0, n1)) < cos_thresh:
            junction_edges.add(edge)

    return JunctionInfo(
        junction_verts=junction_verts,
        junction_edges=junction_edges,
        face_normals=face_normals,
    )


@dataclass
class InnerVertResult:
    """Result of per-face inner vertex generation.

    new_points: original points + appended duplicates (no original verts moved).
    face_inner_vert: (face_id, vert_id) -> inner_vert_id mapping.
        For NON-junction verts: shared inner vert (one per wall vert v).
        For JUNCTION verts: face-cluster-specific inner vert.
    n_dup_verts: number of duplicate verts appended (junction clusters extra).
    """

    new_points: np.ndarray
    face_inner_vert: dict[tuple[int, int], int]
    n_dup_verts: int


def _cluster_face_normals(
    face_ids: list[int],
    face_normals: dict[int, np.ndarray],
    cos_thresh: float,
) -> list[list[int]]:
    """Greedy cluster face ids by normal similarity (cos >= cos_thresh).

    Returns: list of clusters, each a list of face_ids belonging together.
    """
    clusters: list[list[int]] = []
    cluster_means: list[np.ndarray] = []
    for fi in face_ids:
        if fi not in face_normals:
            continue
        n = face_normals[fi]
        best_cl = -1
        best_cos = -2.0
        for ci, cmean in enumerate(cluster_means):
            c = float(np.dot(n, cmean))
            if c >= cos_thresh and c > best_cos:
                best_cos = c
                best_cl = ci
        if best_cl >= 0:
            clusters[best_cl].append(fi)
            new_count = len(clusters[best_cl])
            new_mean = (cluster_means[best_cl] * (new_count - 1) + n) / new_count
            mag = float(np.linalg.norm(new_mean))
            if mag > 1e-30:
                new_mean = new_mean / mag
            cluster_means[best_cl] = new_mean
        else:
            clusters.append([fi])
            cluster_means.append(n.copy())
    return clusters


def generate_per_face_inner_verts(
    wall_face_indices: list[int],
    faces: list[list[int]],
    points: np.ndarray,
    junction_info: JunctionInfo,
    *,
    vnorm: dict[int, np.ndarray] | None = None,
    thickness: float = 0.001,
    cluster_cos: float = 0.9,
) -> InnerVertResult:
    """Generate per-face inner vert positions with junction-aware duplication.

    For each wall vert v:
      - if v is a junction vert (in junction_info.junction_verts):
          cluster adjacent face_normals (cos >= cluster_cos in same cluster)
          each cluster gets its own duplicate inner vert at:
              v - cluster_normal_avg × thickness
          face_inner_vert[(f, v)] = cluster's inner vert
      - else (smooth surface):
          single shared inner vert at v - vnorm[v] × thickness
          (vnorm provided externally; falls back to uniform avg if None)

    The original wall verts are NOT moved. New inner verts are APPENDED to
    points array. The mapping face_inner_vert tells each face's prism which
    inner vert to use for each of its outer verts.

    Args:
        wall_face_indices: indices of wall faces.
        faces: list of face vertex lists.
        points: (N, 3) original vertex coordinates.
        junction_info: result from detect_junction_verts.
        vnorm: per-vert outward normal (for non-junction verts). If None,
            uses uniform avg of adjacent face normals.
        thickness: extrusion distance (positive: inward = -normal direction).
        cluster_cos: face_normals with cos >= this go in same cluster
            (default 0.9 ≈ 25°).

    Returns:
        InnerVertResult with new_points, face_inner_vert mapping, n_dup_verts.
    """
    face_normals = junction_info.face_normals
    junction_verts = junction_info.junction_verts

    # Build per-vert: list of adjacent face ids (only valid wall faces).
    v_to_faces: dict[int, list[int]] = defaultdict(list)
    for fi in wall_face_indices:
        if fi not in face_normals:
            continue
        for v in faces[fi]:
            v_to_faces[int(v)].append(fi)

    new_points_list: list[np.ndarray] = list(points)
    face_inner_vert: dict[tuple[int, int], int] = {}
    n_pts_orig = len(points)
    cursor = n_pts_orig

    # Compute fallback vnorm (uniform avg) if not provided.
    def _fallback_vnorm(v: int) -> np.ndarray:
        f_list = v_to_faces.get(v, [])
        if not f_list:
            return np.zeros(3, dtype=np.float64)
        n_sum = np.zeros(3, dtype=np.float64)
        for fi in f_list:
            n_sum = n_sum + face_normals[fi]
        m = float(np.linalg.norm(n_sum))
        if m < 1e-30:
            return np.zeros(3, dtype=np.float64)
        return n_sum / m

    # For each wall vert: junction → cluster + dup; else → single shared.
    # Track shared inner verts (non-junction).
    shared_inner: dict[int, int] = {}

    for v, f_list in v_to_faces.items():
        if v in junction_verts:
            # Cluster adj face_normals; each cluster gets its own dup.
            clusters = _cluster_face_normals(f_list, face_normals, cluster_cos)
            for cluster_face_ids in clusters:
                # cluster mean normal (re-compute fresh).
                ns = np.stack([face_normals[fi] for fi in cluster_face_ids], axis=0)
                cmean = ns.mean(axis=0)
                m = float(np.linalg.norm(cmean))
                if m > 1e-30:
                    cmean = cmean / m
                # New inner vert at v - cmean × thickness
                inner_pt = points[v] - cmean * thickness
                new_points_list.append(inner_pt)
                inner_id = cursor
                cursor += 1
                # Map every face in this cluster to this inner vert (for v).
                for fi in cluster_face_ids:
                    face_inner_vert[(fi, v)] = inner_id
        else:
            # Smooth — single shared inner vert.
            if vnorm is not None and v in vnorm:
                vn = np.asarray(vnorm[v], dtype=np.float64)
            else:
                vn = _fallback_vnorm(v)
            inner_pt = points[v] - vn * thickness
            new_points_list.append(inner_pt)
            inner_id = cursor
            cursor += 1
            shared_inner[v] = inner_id
            for fi in f_list:
                face_inner_vert[(fi, v)] = inner_id

    new_points = np.asarray(new_points_list, dtype=np.float64)
    n_dup = cursor - n_pts_orig
    return InnerVertResult(
        new_points=new_points,
        face_inner_vert=face_inner_vert,
        n_dup_verts=n_dup,
    )


@dataclass
class PrismCellsResult:
    """Result of single-layer prism cell construction.

    cell_face_verts[cell_id] = [face_verts_list, ...]
        Each prism has 5 faces: bottom tri (wall), top tri (cap), 3 side quads.
        Bottom tri ordered with outward winding (face_normal points away from
        cell). Top tri opposite winding.

    cell_to_wall_face: cell_id -> original wall_face_id (for diagnostic +
        boundary patch tracking).
    """

    cell_face_verts: list[list[list[int]]]
    cell_to_wall_face: list[int]


def build_prism_cells(
    wall_face_indices: list[int],
    faces: list[list[int]],
    inner_result: InnerVertResult,
) -> PrismCellsResult:
    """Build single-layer prism cells using per-face inner verts.

    For each wall face f with outer triangle (a0, a1, a2), construct a prism
    cell with:
      - bottom face: (a0, a1, a2) — wall (boundary patch)
      - top face: (b0, b1, b2) where bi = face_inner_vert[(f, ai)]
      - 3 side quads: (ai, ai+1, bi+1, bi) for i ∈ {0, 1, 2}

    The bottom and top tri have opposite winding to ensure consistent outward
    normals when treated as cell boundary.

    Args:
        wall_face_indices: indices of wall faces (each must be a triangle).
        faces: list of face vertex lists.
        inner_result: from generate_per_face_inner_verts.

    Returns:
        PrismCellsResult with cell_face_verts and cell_to_wall_face.

    Raises:
        ValueError: if any wall face is not a triangle (len != 3).
    """
    cell_face_verts: list[list[list[int]]] = []
    cell_to_wall_face: list[int] = []

    for fi in wall_face_indices:
        f = faces[fi]
        if len(f) != 3:
            raise ValueError(
                f"build_prism_cells requires triangle wall faces, "
                f"got face {fi} with {len(f)} verts."
            )
        a0, a1, a2 = int(f[0]), int(f[1]), int(f[2])
        # Inner verts (per-face). Must exist in mapping.
        if (fi, a0) not in inner_result.face_inner_vert:
            raise ValueError(f"Missing inner vert for face {fi} vert {a0}")
        b0 = inner_result.face_inner_vert[(fi, a0)]
        b1 = inner_result.face_inner_vert[(fi, a1)]
        b2 = inner_result.face_inner_vert[(fi, a2)]

        # 5 faces of prism wedge:
        # Bottom tri (wall) — original orientation (a0, a1, a2)
        # Top tri (cap toward bulk) — reverse: (b0, b2, b1) so normal opposite
        # 3 side quads. Convention: each side quad has outward normal pointing
        # away from cell. Quad (a0, a1, b1, b0) etc.
        prism_faces = [
            [a0, a1, a2],       # bottom (wall)
            [b0, b2, b1],       # top (cap)
            [a0, a1, b1, b0],   # side 0-1
            [a1, a2, b2, b1],   # side 1-2
            [a2, a0, b0, b2],   # side 2-0
        ]
        cell_face_verts.append(prism_faces)
        cell_to_wall_face.append(int(fi))

    return PrismCellsResult(
        cell_face_verts=cell_face_verts,
        cell_to_wall_face=cell_to_wall_face,
    )


@dataclass
class PolyMeshResult:
    """OpenFOAM-style polyMesh result built from cell_face_verts.

    points: passed through (no re-ordering).
    faces: list of vertex lists. Internal faces appear first (sorted by
        (owner, neighbour)), then boundary faces grouped by patch in the
        order: wall, bl_internal, bl_internal_side.
    owner: face_id -> cell_id (length == len(faces)).
    neighbour: face_id -> cell_id (length == n_internal_faces). Boundary
        faces have no entry; OpenFOAM convention.
    patches: list of dicts with name, startFace, nFaces (only patches with
        at least one face are included).
    """

    points: np.ndarray
    faces: list[list[int]]
    owner: list[int]
    neighbour: list[int]
    patches: list[dict]


_PATCH_ORDER = ("wall", "bl_internal", "bl_internal_side")


def _patch_for_face_idx(face_idx_in_cell: int) -> str:
    """Single-layer prism patch hint from face index inside cell.

    face_idx 0 = bottom tri (wall), 1 = top tri (bl_internal),
    2/3/4 = side quads (bl_internal_side).
    """
    if face_idx_in_cell == 0:
        return "wall"
    if face_idx_in_cell == 1:
        return "bl_internal"
    return "bl_internal_side"


def cells_to_polymesh(
    cell_face_verts: list[list[list[int]]],
    points: np.ndarray,
    *,
    cell_kinds: list[str] | None = None,
) -> PolyMeshResult:
    """Convert per-cell face lists into OpenFOAM polyMesh format.

    Algorithm:
    1. Canonical key per face = tuple(sorted(verts)).
    2. Collect occurrences per key: list[(cell_id, face_idx_in_cell, raw_verts)].
    3. 2 occurrences → internal face. owner = min(cells), neighbour = max(cells).
       Use raw_verts from the OWNER (lower-cell) occurrence to preserve outward
       winding from the owner cell.
    4. 1 occurrence → boundary face. Patch from face_idx_in_cell.
    5. 3+ occurrences → ValueError (manifold violation).

    Order:
      * internal faces first, sorted by (owner, neighbour)
      * boundary faces grouped: wall, bl_internal, bl_internal_side

    Args:
        cell_face_verts: per-cell list of face vertex lists (e.g. from
            build_prism_cells.cell_face_verts).
        points: (N, 3) vertex coordinates (passed through to result).
        cell_kinds: optional per-cell kind tag controlling patch
            classification. ``None`` (default) treats every cell as
            ``"prism"`` (face 0 = wall, face 1 = bl_internal, rest =
            bl_internal_side). ``"gap_fill"`` puts every face on the
            bl_internal_side patch.

    Returns:
        PolyMeshResult.

    Raises:
        ValueError: if any face appears in 3 or more cells (non-manifold)
            or if ``cell_kinds`` length disagrees with cells.
    """
    if cell_kinds is not None and len(cell_kinds) != len(cell_face_verts):
        raise ValueError(
            f"cell_kinds length {len(cell_kinds)} != cells "
            f"{len(cell_face_verts)}"
        )

    def _patch_for(cell_id: int, face_idx: int) -> str:
        kind = "prism" if cell_kinds is None else cell_kinds[cell_id]
        if kind == "prism":
            return _patch_for_face_idx(face_idx)
        return "bl_internal_side"

    def _clean_face_vertices(raw_verts: list[int]) -> list[int]:
        """Drop repeated vertices that would emit zero-area polyMesh faces."""
        clean: list[int] = []
        for raw_v in raw_verts:
            v = int(raw_v)
            if not clean or clean[-1] != v:
                clean.append(v)
        if len(clean) > 1 and clean[0] == clean[-1]:
            clean.pop()
        return clean

    occurrences: dict[tuple[int, ...], list[tuple[int, int, list[int]]]] = (
        defaultdict(list)
    )
    for cell_id, cf in enumerate(cell_face_verts):
        for face_idx, raw_verts in enumerate(cf):
            verts = _clean_face_vertices(list(int(v) for v in raw_verts))
            if len(verts) < 3 or len(set(verts)) < 3:
                continue
            key = tuple(sorted(verts))
            occurrences[key].append((cell_id, face_idx, verts))

    internal_records: list[tuple[int, int, list[int]]] = []
    # boundary buckets keyed by patch name to honor ordering convention.
    boundary_records: dict[str, list[tuple[int, list[int]]]] = {
        name: [] for name in _PATCH_ORDER
    }

    for key, occs in occurrences.items():
        if len(occs) == 1:
            cell_id, face_idx, raw_verts = occs[0]
            patch_name = _patch_for(cell_id, face_idx)
            if patch_name not in boundary_records:
                boundary_records[patch_name] = []
            boundary_records[patch_name].append((cell_id, raw_verts))
        elif len(occs) == 2:
            (c0, _idx0, verts0), (c1, _idx1, verts1) = occs
            if c0 == c1:
                # Same cell appears twice with same face — ill-formed.
                raise ValueError(
                    f"Face {key} appears twice in same cell {c0}; "
                    f"cell topology is malformed."
                )
            owner = min(c0, c1)
            neighbour = max(c0, c1)
            owner_verts = verts0 if c0 == owner else verts1
            internal_records.append((owner, neighbour, owner_verts))
        else:
            raise ValueError(
                f"Face {key} shared by {len(occs)} cells "
                f"(cells={[occ[0] for occ in occs]}); "
                f"non-manifold topology — refusing to build polyMesh."
            )

    internal_records.sort(key=lambda r: (r[0], r[1]))

    out_faces: list[list[int]] = []
    out_owner: list[int] = []
    out_neighbour: list[int] = []
    for owner, neighbour, verts in internal_records:
        out_faces.append(list(verts))
        out_owner.append(owner)
        out_neighbour.append(neighbour)

    patches: list[dict] = []
    for patch_name in _PATCH_ORDER:
        bucket = boundary_records.get(patch_name, [])
        if not bucket:
            continue
        start_face = len(out_faces)
        for cell_id, verts in bucket:
            out_faces.append(list(verts))
            out_owner.append(cell_id)
        patches.append({
            "name": patch_name,
            "startFace": start_face,
            "nFaces": len(bucket),
        })

    return PolyMeshResult(
        points=points,
        faces=out_faces,
        owner=out_owner,
        neighbour=out_neighbour,
        patches=patches,
    )


@dataclass
class GapFillResult:
    """Result of gap-fill cell construction at junction edges.

    cell_face_verts[cell_id] = [face_verts_list, ...]
        Each gap-fill cell is a tetrahedron: 4 triangle faces.

    junction_edges: list of wall edges (v_min, v_max) that produced gap-fill
        cells (i.e. all four inner verts distinct). Each edge contributes 2
        consecutive cells in cell_face_verts.
    """

    cell_face_verts: list[list[list[int]]]
    junction_edges: list[tuple[int, int]]


def _tet_faces(
    a: int, b: int, c: int, d: int, points: np.ndarray
) -> list[list[int]]:
    """Return the four triangle faces of a tetrahedron (a, b, c, d).

    If the signed volume is negative, swap c and d so the tet has positive
    orientation; faces are then emitted with outward-pointing winding
    relative to the cell centroid. For polyMesh face matching this is
    cosmetic (the canonical key sorts verts), but consistent winding lets
    boundary patches behave correctly downstream.
    """
    pa = points[a]
    pb = points[b]
    pc = points[c]
    pd = points[d]
    sv = float(np.dot(np.cross(pb - pa, pc - pa), pd - pa))
    if sv < 0:
        c, d = d, c
    return [
        [b, c, d],
        [a, d, c],
        [a, b, d],
        [a, c, b],
    ]


def build_gap_fill_cells(
    wall_face_indices: list[int],
    faces: list[list[int]],
    points: np.ndarray,
    inner_result: InnerVertResult,
) -> GapFillResult:
    """Build gap-fill tetrahedral cells at junction edges.

    For each wall edge (v, w) shared by exactly 2 wall faces (f1, f2):
      * Look up vi1 = inner[(f1, v)], wi1 = inner[(f1, w)],
        vi2 = inner[(f2, v)], wi2 = inner[(f2, w)].
      * If all four are distinct, the edge is a junction edge and we insert
        two tetrahedra to close the topological gap between the two prism
        side flaps:
          tet A: (v, w, wi1, vi1)
          tet B: (v, w, vi2, wi2)
      * Otherwise (any inner vert shared between f1 and f2 at v or w) the
        adjacent prisms already share a side face — no gap to fill.

    Edges shared by 3+ wall faces are non-manifold for our current builder;
    we raise NotImplementedError so future iterations can add fan
    triangulation if a real STL needs it.

    Args:
        wall_face_indices: indices of wall faces.
        faces: list of face vertex lists.
        points: (N, 3) coordinates including duplicated inner verts (used
            only to orient the tet faces consistently).
        inner_result: from generate_per_face_inner_verts.

    Returns:
        GapFillResult.

    Raises:
        NotImplementedError: if any wall edge is shared by 3 or more faces.
    """
    edge_to_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for fi in wall_face_indices:
        f = faces[fi]
        n_v = len(f)
        for i in range(n_v):
            v0 = int(f[i])
            v1 = int(f[(i + 1) % n_v])
            key = (min(v0, v1), max(v0, v1))
            edge_to_faces[key].append(int(fi))

    cell_face_verts: list[list[list[int]]] = []
    filled_edges: list[tuple[int, int]] = []

    for edge, f_list in edge_to_faces.items():
        if len(f_list) > 2:
            raise NotImplementedError(
                f"3+ wall faces share edge {edge} (n_faces={len(f_list)}); "
                "fan triangulation for non-manifold junctions is not "
                "implemented in this iteration."
            )
        if len(f_list) != 2:
            continue
        v, w = edge
        f1, f2 = f_list[0], f_list[1]
        vi1 = inner_result.face_inner_vert.get((f1, v))
        wi1 = inner_result.face_inner_vert.get((f1, w))
        vi2 = inner_result.face_inner_vert.get((f2, v))
        wi2 = inner_result.face_inner_vert.get((f2, w))
        if vi1 is None or wi1 is None or vi2 is None or wi2 is None:
            continue
        if len({vi1, wi1, vi2, wi2}) < 4:
            continue

        cell_face_verts.append(
            _tet_faces(int(v), int(w), int(wi1), int(vi1), inner_result.new_points)
        )
        cell_face_verts.append(
            _tet_faces(int(v), int(w), int(vi2), int(wi2), inner_result.new_points)
        )
        filled_edges.append((int(v), int(w)))

    return GapFillResult(
        cell_face_verts=cell_face_verts,
        junction_edges=filled_edges,
    )


def _triangulate_quad(quad: list[int]) -> list[list[int]]:
    """Canonical triangulation of a 4-vertex quad face.

    Splits along the diagonal connecting the lowest-id vertex of the quad to
    its non-adjacent neighbour. Both incidences of the same shared quad
    therefore pick identical triangles regardless of which cyclic ordering
    each cell stored, which lets prism side quads share with adjacent
    gap-fill tetrahedra at junction edges.
    """
    if len(quad) != 4:
        raise ValueError(f"Expected 4-vert quad, got {len(quad)}: {quad}")
    verts = [int(v) for v in quad]
    min_pos = verts.index(min(verts))
    a = verts[min_pos]
    b = verts[(min_pos + 1) % 4]
    c = verts[(min_pos + 2) % 4]
    d = verts[(min_pos + 3) % 4]
    return [[a, b, c], [a, c, d]]


def _triangulate_prism_cell(prism_cell: list[list[int]]) -> list[list[int]]:
    """Replace every 4-vertex side face in a prism cell with 2 triangles.

    Triangle faces (wall + cap) pass through unchanged so the patch
    classifier still sees face_idx 0 = wall, face_idx 1 = bl_internal in the
    rebuilt cell. The remaining 6 indices belong to side triangles which all
    classify as bl_internal_side.
    """
    out: list[list[int]] = []
    for face in prism_cell:
        if len(face) == 4:
            out.extend(_triangulate_quad(face))
        else:
            out.append([int(v) for v in face])
    return out


@dataclass
class FullBLResult:
    """Combined polyMesh of prism BL cells and junction-edge gap-fill cells.

    polymesh: PolyMeshResult covering both prism and gap-fill cells.
    n_prism_cells: number of prism cells (first ``n_prism_cells`` entries in
        the underlying cell list).
    n_gap_fill_cells: number of tet gap-fill cells appended after prisms.
    junction_edges: wall edges that produced gap-fill cells (from
        ``build_gap_fill_cells``).
    """

    polymesh: PolyMeshResult
    n_prism_cells: int
    n_gap_fill_cells: int
    junction_edges: list[tuple[int, int]]


@dataclass
class BulkPreservingFullBLResult:
    """Combined polyMesh preserving original bulk cells plus VD BL cells.

    ``n_bulk_cells`` original volume cells are emitted first, followed by
    prism layer cells and gap-fill cells.  Wall boundary faces of the original
    bulk are replaced by the innermost VD cap, so the bulk remains attached to
    the new BL stack instead of being dropped.
    """

    polymesh: PolyMeshResult
    n_bulk_cells: int
    n_prism_cells: int
    n_gap_fill_cells: int
    junction_edges: list[tuple[int, int]]


def build_full_bl_polymesh(
    wall_face_indices: list[int],
    faces: list[list[int]],
    points: np.ndarray,
    inner_result: InnerVertResult,
) -> FullBLResult:
    """Build a unified polyMesh combining prism BL + junction gap-fill cells.

    Pipeline:
        1. ``build_prism_cells`` for the per-wall-triangle prism layer.
        2. Triangulate every prism's 4-vertex side quad with a canonical
           diagonal so adjacent prisms / gap-fill tets agree on the split.
        3. ``build_gap_fill_cells`` for tetrahedra at junction edges where
           the per-face inner-vertex duplication leaves a topology gap.
        4. Concatenate cells (prisms first, gap-fills second) and run
           ``cells_to_polymesh`` with per-cell kind tags so gap-fill faces
           land on bl_internal_side instead of being misclassified as wall
           or bl_internal.

    The triangulation step is what lets prism side faces share with the
    triangle faces of the gap-fill tets — without it the 4-vert quad and the
    3-vert triangles never match and every junction edge stays open.

    Args:
        wall_face_indices: indices of wall faces in ``faces``.
        faces: list of face vertex lists.
        points: original (N, 3) coordinates (passed to ``build_gap_fill_cells``
            for tet orientation; the polyMesh stores ``inner_result.new_points``).
        inner_result: from ``generate_per_face_inner_verts``.

    Returns:
        FullBLResult.

    Raises:
        ValueError / NotImplementedError: bubbled from the underlying
            builders if topology preconditions are violated.
    """
    prisms = build_prism_cells(wall_face_indices, faces, inner_result)
    gap = build_gap_fill_cells(wall_face_indices, faces, points, inner_result)

    triangulated_prism_cells = [
        _triangulate_prism_cell(cell) for cell in prisms.cell_face_verts
    ]
    n_prism = len(triangulated_prism_cells)
    n_gap = len(gap.cell_face_verts)

    combined_cells: list[list[list[int]]] = (
        triangulated_prism_cells + gap.cell_face_verts
    )
    cell_kinds = ["prism"] * n_prism + ["gap_fill"] * n_gap

    pm = cells_to_polymesh(
        combined_cells,
        inner_result.new_points,
        cell_kinds=cell_kinds,
    )

    return FullBLResult(
        polymesh=pm,
        n_prism_cells=n_prism,
        n_gap_fill_cells=n_gap,
        junction_edges=list(gap.junction_edges),
    )


@dataclass
class MultiLayerBLResult:
    """Stack of prism BL layers with caps shared between adjacent layers.

    cell_face_verts: per-cell face vertex lists. Cells are ordered by layer
        (layer 0 first, then layer 1, …) and within a layer by the position
        of the originating wall face in ``wall_face_indices``.
    cell_to_wall_face: cell_id -> wall face index (the originating wall face).
    cell_to_layer: cell_id -> 0-based layer index.
    new_points: original points + appended per-layer inner verts. Layer 0's
        inner verts start at ``len(points)``; subsequent layers' inner verts
        follow contiguously.
    num_layers: same as input.
    layer_thicknesses: cumulative thickness from the wall to each layer's
        inner cap (length == num_layers).
    """

    cell_face_verts: list[list[list[int]]]
    cell_to_wall_face: list[int]
    cell_to_layer: list[int]
    new_points: np.ndarray
    num_layers: int
    layer_thicknesses: list[float]


def build_multi_layer_bl(
    wall_face_indices: list[int],
    faces: list[list[int]],
    points: np.ndarray,
    junction_info: JunctionInfo,
    *,
    num_layers: int,
    first_layer_thickness: float,
    growth_ratio: float = 1.0,
    vnorm: dict[int, np.ndarray] | None = None,
    cluster_cos: float = 0.9,
) -> MultiLayerBLResult:
    """Build N stacked prism BL layers above the wall.

    Per-face inner verts are produced fresh for every layer using
    ``generate_per_face_inner_verts`` at the cumulative thickness from the
    wall, so the junction-aware clustering applied at layer 0 carries through
    to every subsequent layer. Vertex ids in different layers are disjoint.

    Each layer's inner cap is shared with the next layer's outer base (same
    vertex ids), so ``cells_to_polymesh`` automatically classifies the
    intermediate caps as internal faces. Only layer 0's bottom is a
    ``wall`` boundary; only layer N-1's top is a ``bl_internal`` boundary.

    Args:
        wall_face_indices: indices of triangle wall faces.
        faces: list of face vertex lists.
        points: (N, 3) original vertex coordinates.
        junction_info: from ``detect_junction_verts``.
        num_layers: number of layers in the stack (>= 1).
        first_layer_thickness: thickness of the first layer (> 0).
        growth_ratio: per-layer thickness multiplier (> 0). Layer k's
            thickness equals ``first_layer_thickness * growth_ratio ** k``.
        vnorm: optional per-vert smooth normal (passed through to
            ``generate_per_face_inner_verts`` for non-junction verts).
        cluster_cos: cluster threshold for junction inner vert duplication.

    Returns:
        MultiLayerBLResult.

    Raises:
        ValueError: if num_layers, first_layer_thickness or growth_ratio is
            non-positive, or if any wall face is not a triangle.
    """
    if num_layers < 1:
        raise ValueError(f"num_layers must be >= 1, got {num_layers}")
    if first_layer_thickness <= 0:
        raise ValueError(
            f"first_layer_thickness must be > 0, got {first_layer_thickness}"
        )
    if growth_ratio <= 0:
        raise ValueError(f"growth_ratio must be > 0, got {growth_ratio}")

    layer_thicknesses: list[float] = []
    t_cum = 0.0
    layer_t = first_layer_thickness
    for _ in range(num_layers):
        t_cum += layer_t
        layer_thicknesses.append(t_cum)
        layer_t *= growth_ratio

    n_orig = len(points)
    combined_points: list[np.ndarray] = [
        np.asarray(p, dtype=np.float64) for p in points
    ]
    layer_inner_maps: list[dict[tuple[int, int], int]] = []

    for t_total in layer_thicknesses:
        local_res = generate_per_face_inner_verts(
            wall_face_indices,
            faces,
            points,
            junction_info,
            vnorm=vnorm,
            thickness=t_total,
            cluster_cos=cluster_cos,
        )
        offset = len(combined_points) - n_orig
        layer_map: dict[tuple[int, int], int] = {
            key: vid + offset for key, vid in local_res.face_inner_vert.items()
        }
        for row in local_res.new_points[n_orig:]:
            combined_points.append(np.asarray(row, dtype=np.float64))
        layer_inner_maps.append(layer_map)

    new_points = np.asarray(combined_points, dtype=np.float64)

    cell_face_verts: list[list[list[int]]] = []
    cell_to_wall_face: list[int] = []
    cell_to_layer: list[int] = []

    for k_idx in range(num_layers):
        outer_map = layer_inner_maps[k_idx - 1] if k_idx > 0 else None
        inner_map = layer_inner_maps[k_idx]

        for fi in wall_face_indices:
            f = faces[fi]
            if len(f) != 3:
                raise ValueError(
                    f"build_multi_layer_bl requires triangle wall faces, "
                    f"got face {fi} with {len(f)} verts."
                )
            a0, a1, a2 = int(f[0]), int(f[1]), int(f[2])
            if outer_map is None:
                o0, o1, o2 = a0, a1, a2
            else:
                o0 = outer_map[(fi, a0)]
                o1 = outer_map[(fi, a1)]
                o2 = outer_map[(fi, a2)]
            i0 = inner_map[(fi, a0)]
            i1 = inner_map[(fi, a1)]
            i2 = inner_map[(fi, a2)]

            prism_faces = [
                [o0, o1, o2],
                [i0, i2, i1],
                [o0, o1, i1, i0],
                [o1, o2, i2, i1],
                [o2, o0, i0, i2],
            ]
            cell_face_verts.append(prism_faces)
            cell_to_wall_face.append(int(fi))
            cell_to_layer.append(k_idx)

    return MultiLayerBLResult(
        cell_face_verts=cell_face_verts,
        cell_to_wall_face=cell_to_wall_face,
        cell_to_layer=cell_to_layer,
        new_points=new_points,
        num_layers=num_layers,
        layer_thicknesses=layer_thicknesses,
    )


def build_multi_layer_gap_fill_cells(
    wall_face_indices: list[int],
    faces: list[list[int]],
    multi_result: MultiLayerBLResult,
) -> GapFillResult:
    """Build per-layer gap-fill tetrahedra for duplicated junction side quads.

    ``build_gap_fill_cells()`` closes a single-layer junction by adding two
    tetrahedra whose faces match the canonical triangulation of each prism side
    flap.  For a multi-layer stack, the same closure is needed independently at
    every layer because layer k's outer vertices are face-specific duplicates
    once k > 0.
    """
    face_pos = {int(fi): i for i, fi in enumerate(wall_face_indices)}
    edge_to_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    edge_local_index: dict[tuple[int, int, int], int] = {}
    for fi in wall_face_indices:
        f = faces[fi]
        n_v = len(f)
        for i in range(n_v):
            v0 = int(f[i])
            v1 = int(f[(i + 1) % n_v])
            key = (min(v0, v1), max(v0, v1))
            edge_to_faces[key].append(int(fi))
            edge_local_index[(int(fi), key[0], key[1])] = i

    n_wall = len(wall_face_indices)
    cell_face_verts: list[list[list[int]]] = []
    filled_edges: list[tuple[int, int]] = []

    for edge, f_list in edge_to_faces.items():
        if len(f_list) > 2:
            raise NotImplementedError(
                f"3+ wall faces share edge {edge} (n_faces={len(f_list)}); "
                "fan triangulation for non-manifold junctions is not "
                "implemented in this iteration."
            )
        if len(f_list) != 2:
            continue
        f1, f2 = int(f_list[0]), int(f_list[1])
        if f1 not in face_pos or f2 not in face_pos:
            continue
        for layer in range(int(multi_result.num_layers)):
            c1 = layer * n_wall + face_pos[f1]
            c2 = layer * n_wall + face_pos[f2]
            if c1 >= len(multi_result.cell_face_verts) or c2 >= len(multi_result.cell_face_verts):
                continue
            i1 = edge_local_index.get((f1, edge[0], edge[1]))
            i2 = edge_local_index.get((f2, edge[0], edge[1]))
            if i1 is None or i2 is None:
                continue
            side1 = list(multi_result.cell_face_verts[c1][2 + i1])
            side2 = list(multi_result.cell_face_verts[c2][2 + i2])
            if tuple(sorted(side1)) == tuple(sorted(side2)):
                continue
            if len(set(side1)) == 4:
                cell_face_verts.append(
                    _tet_faces(side1[0], side1[1], side1[2], side1[3], multi_result.new_points)
                )
            if len(set(side2)) == 4:
                cell_face_verts.append(
                    _tet_faces(side2[0], side2[1], side2[2], side2[3], multi_result.new_points)
                )
            if len(set(side1)) == 4 or len(set(side2)) == 4:
                filled_edges.append((int(edge[0]), int(edge[1])))

    return GapFillResult(
        cell_face_verts=cell_face_verts,
        junction_edges=filled_edges,
    )


def build_multi_layer_full_bl_polymesh(
    wall_face_indices: list[int],
    faces: list[list[int]],
    points: np.ndarray,
    junction_info: JunctionInfo,
    *,
    num_layers: int,
    first_layer_thickness: float,
    growth_ratio: float = 1.0,
    vnorm: dict[int, np.ndarray] | None = None,
    cluster_cos: float = 0.9,
) -> FullBLResult:
    """Build a multi-layer VD BL polyMesh with per-layer junction closures."""
    multi = build_multi_layer_bl(
        wall_face_indices,
        faces,
        points,
        junction_info,
        num_layers=num_layers,
        first_layer_thickness=first_layer_thickness,
        growth_ratio=growth_ratio,
        vnorm=vnorm,
        cluster_cos=cluster_cos,
    )
    gap = build_multi_layer_gap_fill_cells(
        wall_face_indices,
        faces,
        multi,
    )
    prism_cells = [
        _triangulate_prism_cell(cell) for cell in multi.cell_face_verts
    ]
    n_prism = len(prism_cells)
    n_gap = len(gap.cell_face_verts)
    combined_cells = prism_cells + gap.cell_face_verts
    cell_kinds = ["prism"] * n_prism + ["gap_fill"] * n_gap
    pm = cells_to_polymesh(
        combined_cells,
        multi.new_points,
        cell_kinds=cell_kinds,
    )
    return FullBLResult(
        polymesh=pm,
        n_prism_cells=n_prism,
        n_gap_fill_cells=n_gap,
        junction_edges=list(gap.junction_edges),
    )


def _build_multi_layer_gap_bridge_cells(
    wall_face_indices: list[int],
    faces: list[list[int]],
    multi_result: MultiLayerBLResult,
    owner: np.ndarray | None = None,
) -> GapFillResult:
    """Build non-degenerate bridge cells between duplicated layer-edge flaps.

    The earlier gap-fill tet formulation is topologically useful for face
    matching tests, but each tet is built from a single prism side quad and is
    therefore geometrically flat.  Bulk-preserving BL needs actual volume.  This
    helper inserts one bridge polyhedron per junction edge per layer:

    * layer 0: triangular-prism-like cell with two prism side quads, one inner
      quad and two triangular end caps;
    * layer k>0: hexahedron-like cell connecting the previous layer bridge face
      to the current layer bridge face.
    """
    face_pos = {int(fi): i for i, fi in enumerate(wall_face_indices)}
    edge_to_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    edge_local_index: dict[tuple[int, int, int], int] = {}
    for fi in wall_face_indices:
        f = faces[fi]
        n_v = len(f)
        for i in range(n_v):
            v0 = int(f[i])
            v1 = int(f[(i + 1) % n_v])
            key = (min(v0, v1), max(v0, v1))
            edge_to_faces[key].append(int(fi))
            edge_local_index[(int(fi), key[0], key[1])] = i

    n_wall = len(wall_face_indices)
    cell_face_verts: list[list[list[int]]] = []
    filled_edges: list[tuple[int, int]] = []
    vertex_face_graph: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
    bridge_face_counts: dict[tuple[int, ...], int] = defaultdict(int)

    def _edge_vertex_map(fi: int, layer: int, edge: tuple[int, int]) -> dict[int, tuple[int, int]]:
        pos = face_pos[fi]
        cell_idx = layer * n_wall + pos
        side_idx = edge_local_index[(fi, edge[0], edge[1])]
        side = [int(v) for v in multi_result.cell_face_verts[cell_idx][2 + side_idx]]
        f = faces[fi]
        local = side_idx
        start = int(f[local])
        end = int(f[(local + 1) % len(f)])
        # side convention from build_multi_layer_bl:
        # [outer_start, outer_end, inner_end, inner_start].
        return {
            start: (side[0], side[3]),
            end: (side[1], side[2]),
        }

    for edge, f_list in edge_to_faces.items():
        if len(f_list) > 2:
            raise NotImplementedError(
                f"3+ wall faces share edge {edge} (n_faces={len(f_list)}); "
                "fan triangulation for non-manifold junctions is not "
                "implemented in this iteration."
            )
        if len(f_list) != 2:
            continue
        f1, f2 = int(f_list[0]), int(f_list[1])
        if f1 not in face_pos or f2 not in face_pos:
            continue
        for vtx in edge:
            vertex_face_graph[int(vtx)][f1].add(f2)
            vertex_face_graph[int(vtx)][f2].add(f1)

        for layer in range(int(multi_result.num_layers)):
            m1 = _edge_vertex_map(f1, layer, edge)
            m2 = _edge_vertex_map(f2, layer, edge)
            v, w = int(edge[0]), int(edge[1])
            o1v, i1v = m1[v]
            o1w, i1w = m1[w]
            o2v, i2v = m2[v]
            o2w, i2w = m2[w]

            side1 = [o1v, o1w, i1w, i1v]
            side2 = [o2v, o2w, i2w, i2v]
            if tuple(sorted(side1)) == tuple(sorted(side2)):
                continue

            inner_bridge = [i1v, i1w, i2w, i2v]
            split_inner_bridge = (
                os.environ.get("AUTO_TESSELL_BL_VD_MIXED_OWNER_EDGE_CUT", "0") == "1"
                and owner is not None
                and layer == int(multi_result.num_layers) - 1
                and int(owner[f1]) != int(owner[f2])
                and len({i1v, i1w, i2v}) == 3
                and len({i1w, i2w, i2v}) == 3
            )
            if layer == 0:
                cell = [
                    side1,
                    list(reversed(side2)),
                    [v, i2v, i1v],
                    [w, i1w, i2w],
                ]
                if split_inner_bridge:
                    cell.extend([[i1v, i1w, i2v], [i1w, i2w, i2v]])
                else:
                    cell.insert(2, inner_bridge)
            else:
                outer_bridge = [o1v, o2v, o2w, o1w]
                cell = [
                    side1,
                    list(reversed(side2)),
                    outer_bridge,
                    [o1v, i1v, i2v, o2v],
                    [o1w, o2w, i2w, i1w],
                ]
                if split_inner_bridge:
                    cell.extend([[i1v, i1w, i2v], [i1w, i2w, i2v]])
                else:
                    cell.insert(3, inner_bridge)
            cell_keys = [tuple(sorted(int(v) for v in face)) for face in cell]
            if len(set(cell_keys)) != len(cell_keys):
                continue
            if any(bridge_face_counts[key] >= 2 for key in cell_keys):
                continue
            cell_face_verts.append(cell)
            for key in cell_keys:
                bridge_face_counts[key] += 1
            filled_edges.append((v, w))

    if os.environ.get("AUTO_TESSELL_BL_VD_VERTEX_FILL", "0") == "1":
        face_counts: dict[tuple[int, ...], int] = defaultdict(int)
        for cell in cell_face_verts:
            for raw_face in cell:
                face_counts[tuple(sorted(int(v) for v in raw_face))] += 1

        vertex_to_faces: dict[int, set[int]] = defaultdict(set)
        for fi in wall_face_indices:
            for v in faces[fi]:
                vertex_to_faces[int(v)].add(int(fi))

        def _ordered_vertex_faces(v: int) -> list[int]:
            face_set = set(vertex_to_faces.get(v, set()))
            if len(face_set) < 3:
                return []
            graph = vertex_face_graph.get(v, {})
            if not graph:
                return []
            endpoints = [f for f in face_set if len(graph.get(f, set()) & face_set) == 1]
            start = min(endpoints or list(face_set))
            order: list[int] = []
            prev: int | None = None
            cur = start
            for _ in range(len(face_set) + 2):
                if cur in order:
                    break
                order.append(cur)
                nxts = [
                    n for n in sorted(graph.get(cur, set()))
                    if n in face_set and n != prev
                ]
                nxt = next((n for n in nxts if n not in order), None)
                if nxt is None:
                    break
                prev, cur = cur, nxt
            if len(order) != len(face_set):
                return []
            return order

        def _face_vertex_pair(fi: int, layer: int, v: int) -> tuple[int, int] | None:
            try:
                local = [int(x) for x in faces[fi]].index(int(v))
            except ValueError:
                return None
            cell_idx = layer * n_wall + face_pos[int(fi)]
            cell = multi_result.cell_face_verts[cell_idx]
            outer = int(cell[0][local])
            top = cell[1]
            inner_by_local = [int(top[0]), int(top[2]), int(top[1])]
            return outer, inner_by_local[local]

        def _dedupe_ring(ids: list[int]) -> list[int]:
            out: list[int] = []
            for vid in ids:
                if not out or out[-1] != int(vid):
                    out.append(int(vid))
            if len(out) > 1 and out[0] == out[-1]:
                out.pop()
            return out

        for vtx in sorted(vertex_to_faces):
            ordered_faces = _ordered_vertex_faces(vtx)
            if len(ordered_faces) < 3:
                continue
            if owner is not None:
                owners = {int(owner[int(fi)]) for fi in ordered_faces}
                if len(owners) != 1:
                    continue
            for layer in range(int(multi_result.num_layers)):
                pairs = [
                    _face_vertex_pair(fi, layer, vtx)
                    for fi in ordered_faces
                ]
                if any(pair is None for pair in pairs):
                    continue
                outer_ids = _dedupe_ring([int(pair[0]) for pair in pairs if pair is not None])
                inner_ids = _dedupe_ring([int(pair[1]) for pair in pairs if pair is not None])
                if len(inner_ids) < 3 or len(set(inner_ids)) != len(inner_ids):
                    continue
                if layer == 0:
                    cell = [
                        [int(vtx), inner_ids[(i + 1) % len(inner_ids)], inner_ids[i]]
                        for i in range(len(inner_ids))
                    ]
                    cell.append(list(inner_ids))
                else:
                    if (
                        len(outer_ids) != len(inner_ids)
                        or len(outer_ids) < 3
                        or len(set(outer_ids)) != len(outer_ids)
                    ):
                        continue
                    cell = [
                        [
                            outer_ids[i],
                            inner_ids[i],
                            inner_ids[(i + 1) % len(inner_ids)],
                            outer_ids[(i + 1) % len(outer_ids)],
                        ]
                        for i in range(len(inner_ids))
                    ]
                    cell.append(list(outer_ids))
                    cell.append(list(reversed(inner_ids)))
                keys = [tuple(sorted(int(v) for v in face)) for face in cell]
                side_keys = keys[:len(inner_ids)]
                if any(face_counts[key] != 1 for key in side_keys):
                    continue
                if any(face_counts[key] >= 2 for key in keys):
                    continue
                cell_face_verts.append(cell)
                for key in keys:
                    face_counts[key] += 1

    return GapFillResult(
        cell_face_verts=cell_face_verts,
        junction_edges=filled_edges,
    )


def build_bulk_preserving_multi_layer_full_bl_polymesh(
    wall_face_indices: list[int],
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    points: np.ndarray,
    junction_info: JunctionInfo,
    *,
    num_layers: int,
    first_layer_thickness: float,
    growth_ratio: float = 1.0,
    vnorm: dict[int, np.ndarray] | None = None,
    cluster_cos: float = 0.9,
) -> BulkPreservingFullBLResult:
    """Build VD BL while preserving the existing bulk cell topology.

    This is the first bulk-preserving form of the VD refactor.  It reconstructs
    the original bulk cells from OpenFOAM ``faces/owner/neighbour`` and replaces
    each selected wall boundary face with the innermost VD cap face.  The VD
    prism stack and junction gap-fill cells are appended after those bulk cells,
    then the whole cell set is converted to a fresh polyMesh.

    Scope:
      * wall faces must be triangles;
      * non-wall boundary faces, if any, are retained as generic side patch
        faces by ``cells_to_polymesh``.  The tet+BL bench target uses closed
        body meshes where all boundary faces are wall faces.
    """
    owner_arr = np.asarray(owner, dtype=np.int64)
    neighbour_arr = np.asarray(neighbour, dtype=np.int64)
    if len(owner_arr) != len(faces):
        raise ValueError(
            f"owner length {len(owner_arr)} != number of faces {len(faces)}"
        )
    if len(neighbour_arr) > len(faces):
        raise ValueError(
            f"neighbour length {len(neighbour_arr)} > number of faces {len(faces)}"
        )

    wall_set = {int(fi) for fi in wall_face_indices}
    for fi in wall_set:
        if fi < 0 or fi >= len(faces):
            raise ValueError(f"wall face index out of range: {fi}")
        if len(faces[fi]) != 3:
            raise ValueError(
                "bulk-preserving VD currently requires triangle wall faces; "
                f"face {fi} has {len(faces[fi])} vertices"
            )

    multi = build_multi_layer_bl(
        wall_face_indices,
        faces,
        points,
        junction_info,
        num_layers=num_layers,
        first_layer_thickness=first_layer_thickness,
        growth_ratio=growth_ratio,
        vnorm=vnorm,
        cluster_cos=cluster_cos,
    )
    gap = _build_multi_layer_gap_bridge_cells(
        wall_face_indices,
        faces,
        multi,
        owner_arr,
    )

    n_cells = int(owner_arr.max()) + 1 if len(owner_arr) else 0
    if len(neighbour_arr):
        n_cells = max(n_cells, int(neighbour_arr.max()) + 1)
    bulk_cells: list[list[list[int]]] = [[] for _ in range(n_cells)]

    face_pos = {int(fi): i for i, fi in enumerate(wall_face_indices)}
    n_wall = len(wall_face_indices)

    def _innermost_cap_for_wall_face(fi: int) -> list[int]:
        pos = face_pos[int(fi)]
        cell_idx = (int(num_layers) - 1) * n_wall + pos
        top = list(multi.cell_face_verts[cell_idx][1])
        if len(top) != 3:
            raise ValueError(f"VD innermost cap for face {fi} is not triangular")
        # ``build_multi_layer_bl`` stores prism top as [i0, i2, i1] so it is
        # outward for the prism.  The bulk-side face needs the original wall
        # orientation [i0, i1, i2].
        return [int(top[0]), int(top[2]), int(top[1])]

    def _bulk_cut_topology() -> None:
        """Add VD edge/vertex cut faces to same-owner boundary bulk cells.

        The duplicated BL bridge cells expose innermost edge and vertex caps at
        the shrunken bulk interface.  A preserved bulk cell must include those
        cut faces too; replacing only the original wall triangle leaves the BL
        bridge caps as open boundary faces.
        """
        if os.environ.get("AUTO_TESSELL_BL_VD_VERTEX_FILL", "0") != "1":
            return
        if int(multi.num_layers) < 1:
            return

        edge_to_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
        edge_local_index: dict[tuple[int, int, int], int] = {}
        vertex_to_faces: dict[int, set[int]] = defaultdict(set)
        vertex_face_graph: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        for fi in wall_face_indices:
            f = [int(v) for v in faces[fi]]
            for v in f:
                vertex_to_faces[int(v)].add(int(fi))
            for i, v0 in enumerate(f):
                v1 = f[(i + 1) % len(f)]
                key = (min(v0, v1), max(v0, v1))
                edge_to_faces[key].append(int(fi))
                edge_local_index[(int(fi), key[0], key[1])] = i

        last_layer = int(multi.num_layers) - 1

        def _edge_vertex_map(fi: int, edge: tuple[int, int]) -> dict[int, tuple[int, int]]:
            pos = face_pos[int(fi)]
            cell_idx = last_layer * n_wall + pos
            side_idx = edge_local_index[(int(fi), edge[0], edge[1])]
            side = [int(v) for v in multi.cell_face_verts[cell_idx][2 + side_idx]]
            f = [int(v) for v in faces[int(fi)]]
            local = side_idx
            start = f[local]
            end = f[(local + 1) % len(f)]
            return {start: (side[0], side[3]), end: (side[1], side[2])}

        for edge, f_list in edge_to_faces.items():
            if len(f_list) != 2:
                continue
            f1, f2 = int(f_list[0]), int(f_list[1])
            if f1 not in face_pos or f2 not in face_pos:
                continue
            for vtx in edge:
                vertex_face_graph[int(vtx)][f1].add(f2)
                vertex_face_graph[int(vtx)][f2].add(f1)
            own1 = int(owner_arr[f1])
            own2 = int(owner_arr[f2])
            m1 = _edge_vertex_map(f1, edge)
            m2 = _edge_vertex_map(f2, edge)
            v, w = int(edge[0]), int(edge[1])
            _o1v, i1v = m1[v]
            _o1w, i1w = m1[w]
            _o2v, i2v = m2[v]
            _o2w, i2w = m2[w]
            if own1 == own2:
                if 0 <= own1 < len(bulk_cells):
                    bulk_cells[own1].append([i1v, i2v, i2w, i1w])
            elif (
                os.environ.get("AUTO_TESSELL_BL_VD_MIXED_OWNER_EDGE_CUT", "0") == "1"
                and 0 <= own1 < len(bulk_cells)
                and 0 <= own2 < len(bulk_cells)
                and len({i1v, i1w, i2v}) == 3
                and len({i1w, i2w, i2v}) == 3
            ):
                bulk_cells[own1].append([i1v, i1w, i2v])
                bulk_cells[own2].append([i1w, i2w, i2v])

        def _ordered_vertex_faces(v: int) -> list[int]:
            face_set = set(vertex_to_faces.get(v, set()))
            if len(face_set) < 3:
                return []
            owners = {int(owner_arr[fi]) for fi in face_set}
            if len(owners) != 1:
                return []
            graph = vertex_face_graph.get(v, {})
            if not graph:
                return []
            endpoints = [f for f in face_set if len(graph.get(f, set()) & face_set) == 1]
            start = min(endpoints or list(face_set))
            order: list[int] = []
            prev: int | None = None
            cur = start
            for _ in range(len(face_set) + 2):
                if cur in order:
                    break
                order.append(cur)
                nxts = [
                    n for n in sorted(graph.get(cur, set()))
                    if n in face_set and n != prev
                ]
                nxt = next((n for n in nxts if n not in order), None)
                if nxt is None:
                    break
                prev, cur = cur, nxt
            if len(order) != len(face_set):
                return []
            return order

        def _inner_vertex_for_face(fi: int, v: int) -> int | None:
            try:
                local = [int(x) for x in faces[int(fi)]].index(int(v))
            except ValueError:
                return None
            pos = face_pos[int(fi)]
            cell_idx = last_layer * n_wall + pos
            top = multi.cell_face_verts[cell_idx][1]
            inner_by_local = [int(top[0]), int(top[2]), int(top[1])]
            return inner_by_local[local]

        for vtx in sorted(vertex_to_faces):
            ordered = _ordered_vertex_faces(vtx)
            if len(ordered) < 3:
                continue
            owner_cell = int(owner_arr[ordered[0]])
            if owner_cell < 0 or owner_cell >= len(bulk_cells):
                continue
            ring = [_inner_vertex_for_face(fi, vtx) for fi in ordered]
            if any(vid is None for vid in ring):
                continue
            clean_ring: list[int] = []
            for vid in ring:
                if not clean_ring or clean_ring[-1] != int(vid):
                    clean_ring.append(int(vid))
            if len(clean_ring) > 1 and clean_ring[0] == clean_ring[-1]:
                clean_ring.pop()
            if len(clean_ring) >= 3 and len(set(clean_ring)) == len(clean_ring):
                bulk_cells[owner_cell].append(list(clean_ring))

    for fi, raw_face in enumerate(faces):
        own = int(owner_arr[fi])
        if own < 0 or own >= n_cells:
            raise ValueError(f"owner cell out of range for face {fi}: {own}")

        if fi in wall_set:
            bulk_cells[own].append(_innermost_cap_for_wall_face(fi))
            continue

        face = [int(v) for v in raw_face]
        bulk_cells[own].append(face)
        if fi < len(neighbour_arr):
            nbr = int(neighbour_arr[fi])
            if nbr < 0 or nbr >= n_cells:
                raise ValueError(f"neighbour cell out of range for face {fi}: {nbr}")
            bulk_cells[nbr].append(list(reversed(face)))

    _bulk_cut_topology()

    prism_cells = [[list(face) for face in cell] for cell in multi.cell_face_verts]
    n_prism = len(prism_cells)
    n_gap = len(gap.cell_face_verts)
    combined_cells = bulk_cells + prism_cells + gap.cell_face_verts
    cell_kinds = (
        ["bulk"] * len(bulk_cells)
        + ["prism"] * n_prism
        + ["gap_fill"] * n_gap
    )
    pm = cells_to_polymesh(
        combined_cells,
        multi.new_points,
        cell_kinds=cell_kinds,
    )
    return BulkPreservingFullBLResult(
        polymesh=pm,
        n_bulk_cells=len(bulk_cells),
        n_prism_cells=n_prism,
        n_gap_fill_cells=n_gap,
        junction_edges=list(gap.junction_edges),
    )
