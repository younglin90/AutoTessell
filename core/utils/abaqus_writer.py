"""L1 / beta2640 — Abaqus .inp keyword input writer.

Abaqus FEM solver 의 input deck format. Section 키워드 기반 ASCII.
지원 element type: C3D4 (tet), C3D8 (hex), C3D6 (wedge), C3D5 (pyramid).

레퍼런스: Abaqus Keywords Reference Guide §1.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class AbaqusWriteResult:
    success: bool
    output_path: str = ""
    n_nodes: int = 0
    n_elements: int = 0
    elapsed: float = 0.0
    message: str = ""


def _classify_abaqus_elem(face_count: int, face_sizes: list[int]) -> tuple[str, int]:
    if face_count == 4 and all(s == 3 for s in face_sizes):
        return ("C3D4", 4)
    if face_count == 5:
        n_tri = sum(1 for s in face_sizes if s == 3)
        n_quad = sum(1 for s in face_sizes if s == 4)
        if n_tri == 4 and n_quad == 1:
            return ("C3D5", 5)
        if n_tri == 2 and n_quad == 3:
            return ("C3D6", 6)
    if face_count == 6 and all(s == 4 for s in face_sizes):
        return ("C3D8", 8)
    return ("C3D8", 8)  # fallback


def write_abaqus_inp(
    polymesh_dir: str | Path,
    output_path: str | Path,
    *,
    instance_name: str = "PART-1",
    material_name: str = "Steel",
) -> AbaqusWriteResult:
    """OpenFOAM polyMesh → Abaqus .inp deck."""
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    pm_path = Path(polymesh_dir)

    try:
        from core.utils.poly_mesh_reader import read_poly_mesh
        pm = read_poly_mesh(pm_path)
    except Exception as exc:
        return AbaqusWriteResult(
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
        return AbaqusWriteResult(
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
        f.write("*Heading\n")
        f.write(" AutoTessell Abaqus deck (L1/beta2640)\n")
        f.write("*Preprint, echo=NO, model=NO, history=NO, contact=NO\n")

        # Part definition.
        f.write(f"*Part, name={instance_name}\n")

        # Nodes (1-based).
        f.write("*Node\n")
        for i, p in enumerate(points):
            f.write(f"{i + 1}, {p[0]:.10e}, {p[1]:.10e}, {p[2]:.10e}\n")

        # Elements (group by type).
        cells_by_type: dict[str, list[tuple[int, list[int]]]] = {}
        for ci in range(n_cells):
            cf = cell_faces[ci]
            sizes = [len(faces_list[fi]) for fi in cf]
            elem_type, n_v = _classify_abaqus_elem(len(cf), sizes)
            verts: list[int] = []
            seen: set[int] = set()
            for fi in cf:
                for v in faces_list[fi]:
                    vi = int(v)
                    if vi not in seen:
                        seen.add(vi)
                        verts.append(vi)
            verts = (verts + [verts[0]] * n_v)[:n_v]
            cells_by_type.setdefault(elem_type, []).append((ci + 1, verts))

        for elem_type, items in cells_by_type.items():
            f.write(f"*Element, type={elem_type}\n")
            for eid, verts in items:
                vs = ", ".join(str(v + 1) for v in verts)
                f.write(f"{eid}, {vs}\n")

        # Element set + section.
        f.write("*Elset, elset=ALL_ELEMENTS, generate\n")
        f.write(f"1, {n_cells}, 1\n")
        f.write(
            f"*Solid Section, elset=ALL_ELEMENTS, material={material_name}\n"
            ",\n"
        )

        f.write("*End Part\n")

        # Assembly + instance.
        f.write("*Assembly, name=Assembly\n")
        f.write(f"*Instance, name={instance_name}-1, part={instance_name}\n")
        f.write("*End Instance\n")
        f.write("*End Assembly\n")

        # Materials.
        f.write(f"*Material, name={material_name}\n")
        f.write("*Density\n7800.,\n")
        f.write("*Elastic\n2.1e+11, 0.3\n")

    return AbaqusWriteResult(
        success=True, output_path=str(out),
        n_nodes=n_pts, n_elements=n_cells,
        elapsed=time.perf_counter() - t0,
        message=f"Abaqus .inp written ({n_pts} nodes, {n_cells} elements).",
    )
