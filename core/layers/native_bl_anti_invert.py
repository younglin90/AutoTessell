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


def compute_joint_cell_inversion_scale(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    wall_vert_indices: list[int] | set[int],
    motion_dirs: dict[int, np.ndarray],
    requested_extrusion: dict[int, float],
    *,
    safety_factor: float = 0.5,
    max_bisection_iter: int = 20,
) -> float:
    """BLR-9c-d-q-1: joint multi-wall-vertex cap via bisection.

    The single-vertex ``compute_anti_invert_caps`` assumes only one
    wall vertex of a tet moves at a time (other 3 vertices stay
    fixed).  In real BL extrusion *all* wall verts of a tet move
    simultaneously.  When two or more wall verts of the same tet
    move jointly, the cell can invert even if every individual
    single-vertex cap is satisfied.

    This helper computes the maximum *uniform* scale ``s ∈ [0, 1]``
    such that, for **every** cell in the polyMesh, applying
    ``v_new = v + s · requested_extrusion[v] · motion_dirs[v]`` to
    every wall vertex of that cell keeps the cell's signed volume
    positive.  Bisection on ``s`` finds the largest safe scale.

    Returns
    -------
    float
        Joint scale in ``[0, 1]``.  ``1.0`` means no cell would
        invert at full requested extrusion.

    Parameters
    ----------
    requested_extrusion:
        ``v → magnitude`` of the wall vertex's *target* extrusion
        in the absence of any cap.  ``motion_dirs[v]`` should be a
        unit vector; if not, the magnitude is interpreted relative
        to its norm.
    safety_factor:
        After bisection finds the safe maximum ``s_max``, the
        returned scale is ``s_max * safety_factor`` (default 0.5).
    """
    pts = np.asarray(points, dtype=np.float64)
    own = np.asarray(owner, dtype=np.int64)
    nbr = np.asarray(neighbour, dtype=np.int64)
    n_cells = max(
        int(own.max()) if own.size else -1,
        int(nbr.max()) if nbr.size else -1,
    ) + 1
    cell_verts = _build_cell_vertices(faces, own, nbr, n_cells)
    wall_set = set(int(v) for v in wall_vert_indices)
    if not wall_set or n_cells == 0:
        return 1.0

    # Per-cell wall vert ids and their motion + magnitude.
    cell_wall_data: list[tuple[list[int], np.ndarray, np.ndarray]] = []
    cell_bulk_idx: list[np.ndarray] = []
    cell_all_idx: list[np.ndarray] = []
    for cid in range(n_cells):
        cv = cell_verts[cid]
        if len(cv) != 4:
            cell_wall_data.append(([], np.zeros((0, 3)), np.zeros(0)))
            cell_bulk_idx.append(np.zeros(0, dtype=np.int64))
            cell_all_idx.append(np.zeros(0, dtype=np.int64))
            continue
        verts_sorted = sorted(cv)
        wall_in_cell: list[int] = []
        bulk_in_cell: list[int] = []
        for v in verts_sorted:
            if v in wall_set:
                wall_in_cell.append(v)
            else:
                bulk_in_cell.append(v)
        if not wall_in_cell:
            cell_wall_data.append(([], np.zeros((0, 3)), np.zeros(0)))
            cell_bulk_idx.append(
                np.asarray(bulk_in_cell, dtype=np.int64)
            )
            cell_all_idx.append(
                np.asarray(verts_sorted, dtype=np.int64)
            )
            continue
        # Per-wall-vert: unit motion direction × requested magnitude.
        dirs_arr = np.zeros((len(wall_in_cell), 3), dtype=np.float64)
        mags_arr = np.zeros(len(wall_in_cell), dtype=np.float64)
        for i, v in enumerate(wall_in_cell):
            d = motion_dirs.get(v) if motion_dirs else None
            if d is None:
                continue
            d_arr = np.asarray(d, dtype=np.float64).reshape(3)
            dn = float(np.linalg.norm(d_arr))
            if dn < 1e-30:
                continue
            dirs_arr[i] = d_arr / dn
            mags_arr[i] = float(requested_extrusion.get(int(v), 0.0))
        cell_wall_data.append(
            (wall_in_cell, dirs_arr, mags_arr)
        )
        cell_bulk_idx.append(
            np.asarray(bulk_in_cell, dtype=np.int64)
        )
        cell_all_idx.append(
            np.asarray(verts_sorted, dtype=np.int64)
        )

    def _all_cells_positive(s: float) -> bool:
        """Apply scale ``s`` to every wall vert and check whether
        every tet cell's signed volume stays positive."""
        for cid in range(n_cells):
            wall_in_cell, dirs_arr, mags_arr = cell_wall_data[cid]
            all_idx = cell_all_idx[cid]
            if all_idx.size != 4:
                continue
            disp = pts[all_idx].copy()
            for i, v in enumerate(wall_in_cell):
                pos_in_cell = int(np.where(all_idx == v)[0][0])
                disp[pos_in_cell] = (
                    pts[v] + s * mags_arr[i] * dirs_arr[i]
                )
            v0, v1, v2, v3 = disp[0], disp[1], disp[2], disp[3]
            sv = float(np.dot(v1 - v0, np.cross(v2 - v0, v3 - v0)))
            # Maintain the *original* sign — if the original tet
            # was positive, stay positive; if negative, stay
            # negative (the original mesh already satisfied this
            # invariant after PolyMeshWriter normalisation).
            sv_orig = float(np.dot(
                pts[all_idx[1]] - pts[all_idx[0]],
                np.cross(
                    pts[all_idx[2]] - pts[all_idx[0]],
                    pts[all_idx[3]] - pts[all_idx[0]],
                ),
            ))
            if sv_orig > 0 and sv <= 1e-30:
                return False
            if sv_orig < 0 and sv >= -1e-30:
                return False
        return True

    # Bisection: find the largest s in [0, 1] keeping all cells positive.
    # If full extrusion is already safe, no cap is needed (return 1.0).
    if _all_cells_positive(1.0):
        return 1.0
    s_lo, s_hi = 0.0, 1.0
    for _ in range(max_bisection_iter):
        s_mid = 0.5 * (s_lo + s_hi)
        if _all_cells_positive(s_mid):
            s_lo = s_mid
        else:
            s_hi = s_mid
    return s_lo * float(safety_factor)


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

    # Pre-compute per-cell opposite-face vertex tuples keyed by the
    # *missing* vertex, so each (vertex, cell) lookup is O(1).
    # cell_opposite[cid][v] = (i, j, k) such that cv[cid] - {v} = {i, j, k}.
    cell_opposite: dict[int, dict[int, tuple[int, int, int]]] = {}
    for cid in range(len(cell_verts)):
        cv = cell_verts[cid]
        if len(cv) != 4:
            continue
        # Iterate the cell's faces once and tag each by the missing
        # cell vertex (the vertex of the cell *not* on this face).
        cf_map: dict[int, tuple[int, int, int]] = {}
        for fi in cell_faces[cid]:
            f = faces[fi]
            if len(f) != 3:
                continue
            f_tuple = (int(f[0]), int(f[1]), int(f[2]))
            f_set = set(f_tuple)
            missing = cv - f_set
            if len(missing) == 1:
                cf_map[next(iter(missing))] = f_tuple
        cell_opposite[cid] = cf_map

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
        v0 = pts[v]

        adjacent_cells = vert_cells.get(v, [])
        cap_v = float("inf")
        for cid in adjacent_cells:
            cf_map = cell_opposite.get(cid)
            if cf_map is None:
                continue
            opp = cf_map.get(v)
            if opp is None:
                continue
            v1 = pts[opp[0]]
            v2 = pts[opp[1]]
            v3 = pts[opp[2]]
            n_opp = np.cross(v2 - v1, v3 - v1)
            old_vol6 = float(np.dot(v0 - v1, n_opp))   # 6 × signed volume
            d_dot_n = float(np.dot(d_unit, n_opp))
            if d_dot_n >= 0.0:
                continue
            if old_vol6 <= 0.0:
                cap_v = min(cap_v, 0.0)
                continue
            t_critical = -old_vol6 / d_dot_n
            cap_v = min(cap_v, t_critical * float(safety_factor))
        caps[v] = cap_v if cap_v != float("inf") else float("inf")
    return caps
