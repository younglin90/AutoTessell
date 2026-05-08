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
