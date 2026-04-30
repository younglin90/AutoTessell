"""J2 / beta2627 — Gambit .neu (Neutral) format writer.

Gambit Neutral format (legacy ANSYS Fluent / pre-2014 Gambit):
    헤더 → CONTROL INFO → NODAL COORDINATES → ELEMENTS/CELLS → BOUNDARY CONDITIONS.

레퍼런스: ANSYS Fluent 6.3 User's Guide "Gambit Neutral File Format" 부록.

본 구현: ASCII format. tet (type=6) / hex (type=4) / prism (type=5) / pyr (type=7).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class GambitNeuWriteResult:
    success: bool
    output_path: str = ""
    n_nodes: int = 0
    n_cells: int = 0
    n_groups: int = 0
    elapsed: float = 0.0
    message: str = ""


# Gambit ELEMENT TYPE codes.
GAMBIT_ELEM = {
    "edge": 1,
    "quad": 2,
    "tri": 3,
    "hex": 4,    # 8-node brick.
    "prism": 5,  # 6-node wedge.
    "tet": 6,    # 4-node tetrahedron.
    "pyr": 7,    # 5-node pyramid.
}


def _classify_gambit_cell(face_count: int, face_sizes: list[int]) -> tuple[int, int]:
    """Returns (gambit_elem_code, n_verts)."""
    if face_count == 4 and all(s == 3 for s in face_sizes):
        return (GAMBIT_ELEM["tet"], 4)
    if face_count == 5:
        n_tri = sum(1 for s in face_sizes if s == 3)
        n_quad = sum(1 for s in face_sizes if s == 4)
        if n_tri == 4 and n_quad == 1:
            return (GAMBIT_ELEM["pyr"], 5)
        if n_tri == 2 and n_quad == 3:
            return (GAMBIT_ELEM["prism"], 6)
    if face_count == 6 and all(s == 4 for s in face_sizes):
        return (GAMBIT_ELEM["hex"], 8)
    return (GAMBIT_ELEM["hex"], 8)  # polyhedral fallback.


def write_gambit_neu(
    polymesh_dir: str | Path,
    output_path: str | Path,
    *,
    title: str = "AutoTessell mesh",
) -> GambitNeuWriteResult:
    """OpenFOAM polyMesh → Gambit .neu ASCII format."""
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    pm_path = Path(polymesh_dir)

    try:
        from core.utils.poly_mesh_reader import read_poly_mesh
        pm = read_poly_mesh(pm_path)
    except Exception as exc:
        return GambitNeuWriteResult(
            success=False, output_path=str(out),
            message=f"poly_mesh_reader unavailable: {exc!s:.60}",
            elapsed=time.perf_counter() - t0,
        )

    points = np.asarray(pm.get("points", []), dtype=np.float64)
    faces_list = list(pm.get("faces", []))
    owner = np.asarray(pm.get("owner", []), dtype=np.int64)
    neighbour = np.asarray(pm.get("neighbour", []), dtype=np.int64)
    boundary = list(pm.get("boundary", []))

    n_pts = int(points.shape[0])
    n_cells = int(owner.max() + 1) if owner.size else 0
    n_int = int(neighbour.size)
    n_total_faces = len(faces_list)
    n_groups = max(1, len(boundary))

    if n_pts == 0 or n_cells == 0:
        return GambitNeuWriteResult(
            success=False, output_path=str(out),
            message="empty mesh",
            elapsed=time.perf_counter() - t0,
        )

    cell_faces: list[list[int]] = [[] for _ in range(n_cells)]
    for fi in range(n_total_faces):
        if fi < int(owner.size):
            cell_faces[int(owner[fi])].append(fi)
        if fi < n_int and fi < int(neighbour.size):
            cell_faces[int(neighbour[fi])].append(fi)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="ascii") as f:
        # 헤더.
        f.write("        CONTROL INFO 2.0.0\n")
        f.write("** GAMBIT NEUTRAL FILE\n")
        f.write(f"{title}\n")
        f.write("PROGRAM:                Gambit     VERSION:  2.0.0\n")
        f.write("Date: 2026-04-30\n")
        f.write("     NUMNP     NELEM     NGRPS    NBSETS     NDFCD     NDFVL\n")
        f.write(
            f"{n_pts:10d}{n_cells:10d}{n_groups:10d}{len(boundary):10d}"
            f"{3:10d}{3:10d}\n"
        )
        f.write("ENDOFSECTION\n")

        # Nodal coordinates (1-based).
        f.write("   NODAL COORDINATES 2.0.0\n")
        for i, p in enumerate(points):
            f.write(f"{i + 1:10d}{p[0]:20.11e}{p[1]:20.11e}{p[2]:20.11e}\n")
        f.write("ENDOFSECTION\n")

        # Elements.
        f.write("      ELEMENTS/CELLS 2.0.0\n")
        for ci in range(n_cells):
            cf = cell_faces[ci]
            sizes = [len(faces_list[fi]) for fi in cf]
            elem_code, n_verts = _classify_gambit_cell(len(cf), sizes)
            verts: list[int] = []
            seen: set[int] = set()
            for fi in cf:
                for v in faces_list[fi]:
                    vi = int(v)
                    if vi not in seen:
                        seen.add(vi)
                        verts.append(vi)
            verts = verts[:n_verts] + [verts[0]] * max(0, n_verts - len(verts))
            # NTYPE=GTYPE (geometry type), NDP=number of nodes per element.
            f.write(f"{ci + 1:8d}{elem_code:3d}{n_verts:3d} ")
            f.write(" ".join(f"{v + 1:8d}" for v in verts) + "\n")
        f.write("ENDOFSECTION\n")

        # Element group (single fluid group).
        f.write(
            f"       ELEMENT GROUP 2.0.0\n"
            f"GROUP:{1:11d} ELEMENTS:{n_cells:11d} MATERIAL:{2:11d} NFLAGS:{1:11d}\n"
            f"                                fluid\n"
            f"       0\n"
        )
        # ID list (10 per row).
        for i in range(n_cells):
            f.write(f"{i + 1:8d}")
            if (i + 1) % 10 == 0:
                f.write("\n")
        if n_cells % 10 != 0:
            f.write("\n")
        f.write("ENDOFSECTION\n")

        # Boundary conditions per patch.
        for pi, patch in enumerate(boundary):
            start = int(patch.get("startFace", 0))
            nf = int(patch.get("nFaces", 0))
            if nf == 0:
                continue
            name = str(patch.get("name", f"patch-{pi}"))[:32]
            f.write(" BOUNDARY CONDITIONS 2.0.0\n")
            f.write(f"{name:32s}{1:8d}{nf:8d}{0:8d}{6:8d}\n")
            for fi in range(start, min(start + nf, n_total_faces)):
                if fi < int(owner.size):
                    own = int(owner[fi]) + 1
                    # find local face id within owner cell (1-based).
                    if 0 <= own - 1 < n_cells:
                        cf = cell_faces[own - 1]
                        try:
                            local_fid = cf.index(fi) + 1
                        except ValueError:
                            local_fid = 1
                    else:
                        local_fid = 1
                    f.write(f"{own:10d}{6:5d}{local_fid:5d}\n")
            f.write("ENDOFSECTION\n")

    return GambitNeuWriteResult(
        success=True, output_path=str(out),
        n_nodes=n_pts, n_cells=n_cells,
        n_groups=n_groups,
        elapsed=time.perf_counter() - t0,
        message=(
            f"Gambit .neu written ({n_pts} nodes, {n_cells} cells, "
            f"{len(boundary)} BC sets)."
        ),
    )
