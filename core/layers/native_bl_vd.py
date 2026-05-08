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
