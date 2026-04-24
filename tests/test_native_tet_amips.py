"""P2 — AMIPS smoothing tests."""
from __future__ import annotations

import numpy as np


def test_amips_regular_tet_has_zero_energy() -> None:
    from core.generator.native_tet.amips import _tet_amips_energy

    # regular tet (edge length √2 scaled).
    pts = np.array([
        [0, 0, 0], [1, 0, 0],
        [0.5, np.sqrt(3) / 2, 0],
        [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)],
    ], dtype=np.float64)[None]   # (1, 4, 3)
    e = _tet_amips_energy(pts[:, 0], pts[:, 1], pts[:, 2], pts[:, 3])
    assert abs(float(e[0])) < 1e-4


def test_amips_sliver_has_higher_energy_than_regular() -> None:
    from core.generator.native_tet.amips import _tet_amips_energy

    reg = np.array([
        [[0, 0, 0], [1, 0, 0],
         [0.5, np.sqrt(3) / 2, 0],
         [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)]],
    ], dtype=np.float64)
    sliv = np.array([
        [[0, 0, 0], [1, 0, 0], [2, 0.01, 0], [1, 0, 0.01]],
    ], dtype=np.float64)
    e_reg = float(_tet_amips_energy(reg[:, 0], reg[:, 1], reg[:, 2], reg[:, 3])[0])
    e_sl = float(_tet_amips_energy(sliv[:, 0], sliv[:, 1], sliv[:, 2], sliv[:, 3])[0])
    assert e_sl > e_reg + 10.0


def test_amips_relocation_decreases_energy_on_sliver() -> None:
    from core.generator.native_tet.amips import smooth_amips

    # cube 8 verts + 1 interior sliver-prone point.
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        [0.05, 0.5, 0.5],   # 경계 근처 → sliver 유발.
    ], dtype=np.float64)
    tets = np.array([
        [0, 1, 2, 8], [0, 2, 3, 8],
        [4, 5, 6, 8], [4, 6, 7, 8],
        [0, 4, 5, 8], [0, 5, 1, 8],
        [2, 6, 7, 8], [2, 7, 3, 8],
        [1, 5, 6, 8], [1, 6, 2, 8],
        [0, 3, 7, 8], [0, 7, 4, 8],
    ], dtype=np.int64)
    r, new_pts = smooth_amips(
        pts, tets,
        locked_vertex_ids=np.arange(8),
        n_iter=5, alpha=1.0,
    )
    assert r.energy_after <= r.energy_before + 1e-6
