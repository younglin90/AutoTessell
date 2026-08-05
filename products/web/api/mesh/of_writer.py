"""
Pure-Python OpenFOAM polyMesh writer for tetrahedral meshes.

No OpenFOAM tools required — writes all polyMesh files directly.

Usage:
    write_polymesh(vertices, tets, case_dir)

Output:
    case_dir/constant/polyMesh/{points, faces, owner, neighbour, boundary}
"""

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


_FOAM_HEADER = """\
/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           |
     \\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    location    "constant/polyMesh";
    object      {obj};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

"""


def write_polymesh(vertices: np.ndarray, tets: np.ndarray, case_dir: Path) -> dict:
    """
    Convert tet mesh to OpenFOAM polyMesh and write files.

    Args:
        vertices: (N, 3) float64 array of vertex coordinates
        tets:     (M, 4) int32 array of tet vertex indices
        case_dir: Path to OpenFOAM case directory

    Returns:
        {"num_cells": M, "num_faces": F, "num_internal_faces": I, "num_points": N}
    """
    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True, exist_ok=True)

    faces, owner, neighbour, n_internal = _build_face_tables(tets)

    _write_points(vertices, poly_dir / "points")
    _write_faces(faces, poly_dir / "faces")
    _write_labels(owner, poly_dir / "owner", "labelList")
    _write_labels(neighbour, poly_dir / "neighbour", "labelList")
    _write_boundary(n_internal, len(faces), poly_dir / "boundary")

    return {
        "num_cells": len(tets),
        "num_faces": len(faces),
        "num_internal_faces": n_internal,
        "num_points": len(vertices),
    }


# ---------------------------------------------------------------------------
# Face table construction
# ---------------------------------------------------------------------------

# The four triangular faces of a tetrahedron (outward-facing normals)
_TET_FACE_VERTS = [
    (1, 2, 3),
    (0, 3, 2),
    (0, 1, 3),
    (0, 2, 1),
]


def _build_face_tables(tets: np.ndarray):
    """
    Build owner, neighbour, and face lists from tet connectivity.

    OpenFOAM convention:
    - owner[f]     = cell with lower index (always defined)
    - neighbour[f] = cell with higher index (only for internal faces)
    - Internal faces come first, boundary faces last
    - owner array must be sorted (ascending) for internal faces
    """
    # Map canonical (sorted) face -> list of (cell_idx, ordered_face)
    face_map: dict[tuple, list] = {}

    for cell_idx, tet in enumerate(tets):
        for local_verts in _TET_FACE_VERTS:
            ordered = tuple(int(tet[i]) for i in local_verts)
            key = tuple(sorted(ordered))
            if key not in face_map:
                face_map[key] = []
            face_map[key].append((cell_idx, ordered))

    internal: list[tuple] = []  # (owner_cell, neighbour_cell, face_verts)
    boundary: list[tuple] = []  # (owner_cell, face_verts)

    non_manifold_count = 0
    for cells in face_map.values():
        if len(cells) == 2:
            c0, f0 = cells[0]
            c1, f1 = cells[1]
            if c0 < c1:
                internal.append((c0, c1, f0))
            else:
                internal.append((c1, c0, f1))
        elif len(cells) == 1:
            c0, f0 = cells[0]
            boundary.append((c0, f0))
        else:
            # Non-manifold edge: face shared by 3+ cells — degenerate mesh.
            non_manifold_count += 1
            c0, f0 = cells[0]
            boundary.append((c0, f0))

    if non_manifold_count:
        log.warning(
            "%d non-manifold face(s) detected in tet mesh — "
            "mesh quality may be poor; consider re-running STL repair",
            non_manifold_count,
        )

    # Sort internal faces by owner cell (OpenFOAM requirement)
    internal.sort(key=lambda x: (x[0], x[1]))

    faces = [f[2] for f in internal] + [f[1] for f in boundary]
    owner = [f[0] for f in internal] + [f[0] for f in boundary]
    neighbour = [f[1] for f in internal]
    n_internal = len(internal)

    return faces, owner, neighbour, n_internal


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------

def _write_points(vertices: np.ndarray, path: Path) -> None:
    header = _FOAM_HEADER.format(cls="vectorField", obj="points")
    with open(path, "w") as f:
        f.write(header)
        f.write(f"{len(vertices)}\n(\n")
        for x, y, z in vertices:
            f.write(f"({x:.10g} {y:.10g} {z:.10g})\n")
        f.write(")\n")


def _write_faces(faces: list, path: Path) -> None:
    header = _FOAM_HEADER.format(cls="faceList", obj="faces")
    with open(path, "w") as f:
        f.write(header)
        f.write(f"{len(faces)}\n(\n")
        for verts in faces:
            f.write(f"{len(verts)}({' '.join(str(v) for v in verts)})\n")
        f.write(")\n")


def _write_labels(labels: list, path: Path, cls: str) -> None:
    obj = path.name
    header = _FOAM_HEADER.format(cls=cls, obj=obj)
    with open(path, "w") as f:
        f.write(header)
        f.write(f"{len(labels)}\n(\n")
        for v in labels:
            f.write(f"{v}\n")
        f.write(")\n")


def _write_boundary(n_internal: int, n_faces: int, path: Path) -> None:
    """Write boundary file — single 'walls' patch covering all boundary faces."""
    n_boundary = n_faces - n_internal
    header = _FOAM_HEADER.format(cls="polyBoundaryMesh", obj="boundary")
    with open(path, "w") as f:
        f.write(header)
        f.write("1\n(\n")
        f.write("    walls\n    {\n")
        f.write("        type            wall;\n")
        f.write(f"        nFaces          {n_boundary};\n")
        f.write(f"        startFace       {n_internal};\n")
        f.write("    }\n")
        f.write(")\n")
