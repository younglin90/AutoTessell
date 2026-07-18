"""CARD BOOLMERGE4 — per-original-surface OR inclusion e2e.

Wires GWN (generalized winding number) additivity — proven at the unit level
by BOOLMERGE1 (``core/utils/geometry.inside_union_winding_number``,
``tests/test_geometry_boolean_merge.py``) — through the user-facing
``PipelineOrchestrator.run()`` entry point for the first time.

Two overlapping unit cubes are pre-merged for bbox, seeding, and surface
vertices. Final tet centroids are classified against each original STL and
combined with OR. This retains overlap tets that combined-soup ray parity
incorrectly rejected in BOOLMERGE3.

Geometry: A=[0,1]^3, B=[0.5,1.5]^3 -> analytic union volume = 1.875.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.pipeline.orchestrator import PipelineOrchestrator
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)
from core.utils.stl_writer import write_stl_binary

# 2500 is a measured, deterministic sweet spot for this concave (two
# overlapping cubes) shape: swept 1500/2000/2500/3000/3500/4000/6000/12000 —
# below ~2500 the mesher settles into a coarser regime that under-resolves
# the union's re-entrant corner (vol ~1.51-1.57, outside the accept band);
# at 2500 BOOLMERGE3 reproducibly landed on vol=1.7574, the symmetric
# difference. BOOLMERGE4 must recover the overlap and approach union=1.875.
_TEST_CELLS = 2500


# ---------------------------------------------------------------------------
# Geometry helpers (mirrors tests/test_geometry_boolean_merge.py)
# ---------------------------------------------------------------------------


def _unit_cube_mesh() -> tuple[np.ndarray, np.ndarray]:
    """[0,1]^3 axis-aligned cube surface (8 verts + 12 triangles)."""
    V = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [1, 1, 1],
            [0, 1, 1],
        ],
        dtype=np.float64,
    )
    F = np.array(
        [
            [0, 2, 1],
            [0, 3, 2],  # bottom (z=0)
            [4, 5, 6],
            [4, 6, 7],  # top (z=1)
            [0, 1, 5],
            [0, 5, 4],  # front (y=0)
            [2, 3, 7],
            [2, 7, 6],  # back  (y=1)
            [1, 2, 6],
            [1, 6, 5],  # right (x=1)
            [0, 4, 7],
            [0, 7, 3],  # left  (x=0)
        ],
        dtype=np.int64,
    )
    return V, F


def _cube_mesh(lo: float, hi: float) -> tuple[np.ndarray, np.ndarray]:
    """[lo, hi]^3 axis-aligned cube — scaled/translated unit cube."""
    V, F = _unit_cube_mesh()
    return V * (hi - lo) + lo, F


# ---------------------------------------------------------------------------
# polyMesh cell-volume helper (mirrors tests/test_native_tet_solid_volume.py)
# ---------------------------------------------------------------------------


def _cell_volumes(poly_dir: Path) -> np.ndarray:
    """|volume| of every cell, computed from its 4 unique face vertices.

    Orientation-free (|det|/6) so it is not sensitive to boundary-face
    winding errors — measures the geometry, not the bookkeeping.
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
            continue  # not a tet — leaves 0.0
        p = pts[np.asarray(sorted(s), dtype=int)]
        vols[ci] = abs(float(np.dot(p[1] - p[0], np.cross(p[2] - p[0], p[3] - p[0])))) / 6.0
    return vols


# ---------------------------------------------------------------------------
# Surface preservation helper — nearest point on the output boundary mesh
# ---------------------------------------------------------------------------


def _nearest_dist_to_boundary(case_dir: Path, points: np.ndarray) -> np.ndarray:
    """Distance from each query point to the closest triangle of the output
    boundary mesh — reuses the fidelity-checker's polyMesh boundary extractor
    and trimesh's exact point-to-triangle distance."""
    from core.evaluator.fidelity import GeometryFidelityChecker

    boundary = GeometryFidelityChecker()._extract_boundary_mesh(case_dir)
    assert boundary is not None, "polyMesh boundary extraction failed"

    try:
        from trimesh.proximity import closest_point

        _, dist, _ = closest_point(boundary, points)
        return np.asarray(dist, dtype=np.float64)
    except Exception:
        # Fallback: nearest-vertex distance (upper bound on surface distance).
        verts = np.asarray(boundary.vertices, dtype=np.float64)
        d = np.linalg.norm(points[:, None, :] - verts[None, :, :], axis=2)
        return d.min(axis=1)


def _write_cube_stl(path: Path, lo: float, hi: float) -> None:
    V, F = _cube_mesh(lo, hi)
    res = write_stl_binary(V, F, path)
    assert res.success, res.message


def test_boolean_merge_requires_two_surfaces(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least two"):
        PipelineOrchestrator._premerge_surfaces_for_union([], tmp_path)


def test_boolean_union_original_inputs_retain_overlap(tmp_path: Path) -> None:
    """A point inside both inputs remains inside under per-surface OR."""
    from core.generator.native_tet.mesher import _inside_boolean_union_inputs

    a_path = tmp_path / "cube_a.stl"
    b_path = tmp_path / "cube_b.stl"
    _write_cube_stl(a_path, 0.0, 1.0)
    _write_cube_stl(b_path, 0.5, 1.5)

    points = np.array(
        [
            [0.75, 0.75, 0.75],  # overlap: inside A and B
            [1.25, 1.25, 1.25],  # B only
            [2.0, 2.0, 2.0],     # outside both
        ],
        dtype=np.float64,
    )
    mask = _inside_boolean_union_inputs(points, [str(a_path), str(b_path)])

    assert mask.tolist() == [True, True, False]


def test_boolean_union_three_inputs_accept_each_body_and_overlaps(
    tmp_path: Path,
) -> None:
    """Per-surface OR supports N inputs without combined-soup parity errors."""
    from core.generator.native_tet.mesher import _inside_boolean_union_inputs

    paths = [tmp_path / f"cube_{name}.stl" for name in ("a", "b", "c")]
    for path, (lo, hi) in zip(
        paths,
        ((0.0, 1.0), (0.5, 1.5), (1.0, 2.0)),
        strict=True,
    ):
        _write_cube_stl(path, lo, hi)

    points = np.array(
        [
            [0.25, 0.25, 0.25],  # A only
            [0.75, 1.25, 0.75],  # B only
            [1.75, 1.75, 1.75],  # C only
            [0.75, 0.75, 0.75],  # A/B overlap
            [1.25, 1.25, 1.25],  # B/C overlap
            [3.0, 3.0, 3.0],     # outside all inputs
        ],
        dtype=np.float64,
    )

    mask = _inside_boolean_union_inputs(points, [str(path) for path in paths])

    assert mask.tolist() == [True, True, True, True, True, False]


def test_boolean_merge_union_e2e(tmp_path: Path, monkeypatch) -> None:
    """Two overlapping unit cubes merged through additional_input_paths.

    Gate criteria (CARD BOOLMERGE4):
      - success + n_cells > 0.
      - sum |cell vol| in [1.82, 1.95] (union=1.875, rejects XOR=1.75).
      - vol_merged > vol_single_cube(~1.0) + 0.5 -> merge actually happened.
      - surface preservation: sample faces from each original cube (outside
        the other cube's extent) stay within envelope of the output boundary.
    """
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")

    a_path = tmp_path / "cube_a.stl"
    b_path = tmp_path / "cube_b.stl"
    _write_cube_stl(a_path, 0.0, 1.0)
    _write_cube_stl(b_path, 0.5, 1.5)

    case_dir = tmp_path / "case"
    tier_params = {
        "max_cells": _TEST_CELLS,
        "target_cells": _TEST_CELLS,
    }
    result = PipelineOrchestrator().run(
        a_path,
        case_dir,
        additional_input_paths=[b_path],
        mesh_type="tet",
        tier_hint="auto",
        quality_level="draft",
        max_iterations=1,
        auto_retry="off",
        write_of_case=True,
        max_cells=_TEST_CELLS,
        tier_specific_params=tier_params,
    )

    assert tier_params == {
        "max_cells": _TEST_CELLS,
        "target_cells": _TEST_CELLS,
    }, "orchestrator mutated caller-owned tier_specific_params"
    assert result.strategy is not None
    assert result.strategy.selected_tier == "tier_native_tet"
    assert result.strategy.tier_specific_params["boolean_union_input_paths"] == [
        str(a_path),
        str(b_path),
    ]

    assert result.success is True, f"pipeline failed: {result.error}"
    poly_dir = case_dir / "constant" / "polyMesh"
    assert (poly_dir / "points").exists(), "polyMesh was not written"

    # --- 4 canonical invariants via the canonical NativeMeshChecker ---
    # (this is the same evaluator the orchestrator's PASS/PASS_WITH_WARNINGS
    # verdict above was already computed from — asserted explicitly here so
    # the "void-free / degenerate-free / valid coverage" invariants are
    # visible in this test, not just implied by result.success).
    assert result.quality_report is not None, "no quality_report produced"
    checkmesh = result.quality_report.evaluation_summary.checkmesh
    assert checkmesh.negative_volumes == 0, (
        f"{checkmesh.negative_volumes} negative-volume cells — void/inversion "
        f"present in the merged mesh."
    )
    assert checkmesh.cells > 0
    verdict = result.quality_report.evaluation_summary.verdict
    assert verdict in ("PASS", "PASS_WITH_WARNINGS"), f"verdict={verdict}"

    vols = _cell_volumes(poly_dir)
    n_cells = int((vols > 0).sum())
    assert n_cells > 0, "no valid tet cells produced"

    total_vol = float(vols.sum())
    assert 1.82 <= total_vol <= 1.95, (
        f"union volume {total_vol:.4f} outside [1.82, 1.95] band "
        f"(analytic union=1.875; symmetric difference=1.750)"
    )
    single_cube_vol_est = 1.0
    assert total_vol > single_cube_vol_est + 0.5, (
        f"union volume {total_vol:.4f} too close to a single cube's volume "
        f"({single_cube_vol_est}) — the merge does not appear to have "
        f"happened (only one body meshed)."
    )

    # --- surface preservation invariant 1 -----------------------------
    # Sample the original *input vertices* of A and B that lie strictly
    # outside the OTHER cube (so they are on the union's true boundary, not
    # absorbed into the merged interior) and check they survive in the
    # output mesh. Only A's (1,1,1) and B's (0.5,0.5,0.5) sit strictly
    # inside the other body's extent, so those two are excluded — the
    # remaining 7+7 corners are un-ambiguous union-boundary points.
    bbox_diag = float(np.linalg.norm([1.5, 1.5, 1.5]))  # union bbox [0,1.5]^3
    eps = bbox_diag * 0.02

    a_samples = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [0, 1, 1],
        ],
        dtype=np.float64,
    )
    b_samples = np.array(
        [
            [1.5, 0.5, 0.5],
            [0.5, 1.5, 0.5],
            [0.5, 0.5, 1.5],
            [1.5, 1.5, 0.5],
            [1.5, 0.5, 1.5],
            [0.5, 1.5, 1.5],
            [1.5, 1.5, 1.5],
        ],
        dtype=np.float64,
    )

    d_a = _nearest_dist_to_boundary(case_dir, a_samples)
    d_b = _nearest_dist_to_boundary(case_dir, b_samples)
    assert np.all(
        d_a <= eps
    ), f"cube A surface samples strayed from output boundary: {d_a} > eps={eps:.4f}"
    assert np.all(
        d_b <= eps
    ), f"cube B surface samples strayed from output boundary: {d_b} > eps={eps:.4f}"
