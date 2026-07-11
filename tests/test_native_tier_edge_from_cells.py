"""Unit tests for the target-cell-count → tet edge-length derivation.

Regression guard for the "tet + BL 잘 안됨" bug: a small target N (e.g. 100)
used to be ignored — the strategist's auto surface edge seeded 70k+ cells and
the aspect-ratio evaluator then stalled for 30s+.  ``_edge_from_target_cells``
makes N actually drive the tet edge so cell count tracks N.
"""

from __future__ import annotations

import math

import numpy as np

from core.generator._tier_native_common import (
    _edge_from_target_cells,
    _mesh_enclosed_volume,
)

# unit cube (V = 1): 8 corners, 12 triangles
_CUBE_V = np.array(
    [
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ],
    dtype=float,
)
_CUBE_F = np.array(
    [
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
    ],
    dtype=int,
)


def test_enclosed_volume_unit_cube():
    assert math.isclose(_mesh_enclosed_volume(_CUBE_V, _CUBE_F), 1.0, rel_tol=1e-6)


def test_edge_shrinks_as_target_cells_grows():
    e100 = _edge_from_target_cells(_CUBE_V, _CUBE_F, "tier_native_tet", 100)
    e15000 = _edge_from_target_cells(_CUBE_V, _CUBE_F, "tier_native_tet", 15000)
    assert e100 is not None and e15000 is not None
    # more cells ⇒ smaller edge
    assert e15000 < e100
    # ballpark: edge = (6√2·V/N)^(1/3); N=100 → ~0.44 on a unit cube
    assert 0.35 < e100 < 0.55


def test_unknown_tier_returns_none():
    # only native_tet is wired for now → hex/poly skip the override
    assert _edge_from_target_cells(_CUBE_V, _CUBE_F, "tier_native_hex", 100) is None


def test_open_surface_falls_back_to_bbox():
    # drop the top cap → not watertight; still returns a positive edge (bbox vol)
    open_f = _CUBE_F[:-4]
    e = _edge_from_target_cells(_CUBE_V, open_f, "tier_native_tet", 1000)
    assert e is not None and e > 0
