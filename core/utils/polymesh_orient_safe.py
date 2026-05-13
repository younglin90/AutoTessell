"""BLR-9c-d-q-3 — post-BL polyhedron inversion fix (safe iteration).

Standalone post-process that detects cells with negative signed
volume in an OpenFOAM polyMesh and tries to fix each by flipping
the winding of a single owned face — only when the flip is safe
(the neighbour cell stays positive).

Differs from the failed BLR-9c-d-p-8 attempt:
- Single-iteration, single-face per inverted cell (no cascading
  multi-iteration loop).
- Accept the flip ONLY if it makes the inverted cell positive
  AND keeps the neighbour cell positive (or unchanged for
  boundary faces).
- Report which cells couldn't be fixed; caller can decide
  whether to fail.

Returns
-------
dict with keys
  - n_cells:           total cells
  - n_inverted_pre:    cells with vol < 0 before
  - n_inverted_post:   cells with vol < 0 after
  - n_flipped:         faces actually flipped
  - n_unrecoverable:   inverted cells that no single flip could fix
"""
from __future__ import annotations

from pathlib import Path
import re

import numpy as np

from core.utils.logging import get_logger
from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels


log = get_logger(__name__)


def _read_points(points_path: Path) -> np.ndarray:
    text = points_path.read_text()
    m = re.search(r"\n(\d+)\n\(", text)
    n_pts = int(m.group(1)) if m else 0
    body = text[text.index("(") :]
    nums = re.findall(r"-?[\d.eE+-]+", body)
    arr = np.array(nums, dtype=np.float64).reshape(-1, 3)[:n_pts]
    return arr


def _write_faces(faces_path: Path, faces: list[list[int]]) -> None:
    n = len(faces)
    lines: list[str] = [
        "/*--------------------------------*- C++ -*----------------------------------*\\",
        "  =========                 |",
        r"  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox",
        r"   \\    /   O peration     | Version: 13",
        r"    \\  /    A nd           |",
        r"     \\/     M anipulation  |",
        r"\*---------------------------------------------------------------------------*/",
        "FoamFile",
        "{",
        "    version     2.0;",
        "    format      ascii;",
        "    class       faceList;",
        "    location    \"constant/polyMesh\";",
        "    object      faces;",
        "}",
        "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //",
        "",
        str(n),
        "(",
    ]
    for f in faces:
        lines.append(f"{len(f)}({' '.join(str(int(v)) for v in f)})")
    lines.append(")")
    lines.append("")
    lines.append(
        "// ************************************************************************* //"
    )
    faces_path.write_text("\n".join(lines))


def _signed_cell_volumes(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
) -> np.ndarray:
    vol = np.zeros(n_cells, dtype=np.float64)
    n_internal = int(neighbour.shape[0])
    for fi, f in enumerate(faces):
        p = points[np.asarray(f, dtype=np.int64)]
        n_vec = np.zeros(3, dtype=np.float64)
        for k in range(len(f)):
            n_vec += np.cross(p[k], p[(k + 1) % len(f)])
        n_vec *= 0.5
        fc = p.mean(axis=0)
        contrib = float(np.dot(fc, n_vec))
        vol[int(owner[fi])] += contrib
        if fi < n_internal:
            vol[int(neighbour[fi])] -= contrib
    vol /= 3.0
    return vol


def _face_contribution(
    points: np.ndarray,
    face_verts: list[int],
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(face_centroid, area_vec / 2)``.

    The signed volume contribution of a face F to its owner cell C
    is ``c_F · n_F / 3`` where ``n_F`` is the outward area vector
    (positive sign for owner, flipped for neighbour).
    """
    p = points[np.asarray(face_verts, dtype=np.int64)]
    n_vec = np.zeros(3, dtype=np.float64)
    for k in range(len(face_verts)):
        n_vec += np.cross(p[k], p[(k + 1) % len(face_verts)])
    n_vec *= 0.5
    return p.mean(axis=0), n_vec


def fix_inverted_cells_safely(
    case_dir: Path,
    *,
    vol_tol: float = 1e-12,
) -> dict[str, int]:
    """Single-iteration single-face-flip fix.

    For each cell with negative signed volume, walks every face
    where the cell is the owner and asks: does reversing this
    face's winding make the cell positive AND keep the neighbour
    positive?  If yes, accept the flip.  If no single face works,
    leave the cell inverted and report.
    """
    poly = case_dir / "constant" / "polyMesh"
    points_path = poly / "points"
    faces_path = poly / "faces"
    owner_path = poly / "owner"
    neighbour_path = poly / "neighbour"
    if not all(p.exists() for p in (
        points_path, faces_path, owner_path, neighbour_path
    )):
        return {
            "n_cells": 0, "n_inverted_pre": 0,
            "n_inverted_post": 0, "n_flipped": 0,
            "n_unrecoverable": 0,
        }

    pts = _read_points(points_path)
    faces = [list(f) for f in parse_foam_faces(faces_path)]
    owner = np.asarray(parse_foam_labels(owner_path), dtype=np.int64)
    neighbour = np.asarray(
        parse_foam_labels(neighbour_path), dtype=np.int64,
    )
    n_internal = int(neighbour.shape[0])
    n_cells = max(
        int(owner.max()) if owner.size else -1,
        int(neighbour.max()) if neighbour.size else -1,
    ) + 1

    # Per-cell face index map.
    cell_face_ids: list[list[int]] = [[] for _ in range(n_cells)]
    for fi in range(len(faces)):
        cell_face_ids[int(owner[fi])].append(fi)
        if fi < n_internal:
            cell_face_ids[int(neighbour[fi])].append(fi)

    vols = _signed_cell_volumes(pts, faces, owner, neighbour, n_cells)
    inverted = np.where(vols < -vol_tol)[0]
    n_inverted_pre = int(inverted.size)

    n_flipped = 0
    n_unrecoverable = 0
    flipped_face_ids: set[int] = set()
    for cid in inverted:
        cid = int(cid)
        cur_vol_c = vols[cid]
        if cur_vol_c >= -vol_tol:
            continue   # Already fixed by a prior iteration (cascade).
        fixed = False
        for fi in cell_face_ids[cid]:
            if fi in flipped_face_ids:
                continue
            f_centroid, area_vec = _face_contribution(pts, faces[fi])
            face_contrib = float(np.dot(f_centroid, area_vec)) / 3.0
            owner_cid = int(owner[fi])
            # Determine the sign: owner sees +contrib, neighbour
            # sees -contrib.  Flipping the face winding inverts
            # the area vector → owner contrib flips sign,
            # neighbour contrib also flips sign.
            sign_for_cid = 1.0 if owner_cid == cid else -1.0
            new_vol_c = vols[cid] - 2.0 * sign_for_cid * face_contrib
            if new_vol_c <= vol_tol:
                continue
            # Boundary face: no neighbour to worry about.
            if fi >= n_internal:
                pass
            else:
                nbr_cid = int(neighbour[fi]) if owner_cid == cid \
                    else int(owner[fi])
                # Neighbour's contribution flips opposite sign.
                sign_for_nbr = -sign_for_cid
                new_vol_n = (
                    vols[nbr_cid] - 2.0 * sign_for_nbr * face_contrib
                )
                if new_vol_n <= vol_tol:
                    continue
            # Accept: flip the face's vertex order and update vols.
            faces[fi] = list(reversed(faces[fi]))
            flipped_face_ids.add(fi)
            n_flipped += 1
            vols[cid] = new_vol_c
            if fi < n_internal:
                nbr_cid = int(neighbour[fi]) if owner_cid == cid \
                    else int(owner[fi])
                vols[nbr_cid] -= 2.0 * (-sign_for_cid) * face_contrib
            fixed = True
            break
        if not fixed:
            n_unrecoverable += 1

    n_inverted_post = int((vols < -vol_tol).sum())
    if n_flipped > 0:
        _write_faces(faces_path, faces)
    return {
        "n_cells": int(n_cells),
        "n_inverted_pre": n_inverted_pre,
        "n_inverted_post": n_inverted_post,
        "n_flipped": n_flipped,
        "n_unrecoverable": n_unrecoverable,
    }
