"""native_hex must actually mesh the input solid — surface, voids, volume.

Ports the native_tet solid-invariant methodology
(``tests/test_native_tet_solid_volume.py``) to the hex-dominant engine
(``core/generator/native_hex/mesher.py``).  native_tet reached surface 6.000 /
void 0.000 / volume ~1.0 / no-degenerate under "canonical smoke + solid
invariant gates -> quality"; native_hex had never had the same instrumentation
(reported "~15%, unmeasured").  This file makes the state MEASURABLE and locks
whatever passes as a permanent gate.

Measured on ``tests/benchmarks/cube.stl``: the unit cube, bbox exactly
[-0.5, 0.5]^3, surface area 6.000, volume 1.000.  native_hex is a pure-Python
uniform-grid + inside-filter engine with NO external subprocess fallback (no
cfMesh / snappyHexMesh shell-out anywhere under ``core/generator/native_hex/``),
so ``tier_hint="native_hex"`` + ``strict_tier=True`` fully isolate the
self-implementation — there is no ``AUTO_TESSELL_P4C_PYTETWILD`` equivalent.

WHY THE CUBE PASSES CLEANLY.  A unit cube is axis-aligned, so a uniform hex grid
tiles it with ZERO staircase error: every cell is a perfect axis-aligned box.
This is the best case for a Cartesian hex engine, and native_hex nails it —
measured cube.stl / draft / N=2000: surface 6.000, off-plane 0.000, Σ|vol|
1.000, 0 degenerate, skew 3.6e-16, verdict PASS.  The staircase defect lives on
CURVED / ANGLED surfaces (measured cylinder.stl / draft / N=2000: wall-radius
deviation up to 0.047 against the true r=0.5 while skew stays ~0 because draft
keeps the boxes axis-aligned).  A curved-surface fidelity gate is the natural
next card; this file gates the exact-geometry cube, exactly as the tet suite
does.

WHY THREE SEPARATE GATES (inherited from the tet suite).  Total boundary area is
a trap: area lost on the real surface can be silently replaced by interior-void
walls.  So the properties are gated independently:

  1. surface coverage — area lying ON the input surface must equal 6.000.
  2. no interior voids — area lying OFF the input surface must be ~0.
  3. volume — cell volumes must sum to 1.000 with none degenerate.

HEX vs TET measurement.  Boundary faces are QUADS — the fan-triangulation area
logic is unchanged (it already handles n-gons).  A hex cell has 8 vertices, so
the tet's |det|/6 does not apply; cell volume is computed ORIENTATION-FREE by
decomposing the convex cell into centroid-apex pyramids over its faces and
summing per-tet magnitudes, independent of the polyMesh owner/neighbour sign
convention (measure the geometry, not the bookkeeping).

Do NOT widen these tolerances.  The unit cube's area and volume are exact
geometry, not tuning knobs.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from core.pipeline.orchestrator import PipelineOrchestrator
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

_CUBE = Path(__file__).resolve().parent / "benchmarks" / "cube.stl"
_CYLINDER = Path(__file__).resolve().parent / "benchmarks" / "cylinder.stl"
_TRUE_AREA = 6.0  # unit cube
_TRUE_VOLUME = 1.0
_PLANES = 0.5  # |x| = |y| = |z| = 0.5
_CYL_RADIUS = 0.5  # cylinder.stl side-wall radius
_CYL_Z_SIDE = 0.49  # |z| < this => curved side wall, not the flat end caps

# Default N=2000 (calibrated gate). The solid invariants (surface 6.0, void 0,
# volume ~1.0, no degenerate) hold at every N, so a smaller mesh is a faithful,
# faster check. See scripts/smoke_native_hex.py.
_TEST_CELLS = int(os.environ.get("AUTO_TESSELL_TEST_CELLS", "2000"))


def _run_native_hex(case: Path) -> Path:
    PipelineOrchestrator().run(
        _CUBE,
        case,
        quality_level="draft",
        mesh_type="hex_dominant",
        tier_hint="native_hex",
        max_iterations=1,
        auto_retry="off",
        strict_tier=True,
        write_of_case=True,
        max_cells=_TEST_CELLS,
        tier_specific_params={
            "max_cells": _TEST_CELLS,
            "target_cells": _TEST_CELLS,
        },
    )
    poly = case / "constant" / "polyMesh"
    assert (poly / "points").exists(), "polyMesh was not written"
    return poly


def _face_area(pts: np.ndarray, face: list[int]) -> float:
    """|area| of a polygon face (quad for hex) via fan triangulation."""
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
    """|volume| of every hex cell, WITHOUT relying on face orientation.

    A hex cell has 8 vertices, so the tet's |det|/6 does not apply.  Each cell's
    faces are pulled from owner/neighbour and the cell is decomposed into
    centroid-apex pyramids: fan-triangulate each face into tets (centroid, v0,
    vi, vi+1) and sum |det|/6 over every tet.  For a convex cell with an interior
    apex the pyramids tile the cell without overlap, so the sum is the exact
    volume regardless of the polyMesh owner/neighbour sign convention (a
    face-based divergence volume would inherit any face-orientation error).
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


def test_native_hex_covers_input_surface(tmp_path: Path) -> None:
    """Boundary area lying ON the input surface must equal the input's area.

    On the axis-aligned unit cube a uniform hex grid meshes the surface exactly:
    measured cube.stl / draft / N=2000 the on-plane boundary area is 6.000
    (1.000x).  A total-area check would miss interior-void walls; this gate does
    not.
    """
    poly = _run_native_hex(tmp_path / "case")

    on_area, _ = _boundary_area_split(poly)
    ratio = on_area / _TRUE_AREA
    assert 0.95 <= ratio <= 1.05, (
        f"only {on_area:.3f} of the input's {_TRUE_AREA:.3f} surface area is "
        f"covered by boundary faces lying on it ({ratio:.3f}x) — the mesh's "
        f"boundary is not the input surface."
    )


def test_native_hex_has_no_interior_voids(tmp_path: Path) -> None:
    """No boundary area may lie off the input surface (that would be a void wall).

    A watertight input has exactly one boundary: itself.  Any boundary face not
    on the input surface is the wall of a hole in the volume.  Measured cube.stl
    / draft / N=2000: off-plane boundary area 0.000 — the inside filter keeps a
    solid block of cells with no interior holes.
    """
    poly = _run_native_hex(tmp_path / "case")

    _, off_area = _boundary_area_split(poly)
    assert off_area <= 0.05 * _TRUE_AREA, (
        f"{off_area:.3f} of boundary area lies off the input surface — these "
        f"are interior void walls."
    )


def test_native_hex_mesh_encloses_true_volume(tmp_path: Path) -> None:
    """Cell volumes must sum to the input's volume — i.e. the cells tile it.

    Sum |hex volume| (orientation-free) over every cell.  For a valid hex mesh of
    the input this equals the input's volume: less means gaps, more means the
    cells overlap.  Measured cube.stl / draft / N=2000: Σ|vol| 1.000 (1.00x), so
    the hexes tile the cube cleanly.
    """
    poly = _run_native_hex(tmp_path / "case")

    vols = _cell_volumes(poly)
    total = float(vols.sum())
    ratio = total / _TRUE_VOLUME
    assert 0.95 <= ratio <= 1.05, (
        f"cell volumes sum to {total:.3f} = {ratio:.2f}x the input's true "
        f"volume {_TRUE_VOLUME:.3f} — the cells do not tile the input "
        f"(<1 = gaps, >1 = overlap)."
    )


def test_native_hex_has_no_degenerate_cells(tmp_path: Path) -> None:
    """No cell may have (near) zero volume.

    A zero-volume hex is a collapsed box: it has no interior, its skewness is
    unbounded, and a solver cannot integrate over it.  Measured cube.stl / draft
    / N=2000: 0 degenerate cells (mesher's VAL2 reports n_degenerate 0,
    n_flipped 0), max_skewness 3.6e-16.
    """
    poly = _run_native_hex(tmp_path / "case")

    vols = _cell_volumes(poly)
    # 1e-12 against a mean cell volume of ~5e-4 — nine orders down, unambiguous.
    n_degenerate = int((vols < 1e-12).sum())
    assert n_degenerate == 0, (
        f"{n_degenerate}/{vols.size} cells have (near) zero volume — these are "
        f"collapsed hexes and drive max_skewness unbounded."
    )


# ---------------------------------------------------------------------------
# Curved-surface fidelity — the gate the cube CANNOT provide.
# ---------------------------------------------------------------------------


def _cylinder_wall_deviation(poly_dir: Path) -> tuple[float, float, int]:
    """(max, mean, n) |radius - 0.5| over side-wall boundary vertices."""
    pts = np.asarray(parse_foam_points(poly_dir / "points"), dtype=float)
    faces = [list(f) for f in parse_foam_faces(poly_dir / "faces")]
    n_internal = len(parse_foam_labels(poly_dir / "neighbour"))
    bnd: set[int] = set()
    for face in faces[n_internal:]:
        bnd.update(int(v) for v in face)
    bp = pts[np.asarray(sorted(bnd), dtype=int)]
    side = np.abs(bp[:, 2]) < _CYL_Z_SIDE
    r = np.hypot(bp[side, 0], bp[side, 1])
    dev = np.abs(r - _CYL_RADIUS)
    if dev.size == 0:
        return 0.0, 0.0, 0
    return float(dev.max()), float(dev.mean()), int(dev.size)


@pytest.mark.parametrize(
    "quality_level",
    ["standard", "fine"],
)
def test_native_hex_curved_wall_fidelity(tmp_path: Path, quality_level: str) -> None:
    """Side-wall vertices of a meshed cylinder must sit on the true radius.

    This is why the cube is not enough: the cube is axis-aligned, so a Cartesian
    hex grid meshes it with zero error and every solid gate passes trivially. The
    cylinder is the first input that actually exercises how the engine handles a
    surface the grid does not align with.

    STATUS (BETA_HEX_WALLFIT, standard / N=2000): the per-vertex guarded wall-fit
    (mesher.py ``_wall_fit_snap``) projects side-wall vertices onto the input
    triangles inside a ``ratio * edge`` envelope, accepting a move only when the
    surface distance strictly decreases AND every incident cell stays
    non-inverted / non-collapsed. Measured max wall deviation 0.003 (was 0.047 as
    a raw staircase), mean 0.0015, negative_volumes 0, mesh_ok True — a fit, not a
    staircase. Was xfail (draft leaves axis-aligned boxes); now a permanent gate
    on the standard snap path.

    STATUS (CARD HEX-WALLFIT-FINE): fine quality (n_levels=4) was hypothesized to
    fail because the global envelope cap was sized to the finest octree cell, too
    small for wall vertices sitting on a coarse (level 0/1) cell. The envelope was
    generalized to per-vertex (``ratio * max(target_edge, local_scale[v])``) and
    verified harmless (standard unchanged, cube/negative_volumes unaffected) — but
    measurement showed the hypothesis was wrong: n_reject_envelope=0 both before
    and after, so envelope was never the actual limiter here. The real blocker was
    the no-inversion guard rejecting full projections outright (n_reject_vol=39/389
    at that time), out of that card's scope.

    STATUS (CARD HEX-WALLFIT-BACKTRACK): the all-or-nothing revert on a rejected
    full projection was replaced with a bisection backtrack (<=12 iters) to the
    largest fraction of orig->p0 that still passes the same ``_cell_ok`` guard,
    gated by the same strict-decrease check. Measured (cylinder N=2000, fine):
    n_target=350, n_snapped=320, n_snapped_partial=30, n_reject_vol=0, max wall
    deviation 0.0080 (was ~0.035), mean 0.0014, negative_volumes 0. standard is
    unchanged (n_reject_vol=0 both before/after, this code path never triggers;
    max_dev 0.00324). fine is now a permanent gate alongside standard.
    """
    case = tmp_path / "case"
    PipelineOrchestrator().run(
        _CYLINDER,
        case,
        quality_level=quality_level,
        mesh_type="hex_dominant",
        tier_hint="native_hex",
        max_iterations=1,
        auto_retry="off",
        strict_tier=True,
        write_of_case=True,
        max_cells=_TEST_CELLS,
        tier_specific_params={"max_cells": _TEST_CELLS, "target_cells": _TEST_CELLS},
    )
    poly = case / "constant" / "polyMesh"
    assert (poly / "points").exists(), "polyMesh was not written"

    max_dev, mean_dev, n_side = _cylinder_wall_deviation(poly)
    assert n_side >= 20, f"too few side-wall vertices ({n_side}) to judge fidelity"
    assert max_dev <= 0.02, (
        f"cylinder side-wall ({quality_level}) deviates up to {max_dev:.3f} from "
        f"the true radius {_CYL_RADIUS} (mean {mean_dev:.3f}, n={n_side}) — the "
        f"hex grid is staircasing the curved wall instead of fitting it."
    )


def test_native_hex_standard_boundary_skew(tmp_path: Path) -> None:
    """CARD HEX-SKEW-INNER-RELAX: boundary skewness gate on cylinder / standard.

    Root cause (measured): ``_wall_fit_snap`` collapses the owner-cell
    wall-normal thickness |nd| of side-wall boundary cells (0.03 -> 0.0088),
    which blows up checker boundary skewness (tmiss/|nd|) to 4.64 even though
    wall_dev stays good. ``_relax_boundary_sliver_interior`` relaxes only the
    free (non-boundary) vertices of sliver cells inward, under a smart
    accept/revert guard measured on the final mesh.
    """
    case = tmp_path / "case"
    res = PipelineOrchestrator().run(
        _CYLINDER,
        case,
        quality_level="standard",
        mesh_type="hex_dominant",
        tier_hint="native_hex",
        max_iterations=1,
        auto_retry="off",
        strict_tier=True,
        write_of_case=True,
        max_cells=_TEST_CELLS,
        tier_specific_params={"max_cells": _TEST_CELLS, "target_cells": _TEST_CELLS},
    )
    assert res.quality_report is not None
    checkmesh = res.quality_report.evaluation_summary.checkmesh
    assert checkmesh.max_boundary_skewness is not None
    assert checkmesh.max_boundary_skewness <= 3.0, (
        f"cylinder standard boundary skewness {checkmesh.max_boundary_skewness:.3f} "
        f"> 3.0 gate — _relax_boundary_sliver_interior failed to restore "
        f"wall-normal thickness."
    )


@pytest.mark.parametrize(
    "quality_level",
    ["standard", "fine"],
)
def test_native_hex_no_negative_volumes(tmp_path: Path, quality_level: str) -> None:
    """No cell may have a negative (inverted) volume — cylinder, standard & fine.

    Discovered while building CARD HEX-SKEW-INNER-RELAX: with
    ``_relax_boundary_sliver_interior`` disabled (env
    ``AUTO_TESSELL_HEX_SKEW_RELAX_OFF=1``), cylinder.stl fine / N=2000 produced
    checker ``negative_volumes=8`` — a pre-existing defect no test asserted on,
    so it went unnoticed. relax is ON by default and measured to bring
    negative_volumes to 0; this test locks that in as a permanent gate so any
    regression (including a silent one from someone flipping the kill-switch
    default) is caught.
    """
    case = tmp_path / "case"
    res = PipelineOrchestrator().run(
        _CYLINDER,
        case,
        quality_level=quality_level,
        mesh_type="hex_dominant",
        tier_hint="native_hex",
        max_iterations=1,
        auto_retry="off",
        strict_tier=True,
        write_of_case=True,
        max_cells=_TEST_CELLS,
        tier_specific_params={"max_cells": _TEST_CELLS, "target_cells": _TEST_CELLS},
    )
    assert res.quality_report is not None
    checkmesh = res.quality_report.evaluation_summary.checkmesh
    assert checkmesh.negative_volumes == 0, (
        f"cylinder {quality_level} negative_volumes={checkmesh.negative_volumes} "
        f"> 0 — some cells are inverted."
    )
