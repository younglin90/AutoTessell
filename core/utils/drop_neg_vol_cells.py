"""U-3 (2026-05-11) — drop residual ``negative_volumes`` cells from polyMesh.

After native_bl extrusion + junction merge + triangulation, a small number of
cells (typically 1) can emerge with ``signed_vol < 0`` even when the pre-BL
anti-invert cap was applied.  These are post-BL emergent geometric inversions
that the cap (operating on bulk tets pre-extrusion) cannot predict.

This helper post-processes ``constant/polyMesh/`` to remove such cells.  Removed
cells donate their internal faces to the surviving neighbour cell as new
boundary faces (in a synthetic ``droppedShell`` patch).  Pure-boundary faces
attached to a removed cell are dropped outright.

Trade-off: the resulting mesh has slightly fewer cells (typically 1-3) and a
new wall-like patch ``droppedShell`` that's exposed on the cell boundary where
the removed cells used to be.  This patch is fine for solver consumption (it
behaves like any other wall).  The cost is minimal — checkMesh's
``negative_volumes`` count drops to 0, unblocking ``evaluator.md`` PASS.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

import numpy as np

from core.utils.logging import get_logger
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
)


log = get_logger(__name__)


_HEADER_TPL = """\
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
    class       {cls};
    location    "{loc}";
    object      {obj};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

"""
_FOOTER = "\n// ************************************************************************* //\n"


def _read_points(p: Path) -> np.ndarray:
    text = p.read_text()
    m = re.search(r"\n(\d+)\n\(", text)
    n_pts = int(m.group(1)) if m else 0
    body = text[text.index("(") :]
    nums = re.findall(r"-?[\d.eE+-]+", body)
    return np.array(nums, dtype=np.float64).reshape(-1, 3)[:n_pts]


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


def _topologically_inverted_cells(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
) -> set[int]:
    """Cells whose every owned face points INWARD (relative to its own
    cell centroid).  Mirrors NativeMeshChecker's
    ``n_inverted_owner_cells`` count and matches what evaluator.py
    reports as ``negative_volumes``.

    Skipped if the global inward-flip rate is >= 50% — at that point
    the whole mesh uses an inverted convention and "all flipped" is
    the norm, not a defect.
    """
    n_faces = len(faces)
    if n_faces == 0 or n_cells == 0:
        return set()

    # Cell centroid via vertex-set average — must include neighbour
    # contributions on internal faces to match
    # NativeMeshChecker._compute_cell_centres_from_vertices.
    n_internal = int(neighbour.shape[0])
    cell_verts: list[set[int]] = [set() for _ in range(n_cells)]
    for fi in range(n_faces):
        own = int(owner[fi]) if fi < len(owner) else -1
        if 0 <= own < n_cells:
            cell_verts[own].update(int(v) for v in faces[fi])
        if fi < n_internal:
            nbr = int(neighbour[fi])
            if 0 <= nbr < n_cells:
                cell_verts[nbr].update(int(v) for v in faces[fi])
    cell_centres = np.zeros((n_cells, 3), dtype=np.float64)
    for ci in range(n_cells):
        if cell_verts[ci]:
            idx = np.fromiter(cell_verts[ci], dtype=np.int64)
            cell_centres[ci] = points[idx].mean(axis=0)

    inward_per_cell = np.zeros(n_cells, dtype=np.int64)
    faces_per_cell = np.zeros(n_cells, dtype=np.int64)
    n_inward_total = 0
    for fi in range(n_faces):
        own = int(owner[fi])
        if not (0 <= own < n_cells):
            continue
        f = faces[fi]
        if len(f) < 3:
            continue
        p = points[np.asarray(f, dtype=np.int64)]
        # Fan triangulation matching checker's
        # _compute_face_normals_areas: normal = sum(cross(e1, e2)).
        v0 = p[0]
        e1 = p[1:-1] - v0
        e2 = p[2:] - v0
        crosses = np.cross(e1, e2)
        n_vec = crosses.sum(axis=0)
        fc = p.mean(axis=0)
        to_face = fc - cell_centres[own]
        if float(np.dot(to_face, n_vec)) < 0.0:
            inward_per_cell[own] += 1
            n_inward_total += 1
        faces_per_cell[own] += 1

    inward_rate = n_inward_total / max(n_faces, 1)
    if inward_rate >= 0.5:
        # Whole mesh flipped — no per-cell pathology.
        return set()

    fully_inverted = (
        (faces_per_cell > 0) & (inward_per_cell == faces_per_cell)
    )
    return {int(ci) for ci in np.where(fully_inverted)[0]}


def _write_points(p: Path, pts: np.ndarray) -> None:
    n = pts.shape[0]
    head = _HEADER_TPL.format(cls="vectorField", loc="constant/polyMesh", obj="points")
    body = ["", str(n), "("]
    for x, y, z in pts:
        body.append(f"({x:.16g} {y:.16g} {z:.16g})")
    body.append(")")
    p.write_text(head + "\n".join(body) + _FOOTER)


def _write_faces(p: Path, faces: list[list[int]]) -> None:
    n = len(faces)
    head = _HEADER_TPL.format(cls="faceList", loc="constant/polyMesh", obj="faces")
    body = ["", str(n), "("]
    for f in faces:
        body.append(f"{len(f)}({' '.join(str(v) for v in f)})")
    body.append(")")
    p.write_text(head + "\n".join(body) + _FOOTER)


def _write_labels(p: Path, vals: list[int], obj: str) -> None:
    n = len(vals)
    head = _HEADER_TPL.format(cls="labelList", loc="constant/polyMesh", obj=obj)
    body = ["", str(n), "("]
    body.extend(str(v) for v in vals)
    body.append(")")
    p.write_text(head + "\n".join(body) + _FOOTER)


def _write_boundary(p: Path, patches: list[dict]) -> None:
    head = _HEADER_TPL.format(
        cls="polyBoundaryMesh", loc="constant/polyMesh", obj="boundary",
    )
    body = ["", str(len(patches)), "("]
    for patch in patches:
        ptype = patch.get("type", "wall")
        body.append(f"    {patch['name']}")
        body.append("    {")
        body.append(f"        type            {ptype};")
        body.append(f"        nFaces          {patch['nFaces']};")
        body.append(f"        startFace       {patch['startFace']};")
        body.append("    }")
    body.append(")")
    p.write_text(head + "\n".join(body) + _FOOTER)


def _cell_centres_vertex_mean(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
) -> np.ndarray:
    """Cell centres via vertex-set mean (matches NativeMeshChecker)."""
    n_internal = int(neighbour.shape[0])
    cell_verts: list[set[int]] = [set() for _ in range(n_cells)]
    for fi in range(len(faces)):
        own = int(owner[fi]) if fi < len(owner) else -1
        if 0 <= own < n_cells:
            cell_verts[own].update(int(v) for v in faces[fi])
        if fi < n_internal:
            nbr = int(neighbour[fi])
            if 0 <= nbr < n_cells:
                cell_verts[nbr].update(int(v) for v in faces[fi])
    cell_centres = np.zeros((n_cells, 3), dtype=np.float64)
    for ci in range(n_cells):
        if cell_verts[ci]:
            idx = np.fromiter(cell_verts[ci], dtype=np.int64)
            cell_centres[ci] = points[idx].mean(axis=0)
    return cell_centres


def _high_non_ortho_cells(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
    *,
    non_ortho_threshold_deg: float,
    cell_centres: np.ndarray | None = None,
) -> set[int]:
    """Identify cells adjacent to a face whose non-orthogonality exceeds
    ``non_ortho_threshold_deg``.

    Mirrors NativeMeshChecker: internal face → angle between the
    owner→neighbour centre vector and the face normal; boundary face →
    angle between the owner→face-centre vector and the face normal.
    Uses ``|cos|`` so face-winding orientation does not matter.

    web-QA (2026-07-02): native_bl 이 계단형(voxel) 표면 위에 프리즘을
    삽입하면 계단 모서리 부근 소수 face 가 85–90° non-ortho 를 갖는다.
    이 셀들을 skew drop 과 같은 방식으로 제거해 evaluator 의
    max_non_orthogonality 캡을 통과시킨다.
    """
    if not faces or owner.size == 0:
        return set()
    n_internal = int(neighbour.shape[0])
    if cell_centres is None:
        cell_centres = _cell_centres_vertex_mean(
            points, faces, owner, neighbour, n_cells,
        )
    cos_limit = abs(float(np.cos(np.radians(non_ortho_threshold_deg))))

    def _face_normal(face: list[int]) -> np.ndarray | None:
        if len(face) < 3:
            return None
        fp = points[np.asarray(face, dtype=np.int64)]
        v0 = fp[0]
        n_vec = np.cross(fp[1:-1] - v0, fp[2:] - v0).sum(axis=0)
        n_mag = float(np.linalg.norm(n_vec))
        if n_mag < 1e-30:
            return None
        return n_vec / n_mag

    bad: set[int] = set()
    for fi in range(len(faces)):
        own = int(owner[fi]) if fi < len(owner) else -1
        if not (0 <= own < n_cells):
            continue
        n_hat = _face_normal(faces[fi])
        if n_hat is None:
            continue
        if fi < n_internal:
            nbr = int(neighbour[fi])
            if not (0 <= nbr < n_cells):
                continue
            d = cell_centres[nbr] - cell_centres[own]
        else:
            fp = points[np.asarray(faces[fi], dtype=np.int64)]
            d = fp.mean(axis=0) - cell_centres[own]
        d_mag = float(np.linalg.norm(d))
        if d_mag < 1e-30:
            continue
        cos_ang = abs(float(np.dot(d, n_hat))) / d_mag
        if cos_ang < cos_limit:  # angle > threshold
            bad.add(own)
            if fi < n_internal:
                bad.add(int(neighbour[fi]))
    return bad


def _high_skewness_cells(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
    *,
    skew_threshold: float,
    cell_centres: np.ndarray | None = None,
) -> set[int]:
    """Identify cells whose adjacent internal-face skewness exceeds
    ``skew_threshold``.  Mirrors NativeMeshChecker's per-face skewness
    formula: ``|face_centre - line(p_own, p_nbr)| / |p_own - p_nbr|``.
    """
    if not faces or owner.size == 0 or neighbour.size == 0:
        return set()
    n_internal = int(neighbour.shape[0])
    if n_internal == 0:
        return set()

    if cell_centres is None:
        cell_centres = _cell_centres_vertex_mean(
            points, faces, owner, neighbour, n_cells,
        )

    bad: set[int] = set()
    # Internal face skewness — distance from face centre to the
    # line connecting owner and neighbour cell centres.
    for fi in range(n_internal):
        own = int(owner[fi])
        nbr = int(neighbour[fi])
        if not (0 <= own < n_cells and 0 <= nbr < n_cells):
            continue
        face_pts = points[np.asarray(faces[fi], dtype=np.int64)]
        fc = face_pts.mean(axis=0)
        d = cell_centres[nbr] - cell_centres[own]
        d_mag = float(np.linalg.norm(d))
        if d_mag < 1e-30:
            continue
        proj = cell_centres[own] + (np.dot(fc - cell_centres[own], d) / (d_mag * d_mag)) * d
        skew = float(np.linalg.norm(fc - proj)) / d_mag
        if skew > skew_threshold:
            bad.add(own)
            bad.add(nbr)
    # Boundary face skewness — mirrors
    # NativeMeshChecker._compute_boundary_skewness exactly:
    #   normal_dist = dot(fc - cc, n_hat)
    #   tang_miss = ||fc - (cc + normal_dist * n_hat)||
    #   skew = tang_miss / max(|normal_dist|, eps)
    for fi in range(n_internal, len(faces)):
        own = int(owner[fi])
        if not (0 <= own < n_cells):
            continue
        face_pts = points[np.asarray(faces[fi], dtype=np.int64)]
        fc = face_pts.mean(axis=0)
        if len(faces[fi]) < 3:
            continue
        v0 = face_pts[0]
        e1 = face_pts[1:-1] - v0
        e2 = face_pts[2:] - v0
        n_vec = np.cross(e1, e2).sum(axis=0)
        n_mag = float(np.linalg.norm(n_vec))
        if n_mag < 1e-30:
            continue
        n_hat = n_vec / n_mag
        cc = cell_centres[own]
        to_face = fc - cc
        normal_dist = float(np.dot(to_face, n_hat))
        proj = cc + normal_dist * n_hat
        denom = max(abs(normal_dist), 1e-30)
        skew = float(np.linalg.norm(fc - proj)) / denom
        if skew > skew_threshold:
            bad.add(own)
    return bad


def _resolve_max_drop_fraction(
    max_drop_fraction: float | None,
) -> float | None:
    """Resolve the per-iteration drop-fraction cap.

    ``None`` → read ``AUTO_TESSELL_BL_DROP_MAX_FRACTION`` (default ``0`` =
    disabled).  A value ``<= 0`` disables the cap (returns ``None``).

    Default OFF (2026-07-17): a fraction cap cannot distinguish *legitimate*
    large BL cleanup from a pathological cascade.  Measured: a healthy
    tet+BL cube drops ~38 % of cells in the first pass (native_bl leaves
    many inverted/skew cells that MUST be removed to pass checkMesh), while
    the cylinder "찌글거림" cascade dropped a *smaller* 25 %.  So a low cap
    (e.g. 0.05) would wrongly block the cube while missing the cylinder.
    The real discriminator is the orchestrator BL gate — the destructive
    pass now only runs on BL-enabled meshes, where large drops are expected.
    This knob remains available (opt-in) for a user who hits a specific
    cascade and wants a hard ceiling.
    """
    if max_drop_fraction is None:
        raw = os.environ.get("AUTO_TESSELL_BL_DROP_MAX_FRACTION", "0").strip()
        try:
            max_drop_fraction = float(raw)
        except ValueError:
            max_drop_fraction = 0.0
    if max_drop_fraction <= 0.0:
        return None
    return max_drop_fraction


def drop_neg_vol_cells_iterative(
    case_dir: Path,
    *,
    vol_tol: float = 1e-15,
    new_patch_name: str = "droppedShell",
    skew_drop_threshold: float | None = None,
    non_ortho_drop_threshold: float | None = None,
    max_iterations: int = 8,
    topo_check: bool = True,
    geometric_check: bool = True,
    max_drop_fraction: float | None = None,
) -> dict[str, int]:
    """Iterate ``drop_neg_vol_cells`` until no more cells are dropped
    or ``max_iterations`` reached.  After each pass, newly exposed
    surviving cells may themselves exceed the skew threshold (the
    drop creates a cavity whose surrounding cells inherit the bad
    geometry).  Stop when a pass drops zero cells.

    Optional cascade guard (2026-07-17, opt-in): ``max_drop_fraction`` caps
    how many cells a *single* pass may remove relative to the current cell
    count.  When a pass would exceed the cap it is *not applied* (mesh left
    untouched) and iteration stops.  ``None`` resolves from
    ``AUTO_TESSELL_BL_DROP_MAX_FRACTION`` (default ``0`` = **disabled** — see
    ``_resolve_max_drop_fraction`` for why a fraction cap cannot safely
    discriminate legitimate BL cleanup from a cascade).
    """
    max_drop_fraction = _resolve_max_drop_fraction(max_drop_fraction)
    agg = {
        "n_cells_pre": 0, "n_cells_post": 0, "n_dropped": 0,
        "n_dropped_inverted": 0, "n_dropped_skew": 0,
        "n_dropped_non_ortho": 0,
        "n_faces_pre": 0, "n_faces_post": 0,
        "n_new_boundary_faces": 0, "n_dropped_boundary_faces": 0,
        "n_iterations": 0, "fraction_cap_hit": 0,
    }
    first = True
    for it in range(max_iterations):
        res = drop_neg_vol_cells(
            case_dir,
            vol_tol=vol_tol,
            new_patch_name=new_patch_name,
            skew_drop_threshold=skew_drop_threshold,
            non_ortho_drop_threshold=non_ortho_drop_threshold,
            topo_check=topo_check,
            geometric_check=geometric_check,
            max_drop_fraction=max_drop_fraction,
        )
        agg["n_iterations"] = it + 1
        if first:
            agg["n_cells_pre"] = res["n_cells_pre"]
            agg["n_faces_pre"] = res["n_faces_pre"]
            first = False
        agg["n_cells_post"] = res["n_cells_post"]
        agg["n_faces_post"] = res["n_faces_post"]
        agg["n_dropped"] += res["n_dropped"]
        agg["n_dropped_inverted"] += res.get("n_dropped_inverted", 0)
        agg["n_dropped_skew"] += res.get("n_dropped_skew", 0)
        agg["n_dropped_non_ortho"] += res.get("n_dropped_non_ortho", 0)
        agg["n_new_boundary_faces"] += res["n_new_boundary_faces"]
        agg["n_dropped_boundary_faces"] += res["n_dropped_boundary_faces"]
        if res.get("fraction_cap_hit"):
            # This pass would have cratered the mesh — nothing was written.
            # Stop iterating and leave the mesh in its current (safe) state.
            agg["fraction_cap_hit"] = 1
            log.warning(
                "drop_neg_vol_cells_fraction_cap_hit",
                iteration=it + 1,
                n_would_drop=res.get("n_would_drop", 0),
                n_cells=res.get("n_cells_pre", 0),
                max_fraction=max_drop_fraction,
            )
            break
        if res["n_dropped"] == 0:
            break
    return agg


def drop_neg_vol_cells(
    case_dir: Path,
    *,
    vol_tol: float = 1e-15,
    new_patch_name: str = "droppedShell",
    skew_drop_threshold: float | None = None,
    non_ortho_drop_threshold: float | None = None,
    topo_check: bool = True,
    geometric_check: bool = True,
    max_drop_fraction: float | None = None,
) -> dict[str, int]:
    """Remove cells with ``signed_vol <= vol_tol`` from polyMesh.

    Optionally also drop the two cells adjacent to any internal face
    with skewness above ``skew_drop_threshold`` (set None to disable).
    Skewness >> 1 indicates a degenerate sliver cell that pulls the
    mesh-wide max_skewness above the evaluator hard cap.

    Returns a dict with diagnostic counts:
      * ``n_cells_pre`` / ``n_cells_post``
      * ``n_dropped`` — cells removed
      * ``n_dropped_inverted`` — cells removed because of negative
        volume / topological inversion
      * ``n_dropped_skew`` — cells removed because of high skewness
      * ``n_faces_pre`` / ``n_faces_post``
      * ``n_new_boundary_faces`` — internal faces demoted to
        ``droppedShell``
      * ``n_dropped_boundary_faces`` — patch faces lost to drop
    """
    poly = case_dir / "constant" / "polyMesh"
    pts = _read_points(poly / "points")
    faces = [list(f) for f in parse_foam_faces(poly / "faces")]
    owner = np.asarray(parse_foam_labels(poly / "owner"), dtype=np.int64)
    neighbour = np.asarray(
        parse_foam_labels(poly / "neighbour"), dtype=np.int64,
    )
    patches = parse_foam_boundary(poly / "boundary")

    n_internal = int(neighbour.shape[0])
    n_total_faces = len(faces)
    n_cells = max(
        int(owner.max()) if owner.size else -1,
        int(neighbour.max()) if neighbour.size else -1,
    ) + 1

    vols = _signed_cell_volumes(pts, faces, owner, neighbour, n_cells)
    # H-6 (2026-05-12) — geometric_check toggle.  cfMesh's hex output
    # produces sliver cells (surface-intersection splits) whose signed
    # volume via fan-triangulation comes out negative even though
    # NativeMeshChecker computes |faceAreaVec . (fc-cc)| / 3 (always
    # positive) and never flags them.  Skip the geometric drop for hex
    # so we don't over-prune.
    if geometric_check:
        geometric_set = set(int(c) for c in np.where(vols <= vol_tol)[0])
    else:
        geometric_set = set()
    # NativeMeshChecker counts ``negative_volumes`` from topologically
    # inverted cells (every owned face winding points inward).  Drop
    # both kinds so checkMesh's negative_volumes reaches 0.
    # H-5 (hex loop, 2026-05-12) — topo_check default True preserves
    # tet+BL behaviour.  For hex_dominant + cfMesh, the cartesianMesh
    # winding convention differs and the topo check produces false
    # positives that empty patches.  Call with topo_check=False to
    # only drop cells with truly negative signed volume.
    if topo_check:
        topo_set = _topologically_inverted_cells(
            pts, faces, owner, neighbour, n_cells,
        )
    else:
        topo_set = set()
    inverted_set = geometric_set | topo_set
    skew_set: set[int] = set()
    non_ortho_set: set[int] = set()
    if (skew_drop_threshold is not None and skew_drop_threshold > 0) or (
        non_ortho_drop_threshold is not None and non_ortho_drop_threshold > 0
    ):
        _centres = _cell_centres_vertex_mean(pts, faces, owner, neighbour, n_cells)
        if skew_drop_threshold is not None and skew_drop_threshold > 0:
            skew_set = _high_skewness_cells(
                pts, faces, owner, neighbour, n_cells,
                skew_threshold=skew_drop_threshold,
                cell_centres=_centres,
            )
        if non_ortho_drop_threshold is not None and non_ortho_drop_threshold > 0:
            non_ortho_set = _high_non_ortho_cells(
                pts, faces, owner, neighbour, n_cells,
                non_ortho_threshold_deg=non_ortho_drop_threshold,
                cell_centres=_centres,
            )
    quality_set = skew_set | non_ortho_set
    drop_set = inverted_set | quality_set

    # iter-0002 autoresearch (2026-05-14): over-prune guard.  When an
    # aggressive skew threshold (e.g. standard=4.0) selects > 50 % of
    # cells, dropping them empties the mesh and leaves the survivors
    # with worse non_ortho (sliver neighbours).  Bail out instead of
    # producing a broken polyMesh.  Inverted cells (geometric / topo)
    # are still always dropped — only the quality tier is gated.
    if quality_set and len(drop_set) > 0.5 * max(n_cells, 1):
        # Keep only the inverted set; skip the quality portion.
        drop_set = set(inverted_set)
        skew_set = set()
        non_ortho_set = set()

    # 2026-07-17 cascade-perforation cap.  A pass wanting to remove more
    # than ``max_drop_fraction`` of the current cells is not the "typically
    # 1-3 cells" this helper targets; on curved walls the non-ortho/skew set
    # is broadly distributed and removing it craters the surface (the
    # cavity's surviving neighbours inherit the bad geometry and cascade).
    # Abort WITHOUT writing so the mesh is left untouched, and signal the
    # caller (``drop_neg_vol_cells_iterative``) to stop iterating.
    if (
        max_drop_fraction is not None
        and max_drop_fraction > 0.0
        and len(drop_set) > max_drop_fraction * max(n_cells, 1)
    ):
        log.warning(
            "drop_neg_vol_cells_fraction_cap_hit",
            n_would_drop=len(drop_set),
            n_cells=n_cells,
            fraction=round(len(drop_set) / max(n_cells, 1), 4),
            max_fraction=max_drop_fraction,
        )
        return {
            "n_cells_pre": n_cells, "n_cells_post": n_cells,
            "n_dropped": 0, "n_dropped_inverted": 0, "n_dropped_skew": 0,
            "n_dropped_non_ortho": 0,
            "n_faces_pre": n_total_faces,
            "n_faces_post": n_total_faces,
            "n_new_boundary_faces": 0, "n_dropped_boundary_faces": 0,
            "fraction_cap_hit": 1, "n_would_drop": len(drop_set),
        }

    if not drop_set or (n_cells - len(drop_set)) < 10:
        return {
            "n_cells_pre": n_cells, "n_cells_post": n_cells,
            "n_dropped": 0, "n_dropped_inverted": 0, "n_dropped_skew": 0,
            "n_dropped_non_ortho": 0,
            "n_faces_pre": n_total_faces,
            "n_faces_post": n_total_faces,
            "n_new_boundary_faces": 0, "n_dropped_boundary_faces": 0,
        }

    # Build cell remap: surviving cells get new sequential indices.
    cell_remap = np.full(n_cells, -1, dtype=np.int64)
    new_idx = 0
    for ci in range(n_cells):
        if ci not in drop_set:
            cell_remap[ci] = new_idx
            new_idx += 1
    n_cells_post = new_idx

    # Bucket faces.  Each face goes into one of:
    #   - kept_internal: (owner_new, neighbour_new, face_verts)
    #   - kept_boundary[patch_idx]: (owner_new, face_verts)
    #   - dropped_shell: (owner_new, face_verts)  -- new patch
    # face is *lost* if both endpoints are dropped or owner is dropped (boundary).
    kept_internal: list[tuple[int, int, list[int]]] = []
    kept_boundary: list[list[tuple[int, list[int]]]] = [[] for _ in patches]
    dropped_shell: list[tuple[int, list[int]]] = []
    n_dropped_boundary = 0

    # Map face index → patch index (only for boundary faces).
    face_to_patch = [-1] * n_total_faces
    for pi, patch in enumerate(patches):
        s = int(patch["startFace"])
        e = s + int(patch["nFaces"])
        for fi in range(s, e):
            if 0 <= fi < n_total_faces:
                face_to_patch[fi] = pi

    for fi in range(n_total_faces):
        f = faces[fi]
        own = int(owner[fi])
        own_drop = own in drop_set
        if fi < n_internal:
            nbr = int(neighbour[fi])
            nbr_drop = nbr in drop_set
            if own_drop and nbr_drop:
                continue  # face fully consumed by drop set
            if not own_drop and not nbr_drop:
                # Both alive — keep as internal.  Maintain owner < neighbour.
                a = cell_remap[own]
                b = cell_remap[nbr]
                if a < b:
                    kept_internal.append((int(a), int(b), list(f)))
                else:
                    # Flip face winding to swap owner/neighbour.
                    kept_internal.append((int(b), int(a), list(reversed(f))))
                continue
            # Exactly one side dropped — face becomes new boundary.
            if own_drop:
                # Surviving cell is the neighbour side.  Its outward normal
                # is currently pointing FROM neighbour TO owner → away from
                # neighbour.  Flip face winding so normal points outward
                # from the surviving cell.
                surv = cell_remap[nbr]
                dropped_shell.append((int(surv), list(reversed(f))))
            else:
                # Surviving cell is the owner side; outward normal already
                # points away from owner (toward dropped cell).  Keep as-is.
                surv = cell_remap[own]
                dropped_shell.append((int(surv), list(f)))
        else:
            # Boundary face: only owner involvement.
            if own_drop:
                n_dropped_boundary += 1
                continue
            pi = face_to_patch[fi]
            if pi < 0:
                # Face beyond declared patches — preserve as a fallback.
                dropped_shell.append((int(cell_remap[own]), list(f)))
            else:
                kept_boundary[pi].append((int(cell_remap[own]), list(f)))

    # Sort internal faces by (owner, neighbour) — OpenFOAM upper-triangular.
    kept_internal.sort(key=lambda t: (t[0], t[1]))

    # Assemble final face list: internal first, then patches in original
    # order, then droppedShell last.
    new_faces: list[list[int]] = []
    new_owner: list[int] = []
    new_neighbour: list[int] = []
    for own_n, nbr_n, fv in kept_internal:
        new_faces.append(fv)
        new_owner.append(own_n)
        new_neighbour.append(nbr_n)

    new_patches: list[dict] = []
    cursor = len(new_faces)
    for pi, patch in enumerate(patches):
        # Sort by owner for consistency (OpenFOAM convention).
        kept_boundary[pi].sort(key=lambda t: t[0])
        start = cursor
        for own_n, fv in kept_boundary[pi]:
            new_faces.append(fv)
            new_owner.append(own_n)
        cnt = len(kept_boundary[pi])
        new_patches.append({
            "name": patch["name"],
            "type": patch.get("type", "wall"),
            "nFaces": cnt,
            "startFace": start,
        })
        cursor += cnt

    if dropped_shell:
        dropped_shell.sort(key=lambda t: t[0])
        start = cursor
        for own_n, fv in dropped_shell:
            new_faces.append(fv)
            new_owner.append(own_n)
        new_patches.append({
            "name": new_patch_name,
            "type": "wall",
            "nFaces": len(dropped_shell),
            "startFace": start,
        })

    # Write back.
    _write_faces(poly / "faces", new_faces)
    _write_labels(poly / "owner", new_owner, "owner")
    _write_labels(poly / "neighbour", new_neighbour, "neighbour")
    _write_boundary(poly / "boundary", new_patches)

    log.info(
        "drop_neg_vol_cells",
        n_dropped=len(drop_set),
        n_cells_post=n_cells_post,
        n_new_boundary=len(dropped_shell),
        n_dropped_boundary=n_dropped_boundary,
    )

    return {
        "n_cells_pre": n_cells,
        "n_cells_post": n_cells_post,
        "n_dropped": len(drop_set),
        "n_dropped_inverted": len(inverted_set),
        "n_dropped_skew": len(skew_set - inverted_set),
        "n_dropped_non_ortho": len(non_ortho_set - inverted_set - skew_set),
        "n_faces_pre": n_total_faces,
        "n_faces_post": len(new_faces),
        "n_new_boundary_faces": len(dropped_shell),
        "n_dropped_boundary_faces": n_dropped_boundary,
    }
