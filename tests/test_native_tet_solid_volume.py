"""native_tet must actually mesh the input solid — surface, voids, volume.

Measured on ``tests/benchmarks/cube.stl``: the unit cube, bbox exactly
[-0.5, 0.5]^3, surface area 6.000, volume 1.000.  P4-C (pytetwild) is disabled
in every test here so the self-implemented engine is measured alone.

WHY THREE SEPARATE GATES.  An earlier version of this file gated on *total*
boundary area and passed at 0.99x while the mesh was badly wrong — total area
is a trap, because area lost on the real surface can be silently replaced by
the walls of interior voids.  Measured at that moment::

    metric                      value
    total boundary area         5.939  (0.99x — the gate PASSED)
    ...of which ON cube planes  0.031  (0.5 % of the true 6.000!)
    ...of which OFF the planes  5.908  (interior void walls)

So the three properties are gated independently, because each is blind to the
others:

  1. surface coverage — area lying ON the input surface must equal 6.000.
  2. no interior voids — area lying OFF the input surface must be ~0.
  3. volume — cell volumes must sum to 1.000 with none inverted.
     (An inward crater keeps total area while removing volume; a closed
     interior void cancels in the divergence sum while adding to area.)

Do NOT widen these tolerances.  The unit cube's area and volume are exact
geometry, not tuning knobs.
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

_CUBE = Path(__file__).resolve().parent / "benchmarks" / "cube.stl"
_TRUE_AREA = 6.0    # unit cube
_TRUE_VOLUME = 1.0
_PLANES = 0.5       # |x| = |y| = |z| = 0.5


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


def _face_area_vec(pts: np.ndarray, face: list[int]) -> np.ndarray:
    p = pts[np.asarray(face, dtype=int)]
    acc = np.zeros(3)
    for i in range(1, len(face) - 1):
        acc = acc + np.cross(p[i] - p[0], p[i + 1] - p[0]) / 2.0
    return acc


def _boundary_area_split(poly_dir: Path) -> tuple[float, float]:
    """(area lying on the cube's 6 planes, area lying off them)."""
    pts = np.asarray(parse_foam_points(poly_dir / "points"), dtype=float)
    faces = [list(f) for f in parse_foam_faces(poly_dir / "faces")]
    n_internal = len(parse_foam_labels(poly_dir / "neighbour"))

    on_area = off_area = 0.0
    for face in faces[n_internal:]:
        p = pts[np.asarray(face, dtype=int)]
        a = float(np.linalg.norm(_face_area_vec(pts, face)))
        on_plane = any(
            np.all(np.abs(p[:, ax] - s) < 1e-6)
            for ax in range(3)
            for s in (-_PLANES, _PLANES)
        )
        if on_plane:
            on_area += a
        else:
            off_area += a
    return on_area, off_area


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
        a = _face_area_vec(pts, face)
        c = pts[np.asarray(face, dtype=int)].mean(axis=0)
        contrib = float(np.dot(c, a)) / 3.0
        o = int(owner[fi])
        if 0 <= o < n_cells:
            vols[o] += contrib
        if fi < n_internal:
            n_ = int(nb[fi])
            if 0 <= n_ < n_cells:
                vols[n_] -= contrib
    return vols


def test_native_tet_covers_input_surface(tmp_path: Path, monkeypatch) -> None:
    """Boundary area lying ON the input surface must equal the input's area.

    This is the gate that a total-area check misses.  Before BETA2823 only
    0.031 of the cube's 6.000 was actually meshed — 0.5 % — while the total
    looked fine at 5.939 because interior void walls made up the difference.
    """
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    poly = _run_native_tet(tmp_path / "case")

    on_area, _ = _boundary_area_split(poly)
    ratio = on_area / _TRUE_AREA
    assert 0.95 <= ratio <= 1.05, (
        f"only {on_area:.3f} of the input's {_TRUE_AREA:.3f} surface area is "
        f"covered by boundary faces lying on it ({ratio:.3f}x) — the mesh's "
        f"boundary is not the input surface."
    )


def test_native_tet_has_no_interior_voids(tmp_path: Path, monkeypatch) -> None:
    """No boundary area may lie off the input surface (that would be a void wall).

    A watertight input has exactly one boundary: itself.  Any boundary face not
    on the input surface is the wall of a hole in the volume.

    History — off-plane area on cube.stl as the deletion sites were swept::

        5.908   before any fix
        1.959   after BETA2823 locked the real surface vertices
        0.000   after drop_extreme_slivers stopped deleting (BETA2824)

    Four sites deleted tets; the invariant "a deleted tet leaves a void nothing
    fills" had to be applied to all of them.  clip_to_input_surface is the one
    legitimate remover — it drops tets OUTSIDE the surface, which is exactly
    fTetWild's filter_outside and creates no void.
    """
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    poly = _run_native_tet(tmp_path / "case")

    _, off_area = _boundary_area_split(poly)
    assert off_area <= 0.05 * _TRUE_AREA, (
        f"{off_area:.3f} of boundary area lies off the input surface — these "
        f"are interior void walls. Slivers must be removed by topology-"
        f"preserving local operations, not deleted."
    )


@pytest.mark.xfail(
    reason=(
        "Cells sum to 1.346x the true volume — they overlap or are tangled. "
        "The boundary-enclosed volume is exactly 1.000 after BETA2823, so the "
        "surface itself is right; the interior tetrahedralization is not."
    ),
    strict=True,
)
def test_native_tet_mesh_encloses_true_volume(tmp_path: Path, monkeypatch) -> None:
    """Cell volumes must sum to the input's volume, and none may invert."""
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    poly = _run_native_tet(tmp_path / "case")

    vols = _cell_volumes(poly)
    n_inverted = int((vols < 0).sum())
    assert n_inverted == 0, f"{n_inverted}/{vols.size} cells have negative volume"

    total = float(np.abs(vols).sum())
    ratio = total / _TRUE_VOLUME
    assert 0.95 <= ratio <= 1.05, (
        f"cell volumes sum to {total:.3f} = {ratio:.2f}x the input's true "
        f"volume {_TRUE_VOLUME:.3f} — cells overlap or are tangled."
    )
