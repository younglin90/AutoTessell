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

    Returns:
        PolyMeshResult.

    Raises:
        ValueError: if any face appears in 3 or more cells (non-manifold).
    """
    occurrences: dict[tuple[int, ...], list[tuple[int, int, list[int]]]] = (
        defaultdict(list)
    )
    for cell_id, cf in enumerate(cell_face_verts):
        for face_idx, raw_verts in enumerate(cf):
            key = tuple(sorted(int(v) for v in raw_verts))
            occurrences[key].append((cell_id, face_idx, list(int(v) for v in raw_verts)))

    internal_records: list[tuple[int, int, list[int]]] = []
    # boundary buckets keyed by patch name to honor ordering convention.
    boundary_records: dict[str, list[tuple[int, list[int]]]] = {
        name: [] for name in _PATCH_ORDER
    }

    for key, occs in occurrences.items():
        if len(occs) == 1:
            cell_id, face_idx, raw_verts = occs[0]
            patch_name = _patch_for_face_idx(face_idx)
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
