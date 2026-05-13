"""U-3 unit tests for drop_neg_vol_cells."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.utils.drop_neg_vol_cells import drop_neg_vol_cells, _signed_cell_volumes
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
)


def _two_tet_polyMesh(tmp_path: Path, *, second_tet_inverted: bool) -> Path:
    """Create a tiny 2-tet polyMesh.  Optionally make tet 1 negative."""
    poly = tmp_path / "constant" / "polyMesh"
    poly.mkdir(parents=True)

    pts = np.array(
        [
            [0.0, 0.0, 0.0],   # 0
            [1.0, 0.0, 0.0],   # 1
            [0.0, 1.0, 0.0],   # 2
            [0.0, 0.0, 1.0],   # 3
            [1.0, 1.0, 1.0],   # 4 (apex of tet 1)
        ]
    )

    # tet 0 = (0, 1, 2, 3) standard.  Faces (outward):
    #   f0: 0-2-1 (bottom),  f1: 0-1-3 (front),
    #   f2: 0-3-2 (left),    f3: 1-2-3 (right) -- shared with tet 1
    # tet 1 vertices = (1, 2, 3, 4).  Outward faces:
    #   shared face = 1-3-2 (opposite to tet 0's 1-2-3).  Standard outward winding for tet 1 = (1,3,2)? Let's just orient by signed volume.
    #
    # If second_tet_inverted: shrink vertex 4 toward (1,2,3) centroid past plane.
    if second_tet_inverted:
        # Place 4 *inside* tet 0 -- volume of tet (1,2,3,4) becomes negative
        # (assuming our outward face convention).
        pts[4] = np.array([0.2, 0.2, 0.2])

    # Faces list (windings checked: outward normals point AWAY from cell centroid)
    faces: list[list[int]] = [
        # tet0 faces — outward
        [0, 2, 1],   # opposite v3
        [0, 1, 3],   # opposite v2
        [0, 3, 2],   # opposite v1
        [1, 2, 3],   # opposite v0 — shared with tet 1, owner=0 → nbr=1
        # tet1 unique faces (verts 1,2,3,4) — outward
        [2, 3, 4],   # opposite v1
        [1, 4, 3],   # opposite v2
        [1, 2, 4],   # opposite v3
    ]
    # owner/neighbour: face[3] is internal owner=0 nbr=1, others boundary owner only
    # OpenFOAM convention: internal faces first, boundary last.
    # Reorder so internal face is first.
    faces = [
        faces[3],   # internal
        faces[0], faces[1], faces[2],  # tet0 boundary
        faces[4], faces[5], faces[6],  # tet1 boundary
    ]
    owner = [0, 0, 0, 0, 1, 1, 1]
    neighbour = [1]
    # Boundary patch covering all 6 boundary faces
    patches = [{"name": "walls", "type": "wall", "nFaces": 6, "startFace": 1}]

    _write_test_polymesh(poly, pts, faces, owner, neighbour, patches)
    return tmp_path


def _write_test_polymesh(
    poly: Path,
    pts: np.ndarray,
    faces: list[list[int]],
    owner: list[int],
    neighbour: list[int],
    patches: list[dict],
) -> None:
    from core.utils.drop_neg_vol_cells import (
        _write_points, _write_faces, _write_labels, _write_boundary,
    )
    _write_points(poly / "points", pts)
    _write_faces(poly / "faces", faces)
    _write_labels(poly / "owner", owner, "owner")
    _write_labels(poly / "neighbour", neighbour, "neighbour")
    _write_boundary(poly / "boundary", patches)


def test_no_drop_when_all_positive(tmp_path):
    case = _two_tet_polyMesh(tmp_path, second_tet_inverted=False)
    res = drop_neg_vol_cells(case)
    assert res["n_dropped"] == 0
    assert res["n_cells_pre"] == 2
    assert res["n_cells_post"] == 2
    assert res["n_faces_pre"] == res["n_faces_post"]


def test_drop_one_inverted_tet(tmp_path):
    case = _two_tet_polyMesh(tmp_path, second_tet_inverted=True)
    res = drop_neg_vol_cells(case)
    assert res["n_dropped"] == 1, res
    assert res["n_cells_post"] == 1
    # 7 faces pre -> 4 faces post (3 boundary of tet0 + 1 new shell).
    assert res["n_faces_post"] == 4, res


def test_droppedShell_patch_added(tmp_path):
    case = _two_tet_polyMesh(tmp_path, second_tet_inverted=True)
    drop_neg_vol_cells(case)
    patches = parse_foam_boundary(
        case / "constant" / "polyMesh" / "boundary",
    )
    names = [p["name"] for p in patches]
    assert "droppedShell" in names


def test_no_negative_volume_after_drop(tmp_path):
    case = _two_tet_polyMesh(tmp_path, second_tet_inverted=True)
    drop_neg_vol_cells(case)
    poly = case / "constant" / "polyMesh"
    from core.utils.drop_neg_vol_cells import _read_points
    pts = _read_points(poly / "points")
    faces = [list(f) for f in parse_foam_faces(poly / "faces")]
    owner = np.asarray(parse_foam_labels(poly / "owner"), dtype=np.int64)
    neighbour = np.asarray(
        parse_foam_labels(poly / "neighbour"), dtype=np.int64,
    )
    n_cells = int(owner.max()) + 1
    vols = _signed_cell_volumes(pts, faces, owner, neighbour, n_cells)
    assert (vols > 0).all(), vols


def test_idempotent_when_clean(tmp_path):
    case = _two_tet_polyMesh(tmp_path, second_tet_inverted=False)
    drop_neg_vol_cells(case)
    res2 = drop_neg_vol_cells(case)
    assert res2["n_dropped"] == 0
