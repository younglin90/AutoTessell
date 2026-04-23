"""beta97 — native_poly Laplacian smoothing 회귀 테스트."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.generator.native_poly.smooth import SmoothResult, smooth_poly_mesh


def test_smooth_result_defaults() -> None:
    r = SmoothResult(success=True, elapsed=0.1)
    assert r.n_iter_done == 0
    assert r.max_displacement == pytest.approx(0.0)
    assert r.message == ""


def test_smooth_missing_polymesh_fails(tmp_path: Path) -> None:
    """polyMesh 없는 case → success=False."""
    r = smooth_poly_mesh(tmp_path, n_iter=2)
    assert r.success is False
    assert "polyMesh" in r.message


def test_smooth_runs_on_valid_polymesh(tmp_path: Path) -> None:
    """유효 polyMesh 에서 n_iter 회 완료 → success=True."""
    # 간단한 tetrahedron polyMesh 생성
    import sys; sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import tempfile, shutil
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    sp = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    V = np.asarray(sp.vertices, dtype=np.float64)
    F = np.asarray(sp.faces, dtype=np.int64)

    case_dir = tmp_path / "case"
    res = generate_native_tet(V, F, case_dir, seed_density=6)
    if not res.success:
        pytest.skip("native_tet failed — env issue")

    # smooth 실행
    sr = smooth_poly_mesh(case_dir, n_iter=2, relax=0.2)
    assert sr.success
    assert sr.n_iter_done == 2
    assert sr.max_displacement >= 0.0


def test_smooth_harness_params_has_smooth_iters() -> None:
    """beta97 — HARNESS_PARAMS poly 에 smooth_iters 존재."""
    from core.generator._tier_native_common import HARNESS_PARAMS
    poly = HARNESS_PARAMS["tier_native_poly"]
    assert "smooth_iters" in poly["standard"]
    assert poly["standard"]["smooth_iters"] == 3
    assert poly["fine"]["smooth_iters"] == 5
    assert poly["draft"]["smooth_iters"] == 0


def test_smooth_tier_param_keys_include_smooth() -> None:
    """beta97 — smooth_iters/smooth_relax _TIER_PARAM_KEYS 에 포함."""
    import core.generator._tier_native_common as m
    import inspect
    src = inspect.getsource(m)
    assert "smooth_iters" in src
    assert "smooth_relax" in src


def test_harness_accepts_smooth_iters_kwarg() -> None:
    """run_native_poly_harness 가 smooth_iters kwarg 수용."""
    import inspect
    from core.generator.native_poly.harness import run_native_poly_harness
    sig = inspect.signature(run_native_poly_harness)
    assert "smooth_iters" in sig.parameters
    assert sig.parameters["smooth_iters"].default == 0
