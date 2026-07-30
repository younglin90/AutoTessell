"""Regression guard: cylinder curved-wall fidelity (native_tet, BL=0, draft).

Reproduces the "찌글거림" bug where the curved side wall of a closed solid
cylinder (``tests/benchmarks/cylinder.stl`` — axis Z, true radius 0.5,
z in [-0.5, 0.5]) came out badly distorted.  Two coupled defects caused it:

1. ``core/generator/native_tet/mesher.py`` — P4-C (pytetwild) regenerated a
   grade-A, wall-faithful mesh and reassigned ``final_pts``/``final_tets``,
   but on the non-``_phase_bc_skip`` path the re-write that persists it was
   gated only on ``_phase_bc_skip``.  So the stale low-quality pre-P4-C mesh
   (written at line ~1887) stayed on disk and became the output — its
   side-wall boundary vertices deviated up to ~0.33 from the true radius 0.5.

2. ``core/pipeline/orchestrator.py`` — the destructive
   ``drop_neg_vol_cells`` post-process ran even on a pure tet mesh with **no**
   boundary layer, dropping ~25 % of cells on the curved wall and exposing
   interior vertices as boundary craters.

With both fixed, the side-wall boundary vertices sit on the true cylinder
radius (0.5) to within a few thousandths.  Before the fix the max absolute
radius deviation was ~0.327; this test asserts it stays below 0.05.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

# The wall-faithful mesh is produced by the P4-C pytetwild fallback; without
# pytetwild the native path only reaches grade C and the wall stays distorted,
# so the fix under test cannot apply.
pytest.importorskip("pytetwild")

from core.analyzer.file_reader import load_mesh  # noqa: E402
from core.generator.native_tet.source_facet_provenance import (  # noqa: E402
    audit_source_facet_provenance_python,
)
from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402
from core.utils.polymesh_reader import (  # noqa: E402
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

# Fixed geometry of tests/benchmarks/cylinder.stl (verified): axis = Z through
# the origin, true radius 0.5, height 1.0 (z in [-0.5, 0.5]).
_CYLINDER = Path(__file__).resolve().parent / "benchmarks" / "cylinder.stl"
_AXIS_XY = (0.0, 0.0)
_TRUE_RADIUS = 0.5
_Z_SIDE_LIMIT = 0.49  # |z| < this ⇒ curved side wall, not the end caps


def _side_wall_radius_deviation(poly_dir: Path) -> tuple[float, float, int]:
    """Measure vertices owned by side-wall boundary-face topology.

    A conforming cylinder may use only the two source rings, so selecting
    vertices with ``abs(z) < 0.49`` falsely reports zero side vertices.  Side
    faces have interior-z centroids even when every one of their vertices lies
    on an end ring; select those faces first, then measure their vertices.
    """
    pts = np.asarray(parse_foam_points(poly_dir / "points"), dtype=float)
    faces = [list(f) for f in parse_foam_faces(poly_dir / "faces")]
    neighbour = parse_foam_labels(poly_dir / "neighbour")
    n_internal = len(neighbour)

    boundary_verts: set[int] = set()
    for face in faces[n_internal:]:
        face_points = pts[np.asarray(face, dtype=np.int64)]
        if abs(float(face_points[:, 2].mean())) < _Z_SIDE_LIMIT:
            boundary_verts.update(face)
    idx = np.fromiter(sorted(boundary_verts), dtype=np.int64)
    bp = pts[idx]

    r = np.hypot(bp[:, 0] - _AXIS_XY[0], bp[:, 1] - _AXIS_XY[1])
    dev = np.abs(r - _TRUE_RADIUS)
    if dev.size == 0:
        return 0.0, 0.0, 0
    return float(dev.max()), float(dev.mean()), int(dev.size)


def _disk_source_facet_report(poly_dir: Path) -> dict[str, int | bool]:
    source = load_mesh(_CYLINDER)
    points = np.asarray(parse_foam_points(poly_dir / "points"), dtype=np.float64)
    faces = np.asarray(parse_foam_faces(poly_dir / "faces"), dtype=np.int64)
    n_internal = len(parse_foam_labels(poly_dir / "neighbour"))
    return audit_source_facet_provenance_python(
        np.asarray(source.vertices, dtype=np.float64),
        np.asarray(source.faces, dtype=np.int64),
        points,
        faces[n_internal:],
    )


def test_cylinder_side_wall_fidelity(tmp_path, monkeypatch):
    # Reproduce the GUI conditions: the destructive drop pass is ENABLED
    # (as desktop/default_env.py forces it) — the orchestrator BL gate must
    # keep it from running on this BL=0 mesh — and P4-C is enabled.
    monkeypatch.setenv("AUTO_TESSELL_BL_DROP_NEG_VOL", "1")
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "1")

    case = tmp_path / "case"
    result = PipelineOrchestrator().run(
        _CYLINDER,
        case,
        quality_level="draft",
        mesh_type="tet",
        tier_hint="native_tet",
        max_iterations=1,
        auto_retry="off",
        write_of_case=True,
        max_cells=2000,
        tier_specific_params={"max_cells": 2000, "target_cells": 2000},
    )

    poly = case / "constant" / "polyMesh"
    assert (poly / "points").exists(), "polyMesh was not written"

    max_dev, mean_dev, n_side = _side_wall_radius_deviation(poly)

    # Sanity: we must actually be measuring the curved wall.
    assert n_side >= 20, (
        f"too few side-wall boundary vertices ({n_side}) to judge fidelity"
    )

    # The regression guard.  Before the fix: max_dev ~0.327, mean_dev ~0.069.
    assert max_dev < 0.05, (
        f"cylinder side-wall radius max deviation {max_dev:.4f} exceeds 0.05 "
        f"(mean {mean_dev:.4f}, n_side={n_side}) — curved-wall 찌글거림 regressed"
    )

    source_report = _disk_source_facet_report(poly)
    assert source_report["source_faces_preserved"] is True
    assert source_report["n_unowned_candidate_faces"] == 0

    # The mesh must also remain solver-valid: the pre-fix behaviour of gating
    # the drop pass off *without* persisting the faithful P4-C mesh left a
    # skew-397 mesh that failed evaluation.
    verdict = str(result.quality_report.evaluation_summary.verdict.value)
    assert "PASS" in verdict, f"unexpected evaluator verdict: {verdict}"
