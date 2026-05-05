"""P1 — CDT recovery cycle tests."""
from __future__ import annotations

import numpy as np


def _simple_cube():
    import trimesh
    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    return V, F


def test_cdt_recovery_never_worsens_ratio() -> None:
    from scipy.spatial import Delaunay
    from core.generator.native_tet.cdt_recovery import run_cdt_recovery
    from core.generator.native_tet.cdt_check import check_edge_recovery, cdt_ratio

    V, F = _simple_cube()
    D = Delaunay(V)
    tets = np.asarray(D.simplices, dtype=np.int64)

    r_before = check_edge_recovery(F, tets)
    ratio_before = cdt_ratio(r_before)

    new_pts, new_tets, info = run_cdt_recovery(
        V, tets, V, F, max_cycles=3, points_budget=100,
    )
    r_after = check_edge_recovery(F, new_tets)
    ratio_after = cdt_ratio(r_after)

    # 절대 악화되지 않아야 한다 (revert 로직 확인).
    assert ratio_after >= ratio_before - 1e-9
    # tet 수는 감소하지 않아야 한다 (삽입은 tet 을 유지/증가).
    assert new_tets.shape[0] >= tets.shape[0]


def test_cdt_recovery_result_fields() -> None:
    from scipy.spatial import Delaunay
    from core.generator.native_tet.cdt_recovery import run_cdt_recovery

    V, F = _simple_cube()
    D = Delaunay(V)
    tets = np.asarray(D.simplices, dtype=np.int64)
    _, _, info = run_cdt_recovery(
        V, tets, V, F, max_cycles=2, points_budget=50,
    )
    assert info.n_edges_before >= 0
    assert info.n_edges_after >= 0
    assert 0.0 <= info.ratio_before <= 1.0
    assert 0.0 <= info.ratio_after <= 1.0
    assert info.reverted >= 0
