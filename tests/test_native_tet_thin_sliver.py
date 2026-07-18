"""CARD THINSLIVER1 -- interior degenerate slivers on naca0012 are curable.

Measured (harness/plan_thinsliver1.md): naca0012's 17 degenerate tets
(|det|/6 < 1e-9) are 17/17 fully-interior (0 boundary faces) and 14/17 have
an interior endpoint on their shortest edge -- safely collapsible without
touching the surface. ``native_tet_degenerate_removal``'s Phase1 (3-2 flip)
only fires for degenerate edges with exactly 3 owners + a separating
triangle; these 17 have owners != 3 or a same-side apex (su == sv), so
Phase1 cannot remove them and Phase2 (coplanar-flap) does not apply either
(they are not coplanar with an input surface plane). Phase1b (interior-
incident edge-collapse) closes this gap.

MEASURED (2026-07-18, target_cells=2000 fixture config): Phase1b brought
degen 22 (pre-removal, this fixture's config) -> 11 (post). The remaining 11
victims have vertex-star valence 12-26 -- the orientation guard correctly
refuses to collapse them because the whole star can't be verified safe in
one step (that's the guard working, not a bug). Reaching 0 needs a
higher-valence-safe collapse strategy or a different victim-selection rule,
scoped to a follow-up card. This test locks the correctness win (degen
count) without requiring the verdict to flip to PASS -- skew is a separate
axis (THINSLIVER2).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.file_reader import load_mesh
from core.generator.native_tet.mesher import generate_native_tet
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

_NACA = Path(__file__).resolve().parent / "benchmarks" / "naca0012.stl"


@pytest.fixture(scope="module")
def naca_mesh(tmp_path_factory):
    """Single shared native_tet run for this file.

    Repeated in-process ``generate_native_tet`` calls have been observed to
    trigger non-deterministic native-heap access violations under pytest
    (see ``tests/test_native_tet_dual_torus_limit.py`` and
    ``.claude/rules/lessons-learned.md``) -- share one run across all gates.
    """
    prev = os.environ.get("AUTO_TESSELL_P4C_PYTETWILD")
    os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
    try:
        case_dir = tmp_path_factory.mktemp("case")
        mesh = load_mesh(_NACA)
        vertices = np.asarray(mesh.vertices, dtype=float)
        faces = np.asarray(mesh.faces, dtype=np.int64)
        result = generate_native_tet(
            vertices, faces, case_dir, target_cells=2000,
        )
        poly = case_dir / "constant" / "polyMesh"
        assert (poly / "points").exists(), "polyMesh was not written"
        return result, case_dir, vertices, faces
    finally:
        if prev is None:
            os.environ.pop("AUTO_TESSELL_P4C_PYTETWILD", None)
        else:
            os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = prev


def _cell_volumes_signed(poly_dir: Path) -> np.ndarray:
    """Signed vol6 (|det|/6 sign preserved) per cell, from raw tet verts."""
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
        vols[ci] = float(
            np.dot(p[1] - p[0], np.cross(p[2] - p[0], p[3] - p[0]))
        ) / 6.0
    return vols


def test_naca_degenerate_slivers_bounded(naca_mesh) -> None:
    """Regression lock for Phase1b's real win: degen must stay <= 15.

    Measured 22 (pre-Phase1b) -> 11 (post), fixture's target_cells=2000
    config. This gate has margin above 11 so it isn't a flaky pin on an
    exact count, but it locks in that Phase1b's collapse actually fires and
    doesn't silently regress back toward 22 (or worse) -- see the
    xfail(strict) test below for the still-open <=2 target.
    """
    _result, case_dir, _vertices, _faces = naca_mesh
    poly = case_dir / "constant" / "polyMesh"
    vols = _cell_volumes_signed(poly)
    n_degen = int((np.abs(vols) < 1e-9).sum())
    assert n_degen <= 15, (
        f"naca0012 has {n_degen} degenerate tets -- Phase1b's collapse win "
        "regressed (was 11, margin to 15)."
    )


@pytest.mark.xfail(strict=True, reason=(
    "Phase1b (interior-incident edge-collapse) safely removes the "
    "low-valence victims (22 -> 11 in this fixture's target_cells=2000 "
    "config) but the remaining 11 have vertex-star valence 12-26, which the "
    "per-tet orientation guard correctly refuses to collapse in one step. "
    "Reaching <=2 needs a higher-valence-safe collapse strategy, scoped to "
    "a follow-up card -- not a guard relaxation."
))
def test_naca_degenerate_slivers_removed(naca_mesh) -> None:
    """naca0012 degen (|det|/6 < 1e-9) count: measured 22 (pre) -> gate <=2."""
    _result, case_dir, _vertices, _faces = naca_mesh
    poly = case_dir / "constant" / "polyMesh"
    vols = _cell_volumes_signed(poly)
    n_degen = int((np.abs(vols) < 1e-9).sum())
    assert n_degen <= 2, (
        f"naca0012 has {n_degen} degenerate tets (|det|/6 < 1e-9) after "
        "native_tet_degenerate_removal Phase1b -- expected <= 2 (target 0)."
    )
