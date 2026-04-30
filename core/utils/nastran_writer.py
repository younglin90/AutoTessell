"""K1 / beta2633 — Nastran .bdf (Bulk Data File) writer.

NASA/MSC Nastran BDF format — FEM solver 용.
fixed-width 8-column field 또는 large-field 16-column.

레퍼런스: MSC Nastran Quick Reference Guide / NASA NX Nastran User's Guide.

본 구현: 8-column small-field ASCII format.
지원 element: GRID (vertex), CTETRA (4-node tet), CHEXA (8-node hex),
             CPENTA (6-node wedge), CPYRAM (5-node pyramid).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class NastranWriteResult:
    success: bool
    output_path: str = ""
    n_grids: int = 0
    n_elements: int = 0
    elapsed: float = 0.0
    message: str = ""


def _classify_nastran_elem(face_count: int, face_sizes: list[int]) -> str:
    """Returns Nastran element keyword."""
    if face_count == 4 and all(s == 3 for s in face_sizes):
        return "CTETRA"
    if face_count == 5:
        n_tri = sum(1 for s in face_sizes if s == 3)
        n_quad = sum(1 for s in face_sizes if s == 4)
        if n_tri == 4 and n_quad == 1:
            return "CPYRAM"
        if n_tri == 2 and n_quad == 3:
            return "CPENTA"
    if face_count == 6 and all(s == 4 for s in face_sizes):
        return "CHEXA"
    return "CHEXA"  # fallback


def _fmt_field(value, width: int = 8) -> str:
    """Right-justified Nastran small-field (width 8) 포맷."""
    if isinstance(value, float):
        # scientific notation 으로 8 char 안에.
        s = f"{value:.4e}"
        if len(s) > width:
            s = f"{value:.2e}"
    else:
        s = str(value)
    return s.rjust(width)


def write_nastran_bdf(
    polymesh_dir: str | Path,
    output_path: str | Path,
    *,
    title: str = "AutoTessell mesh",
    pid: int = 1,
    mid: int = 1,
) -> NastranWriteResult:
    """OpenFOAM polyMesh → Nastran .bdf small-field format.

    Args:
        title: BDF title (CASE CONTROL).
        pid: property ID (PSOLID).
        mid: material ID (MAT1).
    """
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    pm_path = Path(polymesh_dir)

    try:
        from core.utils.poly_mesh_reader import read_poly_mesh
        pm = read_poly_mesh(pm_path)
    except Exception as exc:
        return NastranWriteResult(
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
        return NastranWriteResult(
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
        # Executive Control + CASE CONTROL.
        f.write("$ Nastran BDF - AutoTessell K1/beta2633\n")
        f.write(f"$ Title: {title}\n")
        f.write("SOL 101\n")  # Linear static.
        f.write("CEND\n")
        f.write(f"TITLE = {title[:64]}\n")
        f.write("BEGIN BULK\n")

        # PSOLID + MAT1 (material card).
        # PSOLID, pid, mid.
        f.write(
            f"PSOLID  {_fmt_field(pid)}{_fmt_field(mid)}\n"
        )
        f.write(
            f"MAT1    {_fmt_field(mid)}{_fmt_field(2.1e11)}{_fmt_field('')}"
            f"{_fmt_field(0.3)}{_fmt_field(7800.0)}\n"
        )

        # GRID cards (vertex).
        for i, p in enumerate(points):
            gid = i + 1  # 1-based.
            f.write(
                f"GRID    {_fmt_field(gid)}{_fmt_field('')}"
                f"{_fmt_field(p[0])}{_fmt_field(p[1])}{_fmt_field(p[2])}\n"
            )

        # Element cards.
        eid = 1
        for ci in range(n_cells):
            cf = cell_faces[ci]
            sizes = [len(faces_list[fi]) for fi in cf]
            keyword = _classify_nastran_elem(len(cf), sizes)
            verts: list[int] = []
            seen: set[int] = set()
            for fi in cf:
                for v in faces_list[fi]:
                    vi = int(v)
                    if vi not in seen:
                        seen.add(vi)
                        verts.append(vi)

            # 1-based GIDs.
            gids = [v + 1 for v in verts]
            if keyword == "CTETRA":
                gids = (gids + [gids[0]] * 4)[:4]
                f.write(
                    f"CTETRA  {_fmt_field(eid)}{_fmt_field(pid)}"
                    f"{_fmt_field(gids[0])}{_fmt_field(gids[1])}"
                    f"{_fmt_field(gids[2])}{_fmt_field(gids[3])}\n"
                )
            elif keyword == "CHEXA":
                gids = (gids + [gids[0]] * 8)[:8]
                # CHEXA spans 2 lines (8-node).
                f.write(
                    f"CHEXA   {_fmt_field(eid)}{_fmt_field(pid)}"
                    f"{_fmt_field(gids[0])}{_fmt_field(gids[1])}"
                    f"{_fmt_field(gids[2])}{_fmt_field(gids[3])}"
                    f"{_fmt_field(gids[4])}{_fmt_field(gids[5])}+\n"
                )
                f.write(
                    f"+       {_fmt_field(gids[6])}{_fmt_field(gids[7])}\n"
                )
            elif keyword == "CPENTA":
                gids = (gids + [gids[0]] * 6)[:6]
                f.write(
                    f"CPENTA  {_fmt_field(eid)}{_fmt_field(pid)}"
                    f"{_fmt_field(gids[0])}{_fmt_field(gids[1])}"
                    f"{_fmt_field(gids[2])}{_fmt_field(gids[3])}"
                    f"{_fmt_field(gids[4])}{_fmt_field(gids[5])}\n"
                )
            elif keyword == "CPYRAM":
                gids = (gids + [gids[0]] * 5)[:5]
                f.write(
                    f"CPYRAM  {_fmt_field(eid)}{_fmt_field(pid)}"
                    f"{_fmt_field(gids[0])}{_fmt_field(gids[1])}"
                    f"{_fmt_field(gids[2])}{_fmt_field(gids[3])}"
                    f"{_fmt_field(gids[4])}\n"
                )
            eid += 1

        f.write("ENDDATA\n")

    return NastranWriteResult(
        success=True, output_path=str(out),
        n_grids=n_pts, n_elements=n_cells,
        elapsed=time.perf_counter() - t0,
        message=(
            f"Nastran BDF written ({n_pts} GRID, {n_cells} elements)."
        ),
    )
