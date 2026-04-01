"""OpenFOAM polyMesh writer for tetrahedral meshes.

Converts numpy tet mesh arrays (vertices, tets) into the five files that
OpenFOAM expects under ``constant/polyMesh/``:
    points, faces, owner, neighbour, boundary

No external tools (OpenFOAM, meshio) are required.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import numpy as np

from core.utils.logging import get_logger

logger = get_logger(__name__)

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


class _FaceRecord(NamedTuple):
    """Stores which cells own/neighbor a face (using global vertex indices)."""
    verts: tuple[int, ...]   # sorted tuple — canonical key
    owner: int               # cell with smaller index (or only cell)
    neighbour: int           # cell with larger index, -1 for boundary


def _canonical(v0: int, v1: int, v2: int) -> tuple[int, int, int]:
    """Return sorted (min, mid, max) tuple as canonical face key."""
    a, b, c = sorted((v0, v1, v2))
    return (a, b, c)


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


class PolyMeshWriter:
    """Writes an OpenFOAM polyMesh directory from raw tet mesh data.

    Algorithm
    ---------
    0.  Normalize tet winding so every cell has a positive (right-handed)
        volume.  Negative tets produce inward face normals via ``_TET_FACES``
        and cause OpenFOAM checkMesh face-orientation and negative-volume
        errors.
    1.  For every tet cell enumerate 4 triangular faces using the outward
        normal convention encoded in ``_TET_FACES``.
    2.  Track which cells share each face (canonical sorted-vertex key).
    3.  Faces seen by 2 cells → internal; by 1 cell → boundary.
    4.  For internal faces: the stored orientation is outward from the
        *generating* cell (the first cell to register the face, which is
        always the lower-ID cell = owner since we iterate in order).  If the
        generator happens to be the neighbour instead, reverse the winding.
    5.  Sort internal faces by (owner, neighbour).
    6.  Append boundary faces sorted by owner.
    7.  Write ``points``, ``faces``, ``owner``, ``neighbour``, ``boundary``.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(
        self,
        vertices: np.ndarray,
        tets: np.ndarray,
        case_dir: Path,
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
        vertices = np.asarray(vertices, dtype=float)
        tets = np.asarray(tets, dtype=int)

        # Step 0: normalise tet winding so all cells have positive volume.
        # Tets from external tools (pytetwild, Netgen …) may have inconsistent
        # vertex ordering; negative-volume tets cause inward face normals which
        # lead to checkMesh "incorrectly oriented" and "negative volume" errors.
        tets = _normalize_tet_winding(vertices, tets)

        poly_dir = case_dir / "constant" / "polyMesh"
        poly_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "polymesh_writer_start",
            num_points=len(vertices),
            num_cells=len(tets),
            poly_dir=str(poly_dir),
        )

        # Step 1-3: build face → cells mapping
        face_cells: dict[tuple[int, int, int], list[int]] = defaultdict(list)
        # Store the ordered (non-canonical) vertices and the generating cell for
        # each canonical key.  We record the orientation from the *first* cell
        # that registers the face together with that cell's ID so we can later
        # fix the winding for internal faces.
        face_ordered: dict[tuple[int, int, int], tuple[int, int, int]] = {}
        face_generator: dict[tuple[int, int, int], int] = {}  # canonical key → generating cell ID

        for cell_id, tet in enumerate(tets):
            for lf in _TET_FACES:
                gv = (int(tet[lf[0]]), int(tet[lf[1]]), int(tet[lf[2]]))
                key = _canonical(*gv)
                face_cells[key].append(cell_id)
                if key not in face_ordered:
                    face_ordered[key] = gv
                    face_generator[key] = cell_id

        # Step 4-5: separate internal and boundary, then sort
        internal: list[tuple[int, int, tuple[int, int, int]]] = []  # (owner, neighbour, key)
        boundary: list[tuple[int, tuple[int, int, int]]] = []        # (owner, key)

        for key, cells in face_cells.items():
            if len(cells) == 2:
                own = min(cells[0], cells[1])
                nbr = max(cells[0], cells[1])
                internal.append((own, nbr, key))
            else:
                boundary.append((cells[0], key))

        # Sort internal by (owner, neighbour) so OpenFOAM's consistency check passes
        internal.sort(key=lambda x: (x[0], x[1]))
        # Sort boundary by owner
        boundary.sort(key=lambda x: x[0])

        n_internal = len(internal)
        n_boundary = len(boundary)
        n_faces = n_internal + n_boundary

        # Build flat lists for writing
        all_face_verts: list[tuple[int, int, int]] = []
        owner_list: list[int] = []
        neighbour_list: list[int] = []

        for own, nbr, key in internal:
            verts = face_ordered[key]
            # The stored orientation is outward from face_generator[key].
            # OpenFOAM requires the face normal to point from owner toward
            # neighbour (i.e. outward from the owner cell).
            # If the stored orientation came from the neighbour cell it points
            # *toward* the owner → reverse it so it points toward the neighbour.
            if face_generator[key] != own:
                verts = (verts[2], verts[1], verts[0])
            all_face_verts.append(verts)
            owner_list.append(own)
            neighbour_list.append(nbr)

        for own, key in boundary:
            all_face_verts.append(face_ordered[key])
            owner_list.append(own)

        # Write all files
        self._write_points(poly_dir, vertices)
        self._write_faces(poly_dir, all_face_verts)
        self._write_owner(poly_dir, owner_list, len(vertices), n_faces, len(tets), n_internal)
        self._write_neighbour(poly_dir, neighbour_list, n_internal)
        self._write_boundary(poly_dir, n_boundary, n_internal)

        # system/ 파일 생성 (checkMesh 등에 필요)
        self._ensure_system_files(case_dir)

        stats = {
            "num_cells": len(tets),
            "num_points": len(vertices),
            "num_faces": n_faces,
            "num_internal_faces": n_internal,
        }
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
                + "    \"div((nuEff*dev2(T(grad(U)))))\" Gauss linear;\n"
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
                + "    U { solver smoothSolver; smoother GaussSeidel; tolerance 1e-06; relTol 0.1; }\n"
                + "    k { solver smoothSolver; smoother GaussSeidel; tolerance 1e-06; relTol 0.1; }\n"
                + "    omega { solver smoothSolver; smoother GaussSeidel; tolerance 1e-06; relTol 0.1; }\n"
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

    # ------------------------------------------------------------------
    # File writers
    # ------------------------------------------------------------------

    def _write_points(self, poly_dir: Path, vertices: np.ndarray) -> None:
        n = len(vertices)
        lines = [_header("vectorField", "constant/polyMesh", "points")]
        lines.append(f"{n}")
        lines.append("(")
        for v in vertices:
            lines.append(f"({v[0]:.10g} {v[1]:.10g} {v[2]:.10g})")
        lines.append(")")
        lines.append(_FOOTER)
        (poly_dir / "points").write_text("\n".join(lines))
        logger.debug("wrote_points", path=str(poly_dir / "points"), n=n)

    def _write_faces(
        self,
        poly_dir: Path,
        face_verts: list[tuple[int, int, int]],
    ) -> None:
        n = len(face_verts)
        lines = [_header("faceList", "constant/polyMesh", "faces")]
        lines.append(f"{n}")
        lines.append("(")
        for f in face_verts:
            lines.append(f"3({f[0]} {f[1]} {f[2]})")
        lines.append(")")
        lines.append(_FOOTER)
        (poly_dir / "faces").write_text("\n".join(lines))
        logger.debug("wrote_faces", path=str(poly_dir / "faces"), n=n)

    def _write_owner(
        self,
        poly_dir: Path,
        owner_list: list[int],
        n_points: int,
        n_faces: int,
        n_cells: int,
        n_internal_faces: int,
    ) -> None:
        n = len(owner_list)
        # note field goes inside FoamFile header
        note = (
            f"nPoints:{n_points}  nCells:{n_cells}  "
            f"nFaces:{n_faces}  nInternalFaces:{n_internal_faces}"
        )
        header = _FOAM_HEADER.format(
            foam_class="labelList",
            location="constant/polyMesh",
            object_name="owner",
        ).replace(
            "    object      owner;",
            f"    note        \"{note}\";\n    object      owner;",
        )
        lines = [header]
        lines.append(f"{n}")
        lines.append("(")
        for o in owner_list:
            lines.append(str(o))
        lines.append(")")
        lines.append(_FOOTER)
        (poly_dir / "owner").write_text("\n".join(lines))
        logger.debug("wrote_owner", path=str(poly_dir / "owner"), n=n)

    def _write_neighbour(
        self,
        poly_dir: Path,
        neighbour_list: list[int],
        n_internal: int,
    ) -> None:
        lines = [_header("labelList", "constant/polyMesh", "neighbour")]
        lines.append(f"{n_internal}")
        lines.append("(")
        for nb in neighbour_list:
            lines.append(str(nb))
        lines.append(")")
        lines.append(_FOOTER)
        (poly_dir / "neighbour").write_text("\n".join(lines))
        logger.debug("wrote_neighbour", path=str(poly_dir / "neighbour"), n=n_internal)

    def _write_boundary(
        self,
        poly_dir: Path,
        n_boundary: int,
        start_face: int,
    ) -> None:
        lines = [_header("polyBoundaryMesh", "constant/polyMesh", "boundary")]
        lines.append("1")
        lines.append("(")
        lines.append("    defaultWall")
        lines.append("    {")
        lines.append("        type wall;")
        lines.append(f"        nFaces {n_boundary};")
        lines.append(f"        startFace {start_face};")
        lines.append("    }")
        lines.append(")")
        lines.append(_FOOTER)
        (poly_dir / "boundary").write_text("\n".join(lines))
        logger.debug(
            "wrote_boundary",
            path=str(poly_dir / "boundary"),
            n_boundary=n_boundary,
            start_face=start_face,
        )
