"""native_poly solid-invariant gates — canonical measurement (CARD POLY-S1).

Ports the native_tet/native_hex solid-invariant methodology
(``tests/test_native_tet_solid_volume.py``, ``tests/test_native_hex_solid_volume.py``)
to the polyhedral-dual engine (``core/generator/native_poly/harness.py``).
native_poly was reported "~15%, unmeasured" — no canonical measurement protocol
existed, so its defects hid behind ``verdict=PASS_WITH_WARNINGS``. This file
makes the state MEASURABLE and locks whatever currently passes as a permanent
gate; what currently fails is recorded as ``xfail(strict=True)`` with the exact
measured numbers, so a silent regression *or* a silent fix both break CI (xpass
on strict=True fails the test, forcing this file to be updated).

Measured on ``tests/benchmarks/cube.stl`` (unit cube, bbox [-0.5, 0.5]^3,
surface area 6.000, volume 1.000) via the canonical path: draft / mesh_type
poly / ``tier_hint="native_poly"`` / ``strict_tier=True``. With ``bl_layers=0``
this routes to ``run_native_poly_harness`` (tet -> poly dual), NOT the scipy
Voronoi fallback (``core/generator/tier_native_poly.py:35-55`` — harness PASS).
N (target_cells/max_cells) is INERT on this path: it is accepted by the tier
runner signature but never forwarded to the harness (tier_native_poly.py:57-61)
— the dual is driven entirely by ``seed_density`` (fixed at 10), so the module
fixture below runs once at the default N with no loss of gate fidelity.

FOUR INDEPENDENT GATES (inherited from the tet/hex suites).  Total boundary
area is a trap: area lost on the real surface can be silently replaced by
interior-void walls, and volume can look plausible while the mesh bulges
outside the input. So each property is gated independently:

  1. surface coverage — area lying ON the input surface must equal 6.000.
  2. no interior voids — area lying OFF the input surface must be ~0.
  3. volume — cell volumes must sum to 1.000, none degenerate.
  4. no degenerate cells.

MEASURED (beta2826, CARD POLY-S3, cube.stl / draft / tier_native_poly,
cells=15, time~=50s, skew=0.457, negative_volumes=0, verdict=PASS):

  1. surface coverage:  6.000 (1.00x)  -> PASS  -> permanent gate.
  2. void (off-plane):  0.000 (<=0.30 allowed) -> PASS -> permanent gate
     (was 2.435 pre-POLY-S3, 7.588 pre-POLY-S2). Root cause fix: dual.py's
     ``is_cap`` classifier flagged any hull face touching >=1 surface point
     as a boundary cap, leaking inward-facing faces as one-sided boundary
     walls. POLY-S3 filters caps to "all vertices lie on one input surface
     plane" (``_surface_planes``) and closes the remaining boundary-edge
     seam with a topological separating face (``_ordered_tet_ring`` open
     fan + stable boundary-face-centroid / boundary-edge-midpoint dual
     point ids). A monotonic guard inside ``tet_to_poly_dual`` compares
     on/off-plane area of the new topological path against the old
     ConvexHull path and only adopts the new path when it does not regress
     either metric.
  3. volume Sigma|vol|: 1.077 (1.08x, >1.05 allowed) -> FAIL -> xfail(strict)
     (was 1.177 pre-POLY-S3). Root cause: closing the void (item 2) also
     tightened the boundary-cell decomposition, but a residual ~7.7%
     over-fill remains unresolved — POLY-S3 did not reach the <=1.05 bar
     the card targeted (prototype predicted 1.049); recorded here rather
     than force-closing the gate. See ``harness/plan_poly3.md`` for the next
     candidate (boundary-cell geometry refinement).
  4. degenerate cells: 0 -> PASS -> permanent gate.

Poly cells are arbitrary convex polyhedra (tet->dual duals), so tet's
|det|/6 does not apply. Volume is computed the same ORIENTATION-FREE way as
the hex suite's ``_cell_volumes``: decompose into centroid-apex pyramids over
each face, fan-triangulate each face, sum |tet vol| magnitudes — this is
correct for any convex cell regardless of polyMesh owner/neighbour sign.

MODULE-SCOPED FIXTURE.  Unlike the tet/hex suites (which re-run per test,
each run being fast), native_poly's harness path takes ~45s/run — re-running
per gate would blow the 3-minute test budget. The pipeline therefore runs
ONCE per module and all four gates read from the shared measurement.

Do NOT widen the xfail tolerances without re-measuring; do NOT flip the
permanent gates to xfail. POLY-S3 fixed void (now a permanent gate); if a
follow-up card fixes volume too, its ``strict=True`` xfail marker will XPASS
and fail the run — update this docstring and the marker together with the
fix, per the card sequence in ``harness/plan_poly1.md`` / ``plan_poly3.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import numpy as np
import pytest

from core.pipeline.orchestrator import PipelineOrchestrator
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

_CUBE = Path(__file__).resolve().parent / "benchmarks" / "cube.stl"
_TRUE_AREA = 6.0  # unit cube
_TRUE_VOLUME = 1.0
_PLANES = 0.5  # |x| = |y| = |z| = 0.5


def _face_area(pts: np.ndarray, face: list[int]) -> float:
    """|area| of a polygon face (arbitrary n-gon for poly) via fan triangulation."""
    p = pts[np.asarray(face, dtype=int)]
    acc = np.zeros(3)
    for i in range(1, len(face) - 1):
        acc = acc + np.cross(p[i] - p[0], p[i + 1] - p[0]) / 2.0
    return float(np.linalg.norm(acc))


def _boundary_area_split(poly_dir: Path) -> tuple[float, float]:
    """(area lying on the cube's 6 planes, area lying off them)."""
    pts = np.asarray(parse_foam_points(poly_dir / "points"), dtype=float)
    faces = [list(f) for f in parse_foam_faces(poly_dir / "faces")]
    n_internal = len(parse_foam_labels(poly_dir / "neighbour"))

    on_area = off_area = 0.0
    for face in faces[n_internal:]:
        p = pts[np.asarray(face, dtype=int)]
        a = _face_area(pts, face)
        on_plane = any(
            np.all(np.abs(p[:, ax] - s) < 1e-6) for ax in range(3) for s in (-_PLANES, _PLANES)
        )
        if on_plane:
            on_area += a
        else:
            off_area += a
    return on_area, off_area


def _cell_volumes(poly_dir: Path) -> np.ndarray:
    """|volume| of every poly cell, WITHOUT relying on face orientation.

    A poly cell is an arbitrary convex polyhedron (tet->dual output), so the
    tet's |det|/6 does not apply. Each cell's faces are pulled from
    owner/neighbour and the cell is decomposed into centroid-apex pyramids:
    fan-triangulate each face into tets (centroid, v0, vi, vi+1) and sum
    |det|/6 over every tet. For a convex cell with an interior apex the
    pyramids tile the cell without overlap, so the sum is the exact volume
    regardless of the polyMesh owner/neighbour sign convention. (Ported
    verbatim from ``tests/test_native_hex_solid_volume.py::_cell_volumes``.)
    """
    pts = np.asarray(parse_foam_points(poly_dir / "points"), dtype=float)
    faces = [list(f) for f in parse_foam_faces(poly_dir / "faces")]
    owner = np.asarray(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
    nb = np.asarray(parse_foam_labels(poly_dir / "neighbour"), dtype=np.int64)
    n_internal = len(nb)
    n_cells = int(max(owner.max(), nb.max() if nb.size else 0)) + 1

    cell_faces: list[list[list[int]]] = [[] for _ in range(n_cells)]
    for fi, face in enumerate(faces):
        o = int(owner[fi])
        if 0 <= o < n_cells:
            cell_faces[o].append(face)
        if fi < n_internal:
            n_ = int(nb[fi])
            if 0 <= n_ < n_cells:
                cell_faces[n_].append(face)

    vols = np.zeros(n_cells, dtype=float)
    for ci, cf in enumerate(cell_faces):
        verts = sorted({int(v) for f in cf for v in f})
        if len(verts) < 4:
            continue  # not a solid cell — leaves 0.0, caught by degenerate gate
        centroid = pts[np.asarray(verts, dtype=int)].mean(axis=0)
        total = 0.0
        for face in cf:
            p = pts[np.asarray(face, dtype=int)]
            for i in range(1, len(face) - 1):
                total += (
                    abs(
                        float(
                            np.dot(
                                p[0] - centroid,
                                np.cross(p[i] - centroid, p[i + 1] - centroid),
                            )
                        )
                    )
                    / 6.0
                )
        vols[ci] = total
    return vols


@pytest.fixture(scope="module")
def poly_case(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Run the canonical native_poly pipeline ONCE and share it across gates.

    The harness path takes ~45s/run; re-running per gate (as the tet/hex
    suites do) would blow the 3-minute test budget, so all four solid-
    invariant gates below read from this single module-scoped measurement.
    """
    case = tmp_path_factory.mktemp("native_poly_case") / "case"
    PipelineOrchestrator().run(
        _CUBE,
        case,
        quality_level="draft",
        mesh_type="poly",
        tier_hint="native_poly",
        max_iterations=1,
        auto_retry="off",
        strict_tier=True,
        write_of_case=True,
    )
    poly = case / "constant" / "polyMesh"
    assert (poly / "points").exists(), "polyMesh was not written"
    yield poly


def test_native_poly_covers_input_surface(poly_case: Path) -> None:
    """Boundary area lying ON the input surface must equal the input's area.

    Measured cube.stl / draft / tier_native_poly: on-plane boundary area
    6.000 (1.000x) — the dual harness reproduces the input surface exactly on
    the flat faces it does close. PERMANENT gate.
    """
    on_area, _ = _boundary_area_split(poly_case)
    ratio = on_area / _TRUE_AREA
    assert 0.95 <= ratio <= 1.05, (
        f"only {on_area:.3f} of the input's {_TRUE_AREA:.3f} surface area is "
        f"covered by boundary faces lying on it ({ratio:.3f}x) — the mesh's "
        f"boundary is not the input surface."
    )


def test_native_poly_has_no_degenerate_cells(poly_case: Path) -> None:
    """No cell may have (near) zero volume.

    Measured cube.stl / draft / tier_native_poly: 0 degenerate cells among 15.
    PERMANENT gate.
    """
    vols = _cell_volumes(poly_case)
    n_degenerate = int((vols < 1e-12).sum())
    assert n_degenerate == 0, (
        f"{n_degenerate}/{vols.size} cells have (near) zero volume — these are "
        f"collapsed poly cells."
    )


def test_native_poly_has_no_interior_voids(poly_case: Path) -> None:
    """No boundary area may lie off the input surface (that would be a void wall).

    A watertight input has exactly one boundary: itself. Measured cube.stl /
    draft / tier_native_poly (post-POLY-S3): off-plane boundary area 0.000
    (was 2.435 pre-POLY-S3, 7.588 pre-POLY-S2). POLY-S3's on-plane cap filter
    plus topological boundary-edge separating face closed the leak entirely.
    PERMANENT gate.
    """
    _, off_area = _boundary_area_split(poly_case)
    assert off_area <= 0.05 * _TRUE_AREA, (
        f"{off_area:.3f} of boundary area lies off the input surface — these "
        f"are interior void walls."
    )


@pytest.mark.xfail(
    reason=(
        "measured 1.077x (Sigma|vol|=1.077, down from 1.177 pre-POLY-S3) — "
        "POLY-S3 closed the interior void (see gate above) but a residual "
        "~7.7% boundary-cell over-fill remains, still above the 1.05 "
        "threshold — see module docstring; open for a follow-up card."
    ),
    strict=True,
)
def test_native_poly_encloses_true_volume(poly_case: Path) -> None:
    """Cell volumes must sum to the input's volume — i.e. the cells tile it.

    Measured cube.stl / draft / tier_native_poly (post-POLY-S3): Sigma|vol|
    1.077 (1.08x), down from 1.177 (1.18x) pre-POLY-S3. Closing the interior
    void (see the void gate above) reduced but did not eliminate the
    boundary-cell over-fill. XFAIL(strict) — still above the 1.05 tolerance;
    scoped to a follow-up card (see harness/plan_poly3.md "다음 후보").
    """
    vols = _cell_volumes(poly_case)
    total = float(vols.sum())
    ratio = total / _TRUE_VOLUME
    assert 0.95 <= ratio <= 1.05, (
        f"cell volumes sum to {total:.3f} = {ratio:.2f}x the input's true "
        f"volume {_TRUE_VOLUME:.3f} — the cells do not tile the input "
        f"(<1 = gaps, >1 = overlap)."
    )
