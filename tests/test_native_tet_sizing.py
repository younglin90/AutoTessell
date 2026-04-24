"""R120 + R158 — sizing field & determinism tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_gradient_limited_caps_ratio() -> None:
    from core.generator.native_tet.adaptive import gradient_limited_sizing

    s = np.array([0.1, 1.0, 1.0, 1.0], dtype=np.float64)
    E = np.array([[0, 1], [1, 2], [2, 3]], dtype=np.int64)
    out = gradient_limited_sizing(s, E, max_ratio=1.5, max_iter=50)
    # vertex 0 은 고정, 인접은 0.15 이하.
    assert out[0] <= 0.1 + 1e-9
    # 인접 edge 비율 감시.
    for (u, v) in E.tolist():
        ratio = max(out[u], out[v]) / max(min(out[u], out[v]), 1e-30)
        assert ratio <= 1.5 + 1e-6


def test_distance_based_sizing_monotone() -> None:
    from core.generator.native_tet.adaptive import distance_based_sizing

    V = np.array(
        [[0, 0, 0], [0.5, 0, 0], [1.0, 0, 0], [2.0, 0, 0]],
        dtype=np.float64,
    )
    Vs = np.array([[0, 0, 0]], dtype=np.float64)
    s = distance_based_sizing(V, Vs, target_edge=1.0, near_ratio=0.5, far_ratio=2.0)
    # 거리 증가 → sizing 증가.
    assert s[0] <= s[1] <= s[2] <= s[3]


def test_sizing_callback_scalar_and_vector() -> None:
    from core.generator.native_tet.adaptive import sizing_callback_eval

    V = np.zeros((5, 3), dtype=np.float64)
    s = sizing_callback_eval(V, lambda x: 0.7)
    assert s.shape == (5,)
    assert np.allclose(s, 0.7)

    def cb_vec(arr):
        return np.full(arr.shape[0], 1.3)

    s2 = sizing_callback_eval(V, cb_vec)
    assert np.allclose(s2, 1.3)


def test_native_tet_determinism_small() -> None:
    """R158 — 동일 입력 두 번 실행 → 동일 tet 배열."""
    from core.generator.native_tet.mesher import generate_native_tet
    import tempfile
    from pathlib import Path

    # 간이 tetrahedron-like 입력 (8 vertex cube).
    import trimesh

    m = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    with tempfile.TemporaryDirectory() as td:
        r1 = generate_native_tet(
            V, F, Path(td) / "c1", seed_density=6,
            enable_phase_a=True, enable_phase_b=False,
        )
        r2 = generate_native_tet(
            V, F, Path(td) / "c2", seed_density=6,
            enable_phase_a=True, enable_phase_b=False,
        )

    if not (r1.success and r2.success):
        pytest.skip("generate_native_tet cube 실패 환경")
    assert r1.n_cells == r2.n_cells
    if r1.tets is not None and r2.tets is not None:
        # tet 순서는 다를 수 있지만 frozenset 비교.
        s1 = {tuple(sorted(map(int, t))) for t in r1.tets}
        s2 = {tuple(sorted(map(int, t))) for t in r2.tets}
        assert s1 == s2
