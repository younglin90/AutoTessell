"""I1 / beta2619 — Tecplot .plt ASCII writer.

Tecplot 360 ASCII format (TITLE/VARIABLES/ZONE 헤더):
    TITLE = "AutoTessell mesh"
    VARIABLES = "X" "Y" "Z"
    ZONE T="zone-name", N=npts, E=ncells, ZONETYPE=FETETRAHEDRON|FEBRICK|FEPOLYHEDRON,
         DATAPACKING=POINT, ELEMENTTYPE=Quadrilateral|...
    <coords> ...
    <connectivity> ...

ZONETYPE codes:
    FETETRAHEDRON  = tet (4 verts/cell)
    FEBRICK        = hex (8)
    FEPOLYHEDRON   = polyhedral (variable)
    FELINESEG, FETRIANGLE, FEQUADRILATERAL — surface meshes.

레퍼런스: Tecplot 360 Data Format Guide.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class TecplotWriteResult:
    success: bool
    output_path: str = ""
    n_nodes: int = 0
    n_cells: int = 0
    zonetype: str = ""
    elapsed: float = 0.0
    message: str = ""


def _classify_zonetype(n_face_per_cell: int, face_sizes: list[int]) -> str:
    if n_face_per_cell == 4 and all(s == 3 for s in face_sizes):
        return "FETETRAHEDRON"
    if n_face_per_cell == 6 and all(s == 4 for s in face_sizes):
        return "FEBRICK"
    return "FEPOLYHEDRON"


def write_tecplot_plt(
    polymesh_dir: str | Path,
    output_path: str | Path,
    *,
    title: str = "AutoTessell mesh",
    zone_name: str = "fluid",
) -> TecplotWriteResult:
    """OpenFOAM polyMesh → Tecplot .plt ASCII format.

    homogeneous cell type (all tet 또는 all hex) → FETETRAHEDRON / FEBRICK.
    mixed → FEPOLYHEDRON (variable connectivity).
    """
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    pm_path = Path(polymesh_dir)

    try:
        from core.utils.poly_mesh_reader import read_poly_mesh
        pm = read_poly_mesh(pm_path)
    except Exception as exc:
        return TecplotWriteResult(
            success=False, output_path=str(out),
            message=f"poly_mesh_reader unavailable: {exc!s:.60}",
            elapsed=time.perf_counter() - t0,
        )

    points = np.asarray(pm.get("points", []), dtype=np.float64)
    faces_list = list(pm.get("faces", []))
    owner = np.asarray(pm.get("owner", []), dtype=np.int64)
    neighbour = np.asarray(pm.get("neighbour", []), dtype=np.int64)

    n_pts = int(points.shape[0])
    n_cells = int(owner.max() + 1) if owner.size else 0
    n_int = int(neighbour.size)
    n_total_faces = len(faces_list)

    if n_pts == 0 or n_cells == 0:
        return TecplotWriteResult(
            success=False, output_path=str(out),
            message="empty mesh",
            elapsed=time.perf_counter() - t0,
        )

    # cell connectivity 빌드.
    cell_faces: list[list[int]] = [[] for _ in range(n_cells)]
    for fi in range(n_total_faces):
        if fi < int(owner.size):
            cell_faces[int(owner[fi])].append(fi)
        if fi < n_int and fi < int(neighbour.size):
            cell_faces[int(neighbour[fi])].append(fi)

    # uniform 인지 판정.
    zonetypes = []
    for ci in range(n_cells):
        nfc = len(cell_faces[ci])
        sizes = [len(faces_list[fi]) for fi in cell_faces[ci]]
        zonetypes.append(_classify_zonetype(nfc, sizes))
    unique_zts = set(zonetypes)
    final_zt = next(iter(unique_zts)) if len(unique_zts) == 1 else "FEPOLYHEDRON"

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="ascii") as f:
        f.write(f'TITLE = "{title}"\n')
        f.write('VARIABLES = "X", "Y", "Z"\n')

        if final_zt == "FETETRAHEDRON":
            f.write(
                f'ZONE T="{zone_name}", N={n_pts}, E={n_cells}, '
                f'DATAPACKING=POINT, ZONETYPE=FETETRAHEDRON\n'
            )
            for p in points:
                f.write(f"{p[0]:.10e} {p[1]:.10e} {p[2]:.10e}\n")
            # tet connectivity: 4 vertex per row (1-based).
            for ci in range(n_cells):
                # tet 의 vertex 추출 (face vertices union).
                verts: list[int] = []
                seen: set[int] = set()
                for fi in cell_faces[ci]:
                    for v in faces_list[fi]:
                        vi = int(v)
                        if vi not in seen:
                            seen.add(vi)
                            verts.append(vi)
                if len(verts) == 4:
                    f.write(" ".join(f"{v + 1}" for v in verts) + "\n")
                else:
                    # malformed — 4 fill 로 padding.
                    f.write(" ".join(f"{v + 1}" for v in verts[:4]) + "\n")

        elif final_zt == "FEBRICK":
            f.write(
                f'ZONE T="{zone_name}", N={n_pts}, E={n_cells}, '
                f'DATAPACKING=POINT, ZONETYPE=FEBRICK\n'
            )
            for p in points:
                f.write(f"{p[0]:.10e} {p[1]:.10e} {p[2]:.10e}\n")
            # hex connectivity: 8 vertex (1-based).
            for ci in range(n_cells):
                verts: list[int] = []
                seen: set[int] = set()
                for fi in cell_faces[ci]:
                    for v in faces_list[fi]:
                        vi = int(v)
                        if vi not in seen:
                            seen.add(vi)
                            verts.append(vi)
                if len(verts) >= 8:
                    f.write(" ".join(f"{v + 1}" for v in verts[:8]) + "\n")

        else:
            # FEPOLYHEDRON: face-based output (Tecplot polyhedral block).
            n_face_total = n_total_faces
            n_face_nodes_total = sum(len(fv) for fv in faces_list)
            f.write(
                f'ZONE T="{zone_name}", NODES={n_pts}, FACES={n_face_total}, '
                f'ELEMENTS={n_cells}, DATAPACKING=BLOCK, '
                f'ZONETYPE=FEPOLYHEDRON, '
                f'TOTALNUMFACENODES={n_face_nodes_total}\n'
            )
            # X, Y, Z 각각 BLOCK packed.
            for axis in range(3):
                for k, p in enumerate(points):
                    f.write(f"{p[axis]:.10e} ")
                    if (k + 1) % 10 == 0:
                        f.write("\n")
                f.write("\n")
            # face-node count, face-node, left/right cells.
            f.write("# face node counts\n")
            for fv in faces_list:
                f.write(f"{len(fv)} ")
            f.write("\n# face nodes\n")
            for fv in faces_list:
                f.write(" ".join(f"{int(v) + 1}" for v in fv) + "\n")
            # left elements (owner+1) / right (neighbour+1, 0=boundary).
            f.write("# left elements\n")
            for fi in range(n_total_faces):
                if fi < int(owner.size):
                    f.write(f"{int(owner[fi]) + 1} ")
                else:
                    f.write("0 ")
            f.write("\n# right elements\n")
            for fi in range(n_total_faces):
                if fi < n_int and fi < int(neighbour.size):
                    f.write(f"{int(neighbour[fi]) + 1} ")
                else:
                    f.write("0 ")
            f.write("\n")

    return TecplotWriteResult(
        success=True, output_path=str(out),
        n_nodes=n_pts, n_cells=n_cells,
        zonetype=final_zt,
        elapsed=time.perf_counter() - t0,
        message=(
            f"Tecplot .plt ASCII written ({n_pts} nodes, {n_cells} cells, "
            f"zonetype={final_zt})."
        ),
    )
