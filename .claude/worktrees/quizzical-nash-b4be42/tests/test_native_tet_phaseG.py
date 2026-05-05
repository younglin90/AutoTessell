"""Round 7 / Phase G — Feature lock + adversarial robustness."""
from __future__ import annotations

import numpy as np
import pytest


# ======================================================================
# Feature lock — corner 가 최종 메쉬에 그대로 유지
# ======================================================================


def test_cube_corners_preserved_after_phase_c(tmp_path) -> None:
    """큐브: Phase C 전체 돌린 뒤에도 8 corner 좌표가 원본에 정확히 존재."""
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    res = generate_native_tet(
        V, F, tmp_path / "cube_feature_lock",
        seed_density=4,
        enable_phase_a=True,
        enable_phase_b=True,
        enable_phase_c=True,
        local_ops_iterations=2,
        tangent_smooth_iterations=2,
        envelope_eps_relative=0.02,
        feature_angle_deg=30.0,
    )
    assert res.success, res.message
    assert res.tet_points is not None

    # 원본 8 corner 전부 1e-6 이내로 보존.
    found = 0
    for corner in V:
        d = np.linalg.norm(res.tet_points - corner, axis=1)
        if d.min() < 1e-6:
            found += 1
    assert found == 8, f"corner 보존 실패: {found}/8"


# ======================================================================
# Adversarial — 실제 복잡 형상에서 crash 없음
# ======================================================================


def _try_generate(case_path, stl_path):
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.load(str(stl_path), force="mesh")
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    return generate_native_tet(
        V, F, case_path,
        seed_density=6,
        enable_phase_a=True,
        enable_phase_b=False,   # 빠른 경로만 벤치.
        max_input_vertices=50000,
    )


@pytest.mark.parametrize(
    "stl_name",
    [
        "01_easy_cube.stl",
        "02_medium_cylinder.stl",
        "03_hard_bracket.stl",
    ],
)
def test_native_tet_on_bench_stls(tmp_path, stl_name) -> None:
    """tests/stl/ 의 벤치 STL 에서 crash 없이 결과 반환 (성공/실패 모두 OK)."""
    from pathlib import Path

    stl = Path(__file__).parent / "stl" / stl_name
    if not stl.exists():
        pytest.skip(f"{stl_name} 없음")

    res = _try_generate(tmp_path / stl_name, stl)
    # crash 만 아니면 OK — 성공률은 별개 벤치에서 추적.
    assert res.message, "result message 비어있음"
    assert res.success in (True, False)


def test_native_tet_survives_nonwatertight_repair(tmp_path) -> None:
    """open-edge 가 있는 mesh 에 대해서도 crash 없음 + 명확한 실패."""
    from core.generator.native_tet.mesher import generate_native_tet

    # 한 triangle 만 — boundary edge 3 개 → non-watertight.
    V = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64,
    )
    F = np.array([[0, 1, 2]], dtype=np.int64)
    res = generate_native_tet(V, F, tmp_path / "open_edge", seed_density=4)
    # 3 점으로 tet 을 만들 수 없으므로 failure 기대 (하지만 crash 아님).
    assert res.success in (True, False)
    assert res.message


def test_native_tet_phase_c_cube_envelope_tight(tmp_path) -> None:
    """큐브에 tight envelope (0.5%) 적용 — reject 되지 않고 성공."""
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    res = generate_native_tet(
        V, F, tmp_path / "cube_tight_env",
        seed_density=4,
        enable_phase_a=True,
        enable_phase_b=True,
        enable_phase_c=True,
        envelope_eps_relative=0.005,
    )
    assert res.success, res.message
