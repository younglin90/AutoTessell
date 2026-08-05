"""CARD FSL4 -- dual-torus 2-boundary-face wedge = confirmed structural known-limit.

Closes the flat-all-surface-sliver sequence on
``tests/benchmarks/high_genus_dual_torus.stl``: FSL1 (detector) -> FSL3
(guarded 2-3 flip, measured 0/9 eligible wedges actually flipped -- all
revert on the min_q guard) -> FSL4 here.  This file does NOT attempt a cure.
It locks the current PASS state (gate A) and pins the cure's known shape as
an xfail(strict) gate (gate B), so a future cure attempt lands as a loud
XPASS -> FAIL alarm instead of a silent regression.

Root cause (measured, see research/quality-harness/plan_fsl4.md and plan_torus_quality.md):

  - The FSL1 detector's 61 core-unflippable wedges all have exactly 2
    boundary faces.  57/61 are coplanar flat-on-surface -- the wedge's two
    boundary faces lie in (nearly) the same plane, dihedral mean 0.74 deg
    / max 11.2 deg.  dual_torus is a thin washer (z in [-0.5, 0.5]) so a
    wedge pinched between the two washer walls collapses onto one wall
    instead of spanning the gap.
  - Approach (a) -- a surface-edge-preserving re-split that inserts a new
    vertex between the wedge's two boundary faces -- is falsified by
    measurement: the wedge's 4 vertices are already coplanar (smallest
    singular value 4.7e-9), so ANY new vertex placed on the true envelope
    (input surface) sits on that same plane too.  A re-split still produces
    coplanar sub-tets -- boundary skew is unchanged -- while adding a
    surface vertex threatens invariant #1 (surface preservation) for no
    gain.  (a) is structurally impossible for this geometry, not merely
    difficult.
  - Approach (b) -- insert an interior offset apex
    (centroid - normal * 0.5 * edge_max) and re-triangulate the wedge's two
    boundary faces around it -- is the only measured cure: worst-wedge
    boundary skew drops 2.94e7 -> 0.34 with the tet's signed volume
    unchanged in sign.  But this requires a full interior cavity
    re-tetrahedralization with neg-vol/void/surface guards across the
    wedge fan -- the same class of problem as cylinder skew 44.9
    (BETA2829, Garimella near-wall point insertion), already confirmed
    multi-card and out of this card's <=80-line scope.

So: gate A locks the #1 invariant (volume tiling) that BETA2832 recovered
for dual_torus -- no future FSL4-cure attempt at the flat-wedge problem may
regress it.  Gate B pins the cure target as a strict xfail so it becomes a
loud signal once the Garimella-style near-wall insertion (separate,
multi-card roadmap item) lands.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.file_reader import load_mesh
from core.evaluator.native_checker import NativeMeshChecker
from core.generator.native_tet.mesher import generate_native_tet
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

_DUAL_TORUS = Path(__file__).resolve().parent / "benchmarks" / "high_genus_dual_torus.stl"


@pytest.fixture(scope="module")
def dual_torus_mesh(tmp_path_factory):
    """Single shared native_tet run for this file.

    Calling generate_native_tet a second time in the same process on this
    geometry (12k+ cells, deep rebudget) was observed to crash the
    interpreter with a non-deterministic access-violation (different stack
    trace each time: aabb.py, mean_curvature.py -- classic native-heap
    corruption signature, not a Python logic bug). It reproduces reliably
    inside pytest but not in a bare `python -c` script running the same call
    twice, so it looks specific to pytest's process/threading setup rather
    than the geometry alone. Root-causing the native extension is out of
    scope here; sharing one run across both gates in this file sidesteps the
    trigger entirely (and is cheaper anyway).
    """
    prev = os.environ.get("AUTO_TESSELL_P4C_PYTETWILD")
    os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
    try:
        case_dir = tmp_path_factory.mktemp("case")
        mesh = load_mesh(_DUAL_TORUS)
        vertices = np.asarray(mesh.vertices, dtype=float)
        faces = np.asarray(mesh.faces, dtype=np.int64)
        result = generate_native_tet(vertices, faces, case_dir, target_cells=600)
        poly = case_dir / "constant" / "polyMesh"
        assert (poly / "points").exists(), "polyMesh was not written"
        return result, case_dir, vertices, faces
    finally:
        if prev is None:
            os.environ.pop("AUTO_TESSELL_P4C_PYTETWILD", None)
        else:
            os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = prev


def _cell_volumes(poly_dir: Path) -> np.ndarray:
    """|volume| of every cell, orientation-free (abs(det)/6 per tet).

    Mirrors ``tests/test_native_tet_solid_volume.py::_cell_volumes`` -- a
    face-orientation-based (divergence theorem) volume inherits any error in
    the polyMesh's face orientation, so pull each cell's 4 vertices straight
    from its faces instead.
    """
    pts = np.asarray(parse_foam_points(poly_dir / "points"), dtype=float)
    faces = [list(f) for f in parse_foam_faces(poly_dir / "faces")]
    owner = np.asarray(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
    nb = np.asarray(parse_foam_labels(poly_dir / "neighbour"), dtype=np.int64)
    n_internal = len(nb)
    n_cells = int(max(owner.max(), nb.max() if nb.size else 0)) + 1

    verts: list[set[int]] = [set() for _ in range(n_cells)]
    for fi, face in enumerate(faces):
        o = int(owner[fi])
        if 0 <= o < n_cells:
            verts[o].update(int(v) for v in face)
        if fi < n_internal:
            n_ = int(nb[fi])
            if 0 <= n_ < n_cells:
                verts[n_].update(int(v) for v in face)

    vols = np.zeros(n_cells, dtype=float)
    for ci, s in enumerate(verts):
        if len(s) != 4:
            continue  # not a tet -- leaves 0.0
        p = pts[np.asarray(sorted(s), dtype=int)]
        vols[ci] = abs(
            float(np.dot(p[1] - p[0], np.cross(p[2] - p[0], p[3] - p[0])))
        ) / 6.0
    return vols


def _input_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    """|signed volume| of the input surface (divergence theorem)."""
    vol = 0.0
    for f in faces:
        a, b, c = vertices[f[0]], vertices[f[1]], vertices[f[2]]
        vol += float(np.dot(a, np.cross(b, c)))
    return abs(vol) / 6.0


def test_dual_torus_volume_tiling_locked(dual_torus_mesh) -> None:
    """Gate A (#1 invariant lock, highest-priority guard in this file).

    sum|cell vol| / input_vol must stay in [0.95, 1.05] and grade must stay
    >= B.  Measured: ratio 0.9913, input_vol=19.4868, grade B.  BETA2832
    recovered dual_torus's volume-tiling from a broken state -- no future
    FSL4-cure attempt at the flat-wedge problem may regress it.
    """
    result, case_dir, vertices, faces = dual_torus_mesh

    input_vol = _input_volume(vertices, faces)
    poly = case_dir / "constant" / "polyMesh"
    total = float(_cell_volumes(poly).sum())
    ratio = total / input_vol
    assert 0.95 <= ratio <= 1.05, (
        f"cell volumes sum to {total:.4f} = {ratio:.4f}x the input's "
        f"{input_vol:.4f} volume -- dual_torus volume-tiling regressed."
    )
    assert result.quality_grade in ("A", "B"), (
        f"grade regressed to {result.quality_grade!r} (expected >= B)"
    )


@pytest.mark.xfail(strict=True, reason=(
    "structural known-limit -- 57/61 unflippable wedges are coplanar "
    "flat-on-surface (dihedral mean 0.74deg/max 11.2deg); the only measured "
    "cure is an interior offset-apex re-tet (2.94e7 -> 0.34), a multi-card "
    "Garimella near-wall insertion effort (same class as cylinder skew 44.9 "
    "/ BETA2829), out of this card's scope."
))
def test_dual_torus_boundary_skew_cure_target(dual_torus_mesh) -> None:
    """Gate B (cure target, expected xfail).

    max_boundary_skew, recomputed via
    ``NativeMeshChecker._compute_boundary_skewness`` (owner-centroid
    tangential-miss / normal_dist), should be < 100.0.  Currently measures
    ~2.94e7.  This is EXPECTED to fail: strict xfail means an unexpected
    pass (XPASS) is reported as a hard failure -- the intended "cure landed"
    alarm for the Garimella near-wall insertion roadmap item.
    """
    _, case_dir, _, _ = dual_torus_mesh

    report = NativeMeshChecker().run(case_dir)
    max_bskew = float(report.max_boundary_skewness or 0.0)
    assert max_bskew < 100.0, (
        f"max_boundary_skew = {max_bskew:.3e} (target < 100.0) -- "
        f"structural known-limit, cure out of this card's scope."
    )
