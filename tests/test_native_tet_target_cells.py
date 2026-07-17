"""Regression guard: native_tet must respect the user's target cell count N.

The bug (measured on ``tests/benchmarks/cube.stl``, mesh_type=tet,
tier_hint=native_tet, quality=draft, N via
``tier_specific_params={"max_cells": N, "target_cells": N}``)::

    target N | before |  ratio  | after | ratio
    ---------+--------+---------+-------+-------
          50 |     50 |   1.00x |    50 | 1.00x
         100 |   9521 |  95.21x |    50 | 0.50x
         500 |    216 |   0.43x |   422 | 0.84x
        1000 |   1318 |   1.32x |  1318 | 1.32x
        2000 |   1318 |   0.66x |  2035 | 1.02x
        5000 |   4304 |   0.86x |  4304 | 0.86x
       10000 |   5921 |   0.59x | 10311 | 1.03x
       20000 |  20052 |   1.00x | 20052 | 1.00x

Two coupled defects:

1. ``mesher.py`` — the P4-C pytetwild fallback (fires when the self-implemented
   mesher misses grade A) used a FIXED ``edge_length_fac=0.05``, ignoring N
   entirely.  N=100 → self-impl made 35 cells (grade D) → P4-C replaced it with
   ~9.5k cells regardless of N.  Now the fac is derived from the N-driven edge
   (``edge / bbox_diag``).
2. ``harness.py`` — the cap-retry meant to catch (1) was dead code for draft
   (``it < max_iter`` with ``max_iter=1`` is never true), and was a blunt
   one-shot ``edge x 1.6`` rather than a measured correction.  Replaced by
   ``_generate_with_cell_rebudget``: a measured-ratio closed loop with its own
   pass budget, so it runs even at draft's ``max_iter=1``.

TOLERANCE BAND — why it is not a uniform +/-15 %:

``n(edge)`` for native_tet is neither continuous nor monotone.  Measured raw
curve on cube.stl (self-impl only, P4-C off)::

    edge  0.87  0.70  0.50 | 0.45  0.40  0.35 | 0.30  0.26  0.22
    cells   50    50    50 |   35    35    35 |  171   216   422

so the attainable cell counts near the coarse end are the sparse set
{35, 50, 171, 216, 422, ...} — for N=100 there simply is no edge that yields
~100 cells.  With P4-C ON, edges 0.35-0.45 additionally jump to 1620-3013
cells, which INVERTS the local gradient and traps the loop.  The closed loop
therefore converges wherever N is representable and otherwise returns the
closest attainable mesh (best-of by log-ratio distance).

Measured bands, cube.stl / draft:
  - N >= 500  : ratio in [0.84, 1.32]  → asserted as [0.75, 1.45]
  - N <= 200  : NOT holdable (N=100 → 0.50x, N=200 → 0.25x) — the sparse
                attainable set plus the P4-C hijack zone.  Asserted one-sided
                (no explosion) only; see ``test_small_target_does_not_explode``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.analyzer.readers import read_stl
from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    MeshStrategy,
    MeshType,
    QualityLevel,
    SurfaceMeshConfig,
)

_CUBE = Path(__file__).resolve().parent / "benchmarks" / "cube.stl"

# Measured post-fix ratios for N >= 500 span [0.84, 1.32]; assert with margin.
_BAND_LO = 0.75
_BAND_HI = 1.45


def _strategy_for(target_cells: int) -> MeshStrategy:
    """Reproduce the CLI/GUI request: N through ``tier_specific_params``."""
    m = read_stl(_CUBE)
    lo = m.vertices.min(axis=0)
    hi = m.vertices.max(axis=0)
    mid = (lo + hi) / 2.0
    return MeshStrategy(
        quality_level=QualityLevel.DRAFT,
        mesh_type=MeshType.TET,
        selected_tier="tier_native_tet",
        flow_type="internal",
        domain=DomainConfig(
            min=[float(x) for x in lo],
            max=[float(x) for x in hi],
            base_cell_size=0.1,
            location_in_mesh=[float(x) for x in mid],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file=str(_CUBE), target_cell_size=0.1, min_cell_size=0.01
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=False,
            num_layers=0,
            first_layer_thickness=0.001,
            growth_ratio=1.2,
            max_total_thickness=0.1,
            min_thickness_ratio=0.1,
        ),
        tier_specific_params={"max_cells": target_cells, "target_cells": target_cells},
    )


def _run_native_tet(target_cells: int, case_dir: Path) -> int:
    """Run the native_tet tier for a target N; return the actual cell count."""
    from core.generator.tier_native_tet import TierNativeTetGenerator

    attempt = TierNativeTetGenerator().run(
        _strategy_for(target_cells), _CUBE, case_dir
    )
    assert attempt.status == "success", f"tier failed: {attempt.error_message}"
    assert attempt.mesh_stats is not None
    return int(attempt.mesh_stats.num_cells)


@pytest.mark.parametrize("target_cells", [500, 2000, 10000])
def test_target_cell_count_is_respected(tmp_path: Path, target_cells: int) -> None:
    """Actual cell count lands within [0.75x, 1.45x] of the requested N.

    Pre-fix this failed for every value here: 500 → 216 (0.43x),
    2000 → 1318 (0.66x), 10000 → 5921 (0.59x) — the open-loop edge estimate
    undershot by 40-70 % and nothing measured or corrected it.
    """
    n = _run_native_tet(target_cells, tmp_path / f"case_{target_cells}")
    ratio = n / target_cells
    assert _BAND_LO <= ratio <= _BAND_HI, (
        f"target_cells={target_cells} produced {n} cells (ratio {ratio:.2f}x), "
        f"outside the [{_BAND_LO}, {_BAND_HI}] band"
    )


def test_small_target_does_not_explode(tmp_path: Path) -> None:
    """N=100 must not blow up to ~9.5k cells (the P4-C 95x overshoot).

    This is a ONE-SIDED guard on purpose.  N=100 is not attainable within
    +/-15 % on cube.stl: the attainable set near the coarse end is
    {35, 50, 171, 216, ...}, so the loop returns 50 cells (0.50x) — the closest
    it can reach through the P4-C hijack zone.  What must never regress is the
    explosion: pre-fix the P4-C fallback ignored N and returned 9521 cells.
    """
    n = _run_native_tet(100, tmp_path / "case_100")
    assert n <= 250, (
        f"target_cells=100 produced {n} cells — the P4-C fallback is ignoring "
        f"the target cell count again (pre-fix: 9521)"
    )


def test_exact_small_target_is_hit(tmp_path: Path) -> None:
    """N=50 is exactly attainable on cube.stl and must stay that way."""
    n = _run_native_tet(50, tmp_path / "case_50")
    assert 40 <= n <= 60, f"target_cells=50 produced {n} cells"
