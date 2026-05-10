"""BLR-9c-d-p-9 — per-vertex anti-invert extrusion cap.

When ``native_bl`` extrudes a wall vertex inward by
``total_thickness * motion_dir``, an adjacent bulk tet can flip
sign once the wall vertex crosses the plane of the tet's
opposite face.  Bench measurements (BLR-9c-d-p-7 root cause)
show this is the dominant failure mode on 7/8 failing 21-STL
cases.

This helper computes, *per wall vertex*, the maximum extrusion
distance along ``motion_dir`` that keeps every adjacent bulk
tet's signed volume positive.  Caller should multiply each
wall vertex's requested thickness by ``min(1, cap[v] / requested[v])``
or similar.

Math
----

For a tet with vertices ``(V0, V1, V2, V3)`` where ``V0`` is the
wall vertex being extruded along unit direction ``d``, the
opposite face is ``(V1, V2, V3)`` with un-normalized normal

    n_opp = (V2 - V1) × (V3 - V1)

Signed volume

    V(t) = ((V0 + t·d) - V1) · n_opp / 6
         = V(0) + t · (d · n_opp) / 6

Initial volume ``V(0) > 0`` by construction (the polyMesh writer
already normalised winding).  We require ``V(t) > 0`` ∀ t ≤ t_max,
which gives

    if d · n_opp ≥ 0:  t_max = ∞  (extrusion safe — vol grows)
    if d · n_opp < 0:  t_max = -6·V(0) / (d · n_opp)

Per-vertex cap = ``min`` over every adjacent bulk tet of
``t_max``, with a safety factor of ``safety`` (default 0.95).
"""
from __future__ import annotations

from typing import Iterable

import numpy as np


def _build_cell_vertices(
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
) -> list[set[int]]:
    """Per-cell unique vertex set, derived from face vertices."""
    cell_verts: list[set[int]] = [set() for _ in range(n_cells)]
    n_internal = int(neighbour.shape[0])
    for fi, f in enumerate(faces):
        cell_verts[int(owner[fi])].update(int(v) for v in f)
        if fi < n_internal:
            cell_verts[int(neighbour[fi])].update(int(v) for v in f)
    return cell_verts


def _build_vertex_cells(
    cell_verts: list[set[int]],
) -> dict[int, list[int]]:
    """Reverse map: vertex id → list of cell ids that include it."""
    vert_cells: dict[int, list[int]] = {}
    for cid, vs in enumerate(cell_verts):
        for v in vs:
            vert_cells.setdefault(v, []).append(cid)
    return vert_cells


def _build_cell_face_indices(
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
) -> list[list[int]]:
    """Per-cell face index list."""
    cell_faces: list[list[int]] = [[] for _ in range(n_cells)]
    n_internal = int(neighbour.shape[0])
    for fi in range(len(faces)):
        cell_faces[int(owner[fi])].append(fi)
        if fi < n_internal:
            cell_faces[int(neighbour[fi])].append(fi)
    return cell_faces


def compute_anti_invert_caps(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    wall_vert_indices: Iterable[int],
    motion_dirs: dict[int, np.ndarray],
    *,
    safety_factor: float = 0.95,
) -> dict[int, float]:
    """Per-wall-vertex extrusion cap so no adjacent bulk tet flips.

    Returns
    -------
    dict[int, float]
        ``cap[v] = max safe extrusion distance along motion_dirs[v]``.
        Wall vertices whose every adjacent cell is a non-tet (4
        unique verts) or whose motion is collinear with every
        opposite-face plane (no constraint) get a sentinel
        ``float("inf")``.

    Parameters
    ----------
    points:
        ``(N, 3)`` polyMesh point coordinates.
    faces:
        polyMesh face vertex lists.
    owner, neighbour:
        polyMesh face owner/neighbour arrays (int).
    wall_vert_indices:
        Wall vertex ids that will be extruded.
    motion_dirs:
        Per-wall-vertex unit motion vector (extrusion direction).
        Vertices missing from ``motion_dirs`` get an ``inf`` cap.
    safety_factor:
        Multiplier applied to the geometric ``t_critical``.  0.95
        leaves a 5 % margin so the tet stays measurably
        positive.
    """
    pts = np.asarray(points, dtype=np.float64)
    own = np.asarray(owner, dtype=np.int64)
    nbr = np.asarray(neighbour, dtype=np.int64)
    n_cells = max(
        int(own.max()) if own.size else -1,
        int(nbr.max()) if nbr.size else -1,
    ) + 1
    cell_verts = _build_cell_vertices(faces, own, nbr, n_cells)
    vert_cells = _build_vertex_cells(cell_verts)
    cell_faces = _build_cell_face_indices(faces, own, nbr, n_cells)

    caps: dict[int, float] = {}
    for v in wall_vert_indices:
        v = int(v)
        d = motion_dirs.get(v) if motion_dirs else None
        if d is None:
            caps[v] = float("inf")
            continue
        d_arr = np.asarray(d, dtype=np.float64).reshape(3)
        d_norm = float(np.linalg.norm(d_arr))
        if d_norm < 1e-30:
            caps[v] = float("inf")
            continue
        d_unit = d_arr / d_norm

        adjacent_cells = vert_cells.get(v, [])
        cap_v = float("inf")
        for cid in adjacent_cells:
            cv = cell_verts[cid]
            if v not in cv or len(cv) != 4:
                continue   # non-tet or v not in cell
            # Find the opposite face: the cell face whose vertex
            # set does not include v.
            opp_face_verts: list[int] | None = None
            for fi in cell_faces[cid]:
                f_set = set(int(x) for x in faces[fi])
                if v not in f_set:
                    opp_face_verts = list(faces[fi])
                    break
            if opp_face_verts is None or len(opp_face_verts) != 3:
                continue
            v1 = pts[opp_face_verts[0]]
            v2 = pts[opp_face_verts[1]]
            v3 = pts[opp_face_verts[2]]
            n_opp = np.cross(v2 - v1, v3 - v1)
            v0 = pts[v]
            old_vol6 = float(np.dot(v0 - v1, n_opp))   # 6 × signed volume
            d_dot_n = float(np.dot(d_unit, n_opp))
            if d_dot_n >= 0.0:
                # Extrusion increases (or doesn't change) volume.
                continue
            if old_vol6 <= 0.0:
                # Tet is already inverted/degenerate — can't help here.
                cap_v = min(cap_v, 0.0)
                continue
            t_critical = -old_vol6 / d_dot_n   # > 0
            cap_v = min(cap_v, t_critical * float(safety_factor))
        caps[v] = cap_v if cap_v != float("inf") else float("inf")
    return caps
