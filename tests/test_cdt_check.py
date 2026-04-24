"""Round 49 — CDT edge recovery check tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_cdt_check_empty() -> None:
    from core.generator.native_tet.cdt_check import check_edge_recovery

    F = np.zeros((0, 3), dtype=np.int64)
    tets = np.zeros((0, 4), dtype=np.int64)
    r = check_edge_recovery(F, tets)
    assert r.n_surface_edges == 0
    assert r.n_missing == 0


def test_cdt_check_all_present() -> None:
    from core.generator.native_tet.cdt_check import check_edge_recovery

    # Single triangle F=(0,1,2), tet=(0,1,2,3) → surface edges {(0,1),(1,2),(0,2)}
    # 모두 tet edge 에 포함.
    F = np.array([[0, 1, 2]], dtype=np.int64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    r = check_edge_recovery(F, tets)
    assert r.n_missing == 0
    assert r.n_surface_edges == 3
    assert r.n_present_as_tet_edges == 3


def test_cdt_check_detects_missing() -> None:
    from core.generator.native_tet.cdt_check import check_edge_recovery

    # 입력 surface 에는 (4,5) edge 가 있지만 tet 에는 없음.
    F = np.array([[0, 1, 2], [4, 5, 6]], dtype=np.int64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    r = check_edge_recovery(F, tets)
    # surface edges: (0,1),(1,2),(0,2),(4,5),(4,6),(5,6) = 6.
    assert r.n_surface_edges == 6
    # tet edges 는 (0,1),(0,2),(0,3),(1,2),(1,3),(2,3).
    # 교집합: (0,1),(0,2),(1,2) = 3. missing = 3.
    assert r.n_present_as_tet_edges == 3
    assert r.n_missing == 3


def test_cdt_check_on_generated_cube(tmp_path) -> None:
    """실제 native_tet 출력의 cube CDT 상태 보고 (실패 없음 확인용)."""
    from core.generator.native_tet.cdt_check import check_edge_recovery
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    res = generate_native_tet(V, F, tmp_path / "cube", seed_density=4)
    assert res.success, res.message

    # tet_points 과 원본 V 가 다를 수 있음 — F indexing 이 유효하려면 surface
    # vertex 는 new-index [0, n_surface) 로 보존됨 (mesher 의 remap 규칙).
    # 따라서 F 를 그대로 쓸 수 있음.
    r = check_edge_recovery(F, res.tets)
    assert r.n_surface_edges > 0
    # 현재 native_tet 은 엄격 CDT 가 아니라 approximate recovery.
    # 최소 1/3 이상만 보장 (실측 ~1/3, 향후 라운드에서 개선 목표).
    assert r.n_present_as_tet_edges >= int(r.n_surface_edges * 0.3)
