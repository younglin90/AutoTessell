"""native_tet must produce a SOLID tetrahedralization — no interior voids.

A watertight tet mesh of a closed input surface has exactly one boundary: the
input surface itself.  Its total boundary area must therefore equal the input
STL's surface area.  Any excess means the volume has holes punched through it,
and every hole's wall is counted as "boundary" with an arbitrary normal.

STATUS (re-measured 2026-07-17 after BETA2822, cube.stl / draft / N=2000,
P4-C disabled so the self-implemented engine is isolated).  This test was
xfail(strict) until the sliver filter's removal predicate was corrected;
it is now a permanent regression guard::

    config                          boundary area    max skew   cells
    legacy (void_free=False)        20.269 (3.38x)      10.5     2034  <- voids
    void_free=True   (default)       6.128 (1.02x)     107.9     2377  <- solid

Root cause (fixed) — ``core/generator/native_tet/filter.py``::

    keep = inside_mask & (q >= thr)      # was: deletes interior slivers
    keep = inside_mask                   # now: void_free, reference predicate

Deleting a tet from a tetrahedralization leaves a void; nothing fills it.
The vendored reference has no such deletion: fTetWild's ``filter_outside``
(``third_party/fTetWild/src/MeshImprovement.cpp:1638``) removes on winding
number alone (``W <= 0.5``) and contains no quality term at all, so a sliver
with ``W > 0.5`` is always kept.  ``protect_boundary_faces`` never compensated
(it only checks *surface vertex* coverage, and fired 0 times); the revert guard
at ``mesher.py:1182`` measures ``area_coverage`` (surface plane coverage),
which interior deletion does not reduce, so it never fired either.

The 2 % residual (6.128 vs 6.000) is NOT a void: the bbox is exactly
[-0.5, 0.5]^3 and the excess is boundary triangles sitting a few degrees off
the cube planes (469 of 482 are not axis-aligned) — a surface-wrinkle defect
tracked separately, not Swiss cheese.

Slivers are now *retained*, not deleted, and the debt is reported by
``FilterResult.n_slivers_retained`` (362 on this case — the same tets the old
predicate silently dropped).  That debt is why skew rose 10.5 -> 107.9: the old
10.5 was obtained by deleting the evidence, not by meshing well.  fTetWild
removes slivers by local operations (collapse / swap / smooth) that preserve
the tetrahedralization; driving that debt to 0 is the follow-up work.

Do NOT "fix" this test by widening the tolerance.  The 1.0x identity is exact
geometry, not a tuning knob.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.pipeline.orchestrator import PipelineOrchestrator
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

_CUBE = Path(__file__).resolve().parent / "benchmarks" / "cube.stl"


def _stl_surface_area(path: Path) -> float:
    m = read_stl(path)
    v = np.asarray(m.vertices, dtype=float)
    tri = v[np.asarray(m.faces, dtype=int)]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    return float(np.linalg.norm(n, axis=1).sum() / 2.0)


def _boundary_area(poly_dir: Path) -> float:
    """Total area of the polyMesh's boundary faces (fan-triangulated)."""
    pts = np.asarray(parse_foam_points(poly_dir / "points"), dtype=float)
    faces = [list(f) for f in parse_foam_faces(poly_dir / "faces")]
    n_internal = len(parse_foam_labels(poly_dir / "neighbour"))
    total = 0.0
    for face in faces[n_internal:]:
        p = pts[np.asarray(face, dtype=int)]
        acc = np.zeros(3)
        for i in range(1, len(face) - 1):
            acc = acc + np.cross(p[i] - p[0], p[i + 1] - p[0]) / 2.0
        total += float(np.linalg.norm(acc))
    return total


def _cell_volumes(poly_dir: Path) -> np.ndarray:
    """Signed volume of every cell, via the divergence theorem over its faces."""
    pts = np.asarray(parse_foam_points(poly_dir / "points"), dtype=float)
    faces = [list(f) for f in parse_foam_faces(poly_dir / "faces")]
    owner = np.asarray(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
    nb = np.asarray(parse_foam_labels(poly_dir / "neighbour"), dtype=np.int64)
    n_internal = len(nb)
    n_cells = int(max(owner.max(), nb.max() if nb.size else 0)) + 1

    vols = np.zeros(n_cells, dtype=float)
    for fi, face in enumerate(faces):
        p = pts[np.asarray(face, dtype=int)]
        a = np.zeros(3)
        for i in range(1, len(face) - 1):
            a = a + np.cross(p[i] - p[0], p[i + 1] - p[0]) / 2.0
        contrib = float(np.dot(p.mean(axis=0), a)) / 3.0
        o = int(owner[fi])
        if 0 <= o < n_cells:
            vols[o] += contrib
        if fi < n_internal:
            n_ = int(nb[fi])
            if 0 <= n_ < n_cells:
                vols[n_] -= contrib
    return vols


def _run_native_tet(case: Path) -> Path:
    PipelineOrchestrator().run(
        _CUBE, case,
        quality_level="draft", mesh_type="tet", tier_hint="native_tet",
        max_iterations=1, auto_retry="off", write_of_case=True,
        max_cells=2000,
        tier_specific_params={"max_cells": 2000, "target_cells": 2000},
    )
    poly = case / "constant" / "polyMesh"
    assert (poly / "points").exists(), "polyMesh was not written"
    return poly


def test_native_tet_mesh_is_solid(tmp_path: Path, monkeypatch) -> None:
    """Boundary area must equal the input surface area (no interior voids).

    NOTE: this is *necessary but not sufficient* — see
    ``test_native_tet_mesh_encloses_true_volume`` below.  An inward crater
    preserves area while eating volume, so this gate alone cannot certify
    solidity.  It does guard the specific defect fixed in BETA2822 (interior
    tet deletion, which drove the ratio to 3.4x), which is why it is kept.
    """
    # Isolate the self-implemented engine: no external pytetwild rescue.
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")

    poly = _run_native_tet(tmp_path / "case")

    expected = _stl_surface_area(_CUBE)
    actual = _boundary_area(poly)
    ratio = actual / expected

    # 5 % slack absorbs fan-triangulation round-off, nothing more.
    assert ratio <= 1.05, (
        f"boundary area {actual:.3f} is {ratio:.2f}x the input surface area "
        f"{expected:.3f} — the volume has interior voids (Swiss cheese). "
        f"Slivers must be removed by local operations, not deleted."
    )


@pytest.mark.xfail(
    reason=(
        "The boundary encloses the wrong volume even though its AREA is right: "
        "measured on cube.stl (true volume 1.000) the cells sum to 1.451x while "
        "the boundary encloses 0.770x. Root cause located at mesher.py:1809 — "
        "`n_surface_in = int(V.shape[0])` locks only the INPUT STL's vertices "
        "(8 for a cube), leaving the ~155 surface vertices BSP created unlocked, "
        "so the Laplacian in smooth_then_drop_slivers pulls the boundary inward. "
        "Tracked as harness CARD BETA2823."
    ),
    strict=True,
)
def test_native_tet_mesh_encloses_true_volume(tmp_path: Path, monkeypatch) -> None:
    """Cell volumes must sum to the input's true volume, and none may invert.

    Why this exists: ``test_native_tet_mesh_is_solid`` gates on boundary AREA
    and passes (0.99x) while the mesh is still wrong.  A crater pushed inward
    keeps the area but removes volume, so area is blind to it.  Two independent
    measures must agree with the truth for the mesh to be a valid
    tetrahedralization of the input::

        cube.stl true         volume 1.000
        sum |cell volume|            1.451   <- cells overlap / are tangled
        boundary-enclosed volume     0.770   <- boundary crumpled inward

    In a valid mesh both equal 1.000 and each other.  Do NOT widen these
    tolerances — the unit cube's volume is exact geometry, not a tuning knob.
    """
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")

    poly = _run_native_tet(tmp_path / "case")

    vols = _cell_volumes(poly)
    total = float(np.abs(vols).sum())
    true_volume = 1.0  # cube.stl is the unit cube (bbox exactly [-0.5, 0.5]^3)

    n_inverted = int((vols < 0).sum())
    assert n_inverted == 0, f"{n_inverted}/{vols.size} cells have negative volume"

    ratio = total / true_volume
    assert 0.95 <= ratio <= 1.05, (
        f"cell volumes sum to {total:.3f} = {ratio:.2f}x the input's true "
        f"volume {true_volume:.3f}. Area can look right while the boundary is "
        f"crumpled inward or cells overlap — this is the sufficient check."
    )
