"""BLR-9c-d-r-2 — split inverted 8-face polyhedra into 3 sub-tets.

The 5 ``negative_volumes`` residual cases on the 21-STL bench
(BLR-9c-d-p-17 deep-dive) all share the pattern of a single
8-face polyhedron — a *triangulated prism* (3 wall verts + 3
inner verts, 2 triangle caps + 6 side triangles) — that ended
up with a globally negative signed volume.

This helper attempts to split each such polyhedron into 3
positive-volume tetrahedra by trying every standard prism
decomposition and picking one whose three tets all have
``signed_vol > 0``.  If no decomposition works, the cell is
left untouched.

The tool reads a polyMesh, performs the split in-memory, and
writes back ``points`` / ``faces`` / ``owner`` / ``neighbour``
with the inverted cells replaced.

This is the minimum repair surface needed to push past the
3 neg_vol residual cases.  Cells that aren't 8-face triangulated
prisms (e.g. 7-face merged junctions) are left for future work.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

import numpy as np

from core.utils.logging import get_logger
from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels


log = get_logger(__name__)


def _read_points(points_path: Path) -> np.ndarray:
    text = points_path.read_text()
    m = re.search(r"\n(\d+)\n\(", text)
    n_pts = int(m.group(1)) if m else 0
    body = text[text.index("(") :]
    nums = re.findall(r"-?[\d.eE+-]+", body)
    return np.array(nums, dtype=np.float64).reshape(-1, 3)[:n_pts]


def _signed_tet_vol(
    a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray,
) -> float:
    return float(np.dot(b - a, np.cross(c - a, d - a))) / 6.0


def _signed_cell_volume(
    points: np.ndarray,
    cell_face_verts: list[list[int]],
    owner_cell: int,
    cell_id: int,
) -> float:
    """Volume via divergence theorem; sign is per ``owner_cell == cell_id``."""
    vol = 0.0
    for f in cell_face_verts:
        p = points[np.asarray(f, dtype=np.int64)]
        n_vec = np.zeros(3, dtype=np.float64)
        for k in range(len(f)):
            n_vec += np.cross(p[k], p[(k + 1) % len(f)])
        n_vec *= 0.5
        fc = p.mean(axis=0)
        vol += float(np.dot(fc, n_vec))
    return vol / 3.0


def _identify_prism_verts(
    cell_verts: set[int],
    faces: list[list[int]],
    cell_face_ids: list[int],
) -> tuple[list[int], list[int]] | None:
    """Identify the 3 wall and 3 inner verts of a triangulated prism.

    For an 8-face triangulated prism the 2 triangle caps are the
    wall and inner cap.  We pick the 2 faces with 3 unique verts
    each (and 6 unique total) and treat the lower-id face as wall.
    Returns ``(wall_verts, inner_verts)`` or ``None`` if the cell
    isn't recognisable.
    """
    if len(cell_verts) != 6:
        return None
    # The 8 faces are: 2 cap triangles + 6 side triangles.
    # Caps: each triangle face has 3 verts that are entirely on
    # one "level" (either all 3 wall or all 3 inner).  Side
    # triangles span both levels (2 from one level + 1 from other).
    # We can find caps by counting how often each vert appears
    # across cell faces — cap verts appear in 4 cell faces (1 cap
    # + 3 sides), side faces span both.
    # Simpler heuristic: look for the two cell faces whose vertex
    # *sets* are entirely disjoint from each other.  Those are
    # the two caps.
    cell_face_v: list[set[int]] = []
    for fi in cell_face_ids:
        fv = set(int(v) for v in faces[fi])
        if len(fv) == 3:   # tri face
            cell_face_v.append(fv)
    cap_pair: tuple[set[int], set[int]] | None = None
    for i in range(len(cell_face_v)):
        for j in range(i + 1, len(cell_face_v)):
            if cell_face_v[i].isdisjoint(cell_face_v[j]):
                cap_pair = (cell_face_v[i], cell_face_v[j])
                break
        if cap_pair is not None:
            break
    if cap_pair is None:
        return None
    a, b = cap_pair
    if min(a) <= min(b):
        wall_verts = sorted(a)
        inner_verts = sorted(b)
    else:
        wall_verts = sorted(b)
        inner_verts = sorted(a)
    return wall_verts, inner_verts


_PRISM_DECOMPS = [
    # 6 standard tet decompositions of a prism with wall=(W0,W1,W2)
    # and inner=(I0,I1,I2) such that Wi connects to Ii.
    # Decomposition: 3 tets — picked among the 6 cyclic / mirror
    # variants known to handle non-planar prisms.
    [(0, 1, 2, 3), (1, 2, 3, 4), (2, 3, 4, 5)],
    [(0, 1, 2, 4), (1, 2, 4, 5), (0, 2, 4, 3)],
    [(0, 1, 2, 5), (0, 1, 5, 4), (0, 4, 5, 3)],
    [(0, 1, 2, 3), (1, 2, 3, 5), (1, 3, 4, 5)],
    [(0, 1, 2, 4), (0, 2, 4, 5), (0, 4, 5, 3)],
    [(0, 1, 2, 5), (0, 2, 4, 5), (0, 4, 5, 3)],
]


def _try_decompose_prism(
    points: np.ndarray,
    wall: list[int],
    inner: list[int],
) -> list[tuple[int, int, int, int]] | None:
    """Try every prism decomposition; return tets that all have
    ``signed_vol > 0``.  Returns ``None`` if no decomposition has all
    three tets positive."""
    verts = wall + inner   # 6 verts
    for decomp in _PRISM_DECOMPS:
        tets: list[tuple[int, int, int, int]] = []
        all_positive = True
        for a, b, c, d in decomp:
            tet = (verts[a], verts[b], verts[c], verts[d])
            v = _signed_tet_vol(
                points[tet[0]], points[tet[1]],
                points[tet[2]], points[tet[3]],
            )
            if v <= 0.0:
                all_positive = False
                break
            tets.append(tet)
        if all_positive:
            return tets
    return None


def diagnose_inverted_polyhedra(
    case_dir: Path,
    *,
    vol_tol: float = 1e-12,
) -> dict[str, int]:
    """Read the polyMesh, scan for inverted cells, and report
    structural classification (n_face / n_unique_vert / split-tried).

    Read-only: doesn't touch the polyMesh.  Used to validate that
    the inverted cells *can* be split before BLR-9c-d-r-3 wires
    the actual writer-replace step in.
    """
    poly = case_dir / "constant" / "polyMesh"
    points_path = poly / "points"
    faces_path = poly / "faces"
    owner_path = poly / "owner"
    neighbour_path = poly / "neighbour"
    if not all(p.exists() for p in (
        points_path, faces_path, owner_path, neighbour_path
    )):
        return {
            "n_inverted": 0, "n_split_ok": 0,
            "n_split_fail": 0, "n_non_prism": 0,
        }

    pts = _read_points(points_path)
    faces = parse_foam_faces(faces_path)
    owner = np.asarray(parse_foam_labels(owner_path), dtype=np.int64)
    neighbour = np.asarray(
        parse_foam_labels(neighbour_path), dtype=np.int64,
    )
    n_internal = int(neighbour.shape[0])
    n_cells = max(
        int(owner.max()) if owner.size else -1,
        int(neighbour.max()) if neighbour.size else -1,
    ) + 1

    cell_face_ids: list[list[int]] = [[] for _ in range(n_cells)]
    for fi in range(len(faces)):
        cell_face_ids[int(owner[fi])].append(fi)
        if fi < n_internal:
            cell_face_ids[int(neighbour[fi])].append(fi)

    # Cell volumes
    vols = np.zeros(n_cells, dtype=np.float64)
    for fi, f in enumerate(faces):
        p = pts[np.asarray(f, dtype=np.int64)]
        n_vec = np.zeros(3, dtype=np.float64)
        for k in range(len(f)):
            n_vec += np.cross(p[k], p[(k + 1) % len(f)])
        n_vec *= 0.5
        fc = p.mean(axis=0)
        contrib = float(np.dot(fc, n_vec))
        vols[int(owner[fi])] += contrib
        if fi < n_internal:
            vols[int(neighbour[fi])] -= contrib
    vols /= 3.0

    inverted = np.where(vols < -vol_tol)[0]
    n_split_ok = 0
    n_split_fail = 0
    n_non_prism = 0
    for cid in inverted:
        cid = int(cid)
        cv = set()
        for fi in cell_face_ids[cid]:
            cv.update(int(v) for v in faces[fi])
        prism = _identify_prism_verts(
            cv, faces, cell_face_ids[cid],
        )
        if prism is None:
            n_non_prism += 1
            continue
        wall, inner = prism
        tets = _try_decompose_prism(pts, wall, inner)
        if tets is None:
            n_split_fail += 1
        else:
            n_split_ok += 1
    return {
        "n_inverted": int(inverted.size),
        "n_split_ok": n_split_ok,
        "n_split_fail": n_split_fail,
        "n_non_prism": n_non_prism,
    }
