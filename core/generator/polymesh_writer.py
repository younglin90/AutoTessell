"""OpenFOAM polyMesh writer.

Converts numpy mesh arrays into the five files that OpenFOAM expects under
``constant/polyMesh/``:
    points, faces, owner, neighbour, boundary

두 경로 제공:
    - ``PolyMeshWriter``: 전용 tet writer (하위 호환; 내부적으로 generic writer 호출).
    - ``write_generic_polymesh``: 임의 cell (tet/hex/poly 공용) writer. 호출 측이
      각 cell 의 외향 face vertex list 를 넘기면 face dedup + owner/neighbour 정렬을
      수행한다.

No external tools (OpenFOAM, meshio) are required.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import NamedTuple, Sequence

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


def write_generic_polymesh(
    vertices: np.ndarray,
    cell_faces: Sequence[Sequence[Sequence[int]]],
    case_dir: Path,
    *,
    patch_name: str = "defaultWall",
    patch_type: str = "wall",
) -> dict[str, int]:
    """Generic polyMesh writer — cell → list of face vertex lists.

    Args:
        vertices: (N, 3) float 좌표 배열.
        cell_faces: ``cell_faces[i]`` = cell i 를 구성하는 face 목록. 각 face 는
            vertex index 시퀀스 (길이 가변: 삼각형 3, 사각형 4, n-gon n).
            **각 face 는 소유 cell 외향 (CCW from outside) 으로 기록되어야 한다.**
        case_dir: 결과 case 디렉터리 — ``constant/polyMesh/`` 하위에 쓰기.
        patch_name / patch_type: 단일 boundary patch 설정 (기본 defaultWall/wall).

    Returns:
        ``{num_cells, num_points, num_faces, num_internal_faces}``.

    Algorithm:
        1. canonical key = tuple(sorted(face_verts)) 로 face dedup.
        2. 공유 2 cells → internal, 1 cell → boundary.
        3. internal face 의 orientation 은 owner cell 측 기록 그대로 사용 (owner
           외향 = owner→neighbour normal).
        4. internal sort by (owner, neighbour); boundary sort by owner.
        5. points/faces/owner/neighbour/boundary 파일 + 최소 system/ 쓰기.

    Non-manifold (3+ cells 공유) face 는 첫 2 cell 을 internal 로 선택하고 나머지는
    무시한다 (경고 로그 포함).
    """
    # Lazy imports — 순환 import 회피
    from core.generator.tier_layers_post import (  # noqa: PLC0415
        _ensure_minimal_controldict,
        _write_minimal_fv_dicts,
    )
    from core.layers.native_bl import (  # noqa: PLC0415
        _write_boundary,
        _write_faces,
        _write_labels,
        _write_points,
    )

    vertices_arr = np.asarray(vertices, dtype=np.float64)
    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True, exist_ok=True)
    _ensure_minimal_controldict(case_dir)
    _write_minimal_fv_dicts(case_dir)

    # face_map: canonical key → [(cell_id, ordered_verts), ...]
    face_map: dict[tuple[int, ...], list[tuple[int, list[int]]]] = defaultdict(list)
    for ci, faces_of_cell in enumerate(cell_faces):
        for f in faces_of_cell:
            verts = [int(v) for v in f]
            if len(verts) < 3:
                continue
            key = tuple(sorted(verts))
            face_map[key].append((ci, verts))

    internal_faces: list[list[int]] = []
    internal_owner: list[int] = []
    internal_nbr: list[int] = []
    boundary_faces: list[list[int]] = []
    boundary_owner: list[int] = []

    for key, refs in face_map.items():
        n_refs = len(refs)
        if n_refs == 2:
            (ca, fa), (cb, fb) = refs
        elif n_refs == 1:
            ci, fv = refs[0]
            boundary_faces.append(fv)
            boundary_owner.append(ci)
            continue
        else:
            # non-manifold: 첫 2 cell 만 internal 로 사용, 나머지 무시.
            logger.warning(
                "generic_polymesh_non_manifold_face",
                n_refs=n_refs,
                key_len=len(key),
            )
            (ca, fa), (cb, fb) = refs[0], refs[1]

        owner_c = min(ca, cb)
        nbr_c = max(ca, cb)
        f_use = fa if ca == owner_c else fb
        internal_faces.append(f_use)
        internal_owner.append(owner_c)
        internal_nbr.append(nbr_c)

    int_order = sorted(
        range(len(internal_faces)),
        key=lambda i: (internal_owner[i], internal_nbr[i]),
    )
    bnd_order = sorted(range(len(boundary_faces)), key=lambda i: boundary_owner[i])

    n_internal = len(int_order)
    final_faces = [internal_faces[i] for i in int_order] + [
        boundary_faces[i] for i in bnd_order
    ]
    final_owner = [internal_owner[i] for i in int_order] + [
        boundary_owner[i] for i in bnd_order
    ]
    final_nbr = [internal_nbr[i] for i in int_order]

    n_faces = len(final_faces)
    owner_note = (
        f"nPoints:{int(vertices_arr.shape[0])}  nCells:{len(cell_faces)}  "
        f"nFaces:{n_faces}  nInternalFaces:{n_internal}"
    )

    _write_points(poly_dir / "points", vertices_arr)
    _write_faces(poly_dir / "faces", final_faces)
    _write_labels(
        poly_dir / "owner",
        np.array(final_owner, dtype=np.int64),
        "owner",
        note=owner_note,
    )
    _write_labels(
        poly_dir / "neighbour",
        np.array(final_nbr, dtype=np.int64),
        "neighbour",
    )
    _write_boundary(
        poly_dir / "boundary",
        [
            {
                "name": patch_name,
                "type": patch_type,
                "nFaces": len(boundary_faces),
                "startFace": n_internal,
            }
        ],
    )

    return {
        "num_cells": len(cell_faces),
        "num_points": int(vertices_arr.shape[0]),
        "num_faces": len(final_faces),
        "num_internal_faces": n_internal,
    }


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
        vertices = np.asarray(vertices, dtype=np.float64)
        tets = np.asarray(tets, dtype=np.int64)

        # Step 0: normalise tet winding so all cells have positive volume.
        # Tets from external tools (pytetwild, Netgen …) may have inconsistent
        # vertex ordering; negative-volume tets cause inward face normals which
        # lead to checkMesh "incorrectly oriented" and "negative volume" errors.
        tets = _normalize_tet_winding(vertices, tets)

        logger.info(
            "polymesh_writer_start",
            num_points=len(vertices),
            num_cells=len(tets),
            case_dir=str(case_dir),
        )

        # Step 1: build cell_faces (각 cell 의 외향 face 4 개) — generic writer 위임.
        cell_faces: list[list[list[int]]] = []
        for tet in tets:
            faces = [
                [int(tet[lf[0]]), int(tet[lf[1]]), int(tet[lf[2]])]
                for lf in _TET_FACES
            ]
            cell_faces.append(faces)

        stats = write_generic_polymesh(vertices, cell_faces, case_dir)

        # Writer-specific system files (GAMG solver 등 tet 솔루션 설정) 덮어쓰기.
        # generic writer 의 최소 controlDict 는 generic 솔루션이므로, tet 전용
        # PolyMeshWriter 는 자체 고정 스펙을 유지해 하위 호환 보장.
        self._ensure_system_files(case_dir)

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
