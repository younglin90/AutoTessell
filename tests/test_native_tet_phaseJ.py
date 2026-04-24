"""Round 10 / Phase J — Inverted tet detection + Phase B comparison."""
from __future__ import annotations

import numpy as np
import pytest


# ======================================================================
# Inverted tet
# ======================================================================


def test_signed_volume6_positive_tet() -> None:
    from core.generator.native_tet.validate import signed_volume6

    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    v6 = signed_volume6(pts, tets)
    assert v6[0] > 0


def test_fix_inverted_tets_swaps_negative() -> None:
    from core.generator.native_tet.validate import fix_inverted_tets, signed_volume6

    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64,
    )
    # v2, v3 swapped → signed vol negative.
    tets = np.array([[0, 1, 3, 2]], dtype=np.int64)
    v6 = signed_volume6(pts, tets)
    assert v6[0] < 0

    fixed, vr = fix_inverted_tets(pts, tets)
    assert vr.n_inverted_before == 1
    assert vr.n_fixed_by_swap == 1
    v6_after = signed_volume6(pts, fixed)
    assert v6_after[0] > 0


def test_fix_inverted_noop_on_all_positive() -> None:
    from core.generator.native_tet.validate import fix_inverted_tets

    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    fixed, vr = fix_inverted_tets(pts, tets)
    assert vr.n_inverted_before == 0
    assert vr.n_fixed_by_swap == 0


def test_fix_inverted_detects_degenerate() -> None:
    from core.generator.native_tet.validate import fix_inverted_tets

    # 4 공면 점 — vol = 0.
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    fixed, vr = fix_inverted_tets(pts, tets)
    assert vr.n_degenerate == 1


# ======================================================================
# Integration — native_tet 이 invalid mesh 를 내보내지 않음
# ======================================================================


def test_native_tet_final_mesh_all_positive(tmp_path) -> None:
    """최종 출력의 모든 tet 이 양의 부피."""
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator.native_tet.validate import signed_volume6
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    res = generate_native_tet(
        V, F, tmp_path / "sphere_validate",
        seed_density=6,
        enable_phase_a=True,
        enable_phase_b=True,
        enable_phase_c=True,
        local_ops_iterations=2,
    )
    assert res.success, res.message
    v6 = signed_volume6(res.tet_points, res.tets)
    # 허용 오차 이내로 전부 >= 0.
    assert (v6 >= -1e-18).all(), (
        f"invalid tet {int((v6 < 0).sum())} 개 포함"
    )
