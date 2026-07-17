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
    """|volume| of every cell, computed WITHOUT relying on face orientation.

    Each cell's four vertices are pulled straight from its faces and the volume
    taken as |det|/6.  This matters: a face-based (divergence-theorem) volume
    inherits any error in the polyMesh's face orientation, and this mesh has
    some — measured 18 of 446 boundary faces pointing inward.  Doing it that way
    read 1.735x and looked like massive cell overlap; the orientation-free
    measure reads 1.003x, i.e. no overlap at all.  Measure the geometry, not the
    bookkeeping.
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
            continue  # not a tet — leaves 0.0, caught by the degenerate gate
        p = pts[np.asarray(sorted(s), dtype=int)]
        vols[ci] = abs(
            float(np.dot(p[1] - p[0], np.cross(p[2] - p[0], p[3] - p[0])))
        ) / 6.0
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


def test_native_tet_mesh_encloses_true_volume(tmp_path: Path, monkeypatch) -> None:
    """Cell volumes must sum to the input's volume — i.e. the cells tile it.

    Sum |tet volume| over every cell.  For a valid tetrahedralization of the
    input this equals the input's volume exactly: less means gaps, more means
    the tets overlap.  Measured 1.003x, so they tile the cube cleanly.
    """
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    poly = _run_native_tet(tmp_path / "case")

    vols = _cell_volumes(poly)
    total = float(vols.sum())
    ratio = total / _TRUE_VOLUME
    assert 0.95 <= ratio <= 1.05, (
        f"cell volumes sum to {total:.3f} = {ratio:.2f}x the input's true "
        f"volume {_TRUE_VOLUME:.3f} — the cells do not tile the input "
        f"(<1 = gaps, >1 = overlap)."
    )


@pytest.mark.xfail(
    reason=(
        "50 of 2398 cells are degenerate (volume exactly 0) on cube.stl. They "
        "are the source of max_skewness 1.7e29. They were previously deleted "
        "by drop_extreme_slivers, which hid them at the cost of punching voids "
        "(BETA2824); they must instead be removed by topology-preserving local "
        "operations — collapse / swap / smooth — per fTetWild section 3.4."
    ),
    strict=True,
)
def test_native_tet_has_no_degenerate_cells(tmp_path: Path, monkeypatch) -> None:
    """No cell may have (near) zero volume.

    A zero-volume tet is four coplanar points: it has no interior, its skewness
    is unbounded, and a solver cannot integrate over it.  This is the last
    remaining defect once the boundary is exact and the cells tile the volume.
    """
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    poly = _run_native_tet(tmp_path / "case")

    vols = _cell_volumes(poly)
    # 1e-9 against a mean cell volume of ~4e-4 — six orders down, unambiguous.
    n_degenerate = int((vols < 1e-9).sum())
    assert n_degenerate == 0, (
        f"{n_degenerate}/{vols.size} cells have (near) zero volume — these are "
        f"flat tets and drive max_skewness to ~1e29."
    )
