"""native_tet must produce a SOLID tetrahedralization — no interior voids.

A watertight tet mesh of a closed input surface has exactly one boundary: the
input surface itself.  Its total boundary area must therefore equal the input
STL's surface area.  Any excess means the volume has holes punched through it,
and every hole's wall is counted as "boundary" with an arbitrary normal.

STATUS (measured 2026-07-17, cube.stl / draft / N=2000, P4-C disabled so the
self-implemented engine is isolated)::

    true surface area (1x1x1 cube)   6.000
    self-impl boundary area         20.409   <-- 3.40x  == Swiss cheese
    distinct boundary normals           18   (a cube has 6)

Root cause — ``core/generator/native_tet/filter.py:104``::

    keep = inside_mask & (q >= thr)

The sliver filter *deletes* low-quality tets.  Deleting a tet from a
tetrahedralization leaves a void; nothing fills it.  ``protect_boundary_faces``
(filter.py:107) only guarantees each *surface vertex* stays covered — it never
checks volumetric integrity.  The revert guard at ``mesher.py:1221`` measures
``area_coverage`` (surface plane coverage), which interior deletion does not
reduce, so the guard never fires.  ``cavity_retri.py`` (cavity re-meshing)
exists but is referenced 0 times from mesher.py.

Why this is xfail rather than fixed: neither obvious lever works alone —

    config                     boundary area      skew
    HEAD (delete slivers)      20.409 (3.40x)     10.5   <- voids
    no interior delete          5.939 (0.99x)     63.3   <- solid, slivers stay
    no delete + passes on       5.870 (0.98x)   1.3e15   <- solid, degenerate

fTetWild's answer is that slivers are neither deleted nor tolerated: they are
removed by local operations (collapse / swap / smooth) that preserve the
tetrahedralization.  Those operators exist here (local_ops.py, flip.py,
amips.py, klingner_full_sweep.py) but currently degrade the mesh, so making
this test pass is an algorithmic project, not a patch.

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


@pytest.mark.xfail(
    reason=(
        "native_tet's sliver filter deletes interior tets and leaves voids: "
        "boundary area is 3.40x the true surface (20.409 vs 6.000) on "
        "cube.stl. See this module's docstring for the measured evidence and "
        "why no single lever fixes it."
    ),
    strict=True,
)
def test_native_tet_mesh_is_solid(tmp_path: Path, monkeypatch) -> None:
    """Boundary area must equal the input surface area (no interior voids)."""
    # Isolate the self-implemented engine: no external pytetwild rescue.
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")

    case = tmp_path / "case"
    PipelineOrchestrator().run(
        _CUBE, case,
        quality_level="draft", mesh_type="tet", tier_hint="native_tet",
        max_iterations=1, auto_retry="off", write_of_case=True,
        max_cells=2000,
        tier_specific_params={"max_cells": 2000, "target_cells": 2000},
    )

    poly = case / "constant" / "polyMesh"
    assert (poly / "points").exists(), "polyMesh was not written"

    expected = _stl_surface_area(_CUBE)
    actual = _boundary_area(poly)
    ratio = actual / expected

    # 5 % slack absorbs fan-triangulation round-off, nothing more.
    assert ratio <= 1.05, (
        f"boundary area {actual:.3f} is {ratio:.2f}x the input surface area "
        f"{expected:.3f} — the volume has interior voids (Swiss cheese). "
        f"Slivers must be removed by local operations, not deleted."
    )
