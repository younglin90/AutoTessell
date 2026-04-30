"""H1 / beta2610 — ANSYS Fluent .msh writer (legacy ASCII format).

Fluent .msh 포맷 (TGrid/Gambit 호환):
    (0 "comment")            ; 주석
    (1 (zone-id ...))        ; header
    (2 dimension)            ; (2 3) = 3D
    (10 (zone-id 1 max-pt 1 nd))  ; node count header
    (10 (zone-id 1 max-pt 0 nd) ( ... coords ... ))  ; node coords
    (12 (zone-id 1 max-cell 1 type)) ; cell count header
    (12 (zone-id 1 max-cell 0 type) ( ... )) ; cell connectivity
    (13 (zone-id 1 max-face type face-type)) ; face header
    (13 (zone-id 1 max-face bc-type face-type) ( ... ))

레퍼런스:
    - ANSYS Fluent User's Guide "Mesh File Format" 부록.
    - github.com/ANSYS/PyAnsys (오픈 소스 도구로 Fluent format 다룸).

본 구현: ASCII text format (binary 는 별도 카드).

CLAUDE.md 정책: numpy only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class FluentWriteResult:
    success: bool
    output_path: str = ""
    n_nodes: int = 0
    n_cells: int = 0
    n_faces: int = 0
    n_zones: int = 0
    elapsed: float = 0.0
    message: str = ""


# Fluent face / cell type codes:
FACE_TYPE = {
    "mixed": 0,
    "linear": 2,        # 2-node edge
    "triangular": 3,
    "quadrilateral": 4,
    "polygonal": 5,
}

CELL_TYPE = {
    "mixed": 0,
    "tri": 1,
    "tetra": 2,
    "quad": 3,
    "hexa": 4,
    "pyramid": 5,
    "wedge": 6,
    "polyhedral": 7,
}

BC_TYPE = {
    "interior": 2,
    "wall": 3,
    "pressure-inlet": 4,
    "pressure-outlet": 5,
    "symmetry": 7,
    "periodic-shadow": 8,
    "pressure-far-field": 9,
    "velocity-inlet": 10,
    "fan": 12,
    "mass-flow-inlet": 20,
    "interface": 24,
    "outflow": 36,
}


def _classify_cell(n_face_per_cell: int, face_sizes: list[int]) -> int:
    """OpenFOAM cell → Fluent cell-type code."""
    if n_face_per_cell == 4 and all(s == 3 for s in face_sizes):
        return CELL_TYPE["tetra"]
    if n_face_per_cell == 5:
        n_tri = sum(1 for s in face_sizes if s == 3)
        n_quad = sum(1 for s in face_sizes if s == 4)
        if n_tri == 4 and n_quad == 1:
            return CELL_TYPE["pyramid"]
        if n_tri == 2 and n_quad == 3:
            return CELL_TYPE["wedge"]
    if n_face_per_cell == 6 and all(s == 4 for s in face_sizes):
        return CELL_TYPE["hexa"]
    return CELL_TYPE["polyhedral"]


def write_fluent_msh(
    polymesh_dir: str | Path,
    output_path: str | Path,
    *,
    bc_type_map: dict[str, str] | None = None,
) -> FluentWriteResult:
    """OpenFOAM polyMesh → Fluent .msh ASCII format.

    Args:
        polymesh_dir: OpenFOAM polyMesh 디렉터리.
        output_path: 출력 .msh 파일 경로.
        bc_type_map: patch type → Fluent BC name 매핑 override.
            default: {"wall": "wall", "patch": "pressure-far-field",
                      "symmetry": "symmetry", "empty": "symmetry"}
    """
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    pm_path = Path(polymesh_dir)

    try:
        from core.utils.poly_mesh_reader import read_poly_mesh
        pm = read_poly_mesh(pm_path)
    except Exception as exc:
        return FluentWriteResult(
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
    n_faces = len(faces_list)

    if n_pts == 0 or n_cells == 0:
        return FluentWriteResult(
            success=False, output_path=str(out),
            message="empty mesh",
            elapsed=time.perf_counter() - t0,
        )

    bc_map = {
        "wall": "wall",
        "patch": "pressure-far-field",
        "symmetry": "symmetry",
        "symmetryplane": "symmetry",
        "empty": "symmetry",
    }
    if bc_type_map:
        bc_map.update(bc_type_map)

    # cell type 분류 (per-cell).
    cell_faces: list[list[int]] = [[] for _ in range(n_cells)]
    for fi in range(n_faces):
        if fi < int(owner.size):
            cell_faces[int(owner[fi])].append(fi)
        if fi < n_int and fi < int(neighbour.size):
            cell_faces[int(neighbour[fi])].append(fi)

    cell_type_codes = []
    for ci in range(n_cells):
        nfc = len(cell_faces[ci])
        sizes = [len(faces_list[fi]) for fi in cell_faces[ci]]
        cell_type_codes.append(_classify_cell(nfc, sizes))

    # uniform cell type? (all same → use single zone).
    unique_ct = set(cell_type_codes)
    cell_zone_type = next(iter(unique_ct)) if len(unique_ct) == 1 else CELL_TYPE["mixed"]

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="ascii") as f:
        # Header.
        f.write("(0 \"AutoTessell Fluent .msh writer (H1/beta2610)\")\n")
        f.write("(1 \"Fluent format ASCII\")\n")
        f.write("(2 3)\n")  # 3D.

        # Node count header (zone-id=0 = global header).
        f.write(f"(10 (0 1 {n_pts:x} 0 3))\n")

        # Node coordinates (zone-id=1).
        f.write(f"(10 (1 1 {n_pts:x} 1 3)(\n")
        for p in points:
            f.write(f"  {p[0]:.16e} {p[1]:.16e} {p[2]:.16e}\n")
        f.write("))\n")

        # Cell count header.
        f.write(f"(12 (0 1 {n_cells:x} 0 0))\n")
        # Cell zone (zone-id=2, type=fluid).
        f.write(f"(12 (2 1 {n_cells:x} 1 {cell_zone_type:d})")
        if cell_zone_type == CELL_TYPE["mixed"]:
            f.write("(\n")
            for ct in cell_type_codes:
                f.write(f"{ct:d}\n")
            f.write("))\n")
        else:
            f.write(")\n")

        # Face count header.
        f.write(f"(13 (0 1 {n_faces:x} 0))\n")

        # Internal faces (zone-id=3).
        if n_int > 0:
            f.write(f"(13 (3 1 {n_int:x} {BC_TYPE['interior']:d} 0)(\n")
            for fi in range(n_int):
                fv = faces_list[fi]
                fv_hex = " ".join(f"{int(v) + 1:x}" for v in fv)
                own = int(owner[fi]) + 1
                nbr = int(neighbour[fi]) + 1
                f.write(f"{len(fv):x} {fv_hex} {own:x} {nbr:x}\n")
            f.write("))\n")

        # Boundary face zones (zone-id=4+).
        zone_id = 4
        for pi, patch in enumerate(boundary):
            start = int(patch.get("startFace", 0))
            nf = int(patch.get("nFaces", 0))
            if nf == 0:
                continue
            type_str = str(patch.get("type", "patch")).lower()
            bc_name = bc_map.get(type_str, "wall")
            bc_code = BC_TYPE.get(bc_name, BC_TYPE["wall"])
            patch_name = str(patch.get("name", f"patch-{pi}"))
            f.write(f"(13 ({zone_id:x} {start + 1:x} {start + nf:x} {bc_code:d} 0)(\n")
            for fi in range(start, start + nf):
                if fi >= n_faces:
                    break
                fv = faces_list[fi]
                fv_hex = " ".join(f"{int(v) + 1:x}" for v in fv)
                own = int(owner[fi]) + 1 if fi < int(owner.size) else 0
                f.write(f"{len(fv):x} {fv_hex} {own:x} 0\n")
            f.write("))\n")
            # Zone name.
            f.write(f"(45 ({zone_id:d} {bc_name} {patch_name})())\n")
            zone_id += 1

    return FluentWriteResult(
        success=True, output_path=str(out),
        n_nodes=n_pts, n_cells=n_cells, n_faces=n_faces,
        n_zones=zone_id - 4,
        elapsed=time.perf_counter() - t0,
        message=(
            f"Fluent .msh ASCII written ({n_pts} nodes, {n_cells} cells, "
            f"{n_faces} faces, {zone_id - 4} BC zones)."
        ),
    )
