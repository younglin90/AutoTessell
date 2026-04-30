"""J1 / beta2626 — AVS UCD (Unstructured Cell Data) format writer.

UCD format (AVS Express, FieldView, ParaView, Salome):
    ASCII header:
        n_nodes  n_cells  n_node_data  n_cell_data  n_model_data
    nodes (1-based):
        node_id  x  y  z
    cells:
        cell_id  material_id  cell_type  v0 v1 v2 ...
    cell_type: tet, hex, prism, pyr, line, tri, quad, ...

레퍼런스: AVS UCD Format Reference (https://lanl.github.io/LaGriT/pages/docs/UCD_Format.html).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class AVSUCDWriteResult:
    success: bool
    output_path: str = ""
    n_nodes: int = 0
    n_cells: int = 0
    elapsed: float = 0.0
    message: str = ""


def _classify_ucd_cell(face_count: int, face_sizes: list[int]) -> tuple[str, int]:
    """Returns (cell_type_str, expected_n_verts)."""
    if face_count == 4 and all(s == 3 for s in face_sizes):
        return ("tet", 4)
    if face_count == 5:
        n_tri = sum(1 for s in face_sizes if s == 3)
        n_quad = sum(1 for s in face_sizes if s == 4)
        if n_tri == 4 and n_quad == 1:
            return ("pyr", 5)
        if n_tri == 2 and n_quad == 3:
            return ("prism", 6)
    if face_count == 6 and all(s == 4 for s in face_sizes):
        return ("hex", 8)
    return ("hex", 8)  # fallback (UCD lacks polyhedral support).


def write_avs_ucd(
    polymesh_dir: str | Path,
    output_path: str | Path,
) -> AVSUCDWriteResult:
    """OpenFOAM polyMesh → AVS UCD ASCII format.

    Polyhedral cells 는 UCD 표준 미지원 — hex(8) 로 fallback (8 vertex 추출).
    """
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    pm_path = Path(polymesh_dir)

    try:
        from core.utils.poly_mesh_reader import read_poly_mesh
        pm = read_poly_mesh(pm_path)
    except Exception as exc:
        return AVSUCDWriteResult(
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
        return AVSUCDWriteResult(
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
        # Header: n_nodes n_cells n_node_data n_cell_data n_model_data.
        f.write(f"{n_pts} {n_cells} 0 0 0\n")
        # Nodes (1-based).
        for i, p in enumerate(points):
            f.write(f"{i + 1} {p[0]:.10e} {p[1]:.10e} {p[2]:.10e}\n")
        # Cells.
        for ci in range(n_cells):
            cf = cell_faces[ci]
            sizes = [len(faces_list[fi]) for fi in cf]
            cell_type, n_verts_expected = _classify_ucd_cell(len(cf), sizes)
            verts: list[int] = []
            seen: set[int] = set()
            for fi in cf:
                for v in faces_list[fi]:
                    vi = int(v)
                    if vi not in seen:
                        seen.add(vi)
                        verts.append(vi)
            if len(verts) >= n_verts_expected:
                vstr = " ".join(f"{v + 1}" for v in verts[:n_verts_expected])
                f.write(f"{ci + 1} 1 {cell_type} {vstr}\n")
            else:
                # 부족한 vertex — padding.
                vstr = " ".join(f"{v + 1}" for v in verts)
                pad = " ".join(f"{verts[0] + 1}" for _ in range(n_verts_expected - len(verts)))
                f.write(f"{ci + 1} 1 {cell_type} {vstr} {pad}\n")

    return AVSUCDWriteResult(
        success=True, output_path=str(out),
        n_nodes=n_pts, n_cells=n_cells,
        elapsed=time.perf_counter() - t0,
        message=f"AVS UCD written ({n_pts} nodes, {n_cells} cells).",
    )
