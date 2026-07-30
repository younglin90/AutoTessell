"""AMIPS must never relocate a vertex on the current tetrahedral boundary."""

from __future__ import annotations

import numpy as np
import pytest

from core.generator.native_tet.amips import (
    _boundary_vertex_mask,
    _boundary_vertex_mask_python,
    smooth_amips,
    smooth_amips_analytic,
)


def _cube_star() -> tuple[np.ndarray, np.ndarray]:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
            [0.0, 1.0, 1.0],
            [0.43, 0.51, 0.47],
        ],
        dtype=np.float64,
    )
    faces = np.array(
        [
            [0, 2, 1],
            [0, 3, 2],
            [4, 5, 6],
            [4, 6, 7],
            [0, 1, 5],
            [0, 5, 4],
            [3, 7, 6],
            [3, 6, 2],
            [0, 4, 7],
            [0, 7, 3],
            [1, 2, 6],
            [1, 6, 5],
        ],
        dtype=np.int64,
    )
    tets = np.column_stack(
        [faces, np.full(faces.shape[0], 8, dtype=np.int64)],
    )
    volumes = np.einsum(
        "ij,ij->i",
        points[tets[:, 1]] - points[tets[:, 0]],
        np.cross(
            points[tets[:, 2]] - points[tets[:, 0]],
            points[tets[:, 3]] - points[tets[:, 0]],
        ),
    )
    negative = volumes < 0.0
    tets[negative, 2], tets[negative, 3] = (
        tets[negative, 3].copy(),
        tets[negative, 2].copy(),
    )
    return points, tets


def test_python_boundary_mask_finds_cube_shell_only() -> None:
    points, tets = _cube_star()
    mask = _boundary_vertex_mask_python(tets, points.shape[0])
    np.testing.assert_array_equal(mask, [True] * 8 + [False])


def test_native_boundary_mask_matches_python_fallback() -> None:
    from core.utils.native_extensions import load_native_tet_predicates

    native = load_native_tet_predicates()
    if native is None or not hasattr(native, "tet_boundary_vertex_mask"):
        pytest.skip("native_tet_predicates boundary-mask kernel is not built")
    points, tets = _cube_star()
    expected = _boundary_vertex_mask_python(tets, points.shape[0])
    actual = np.asarray(
        native.tet_boundary_vertex_mask(tets, points.shape[0]),
        dtype=np.bool_,
    )
    np.testing.assert_array_equal(actual, expected)


def test_native_boundary_mask_rejects_invalid_contracts() -> None:
    from core.utils.native_extensions import load_native_tet_predicates

    native = load_native_tet_predicates()
    if native is None or not hasattr(native, "tet_boundary_vertex_mask"):
        pytest.skip("native_tet_predicates boundary-mask kernel is not built")
    _, tets = _cube_star()
    with pytest.raises((TypeError, ValueError)):
        native.tet_boundary_vertex_mask(tets, -1)
    with pytest.raises((TypeError, ValueError)):
        native.tet_boundary_vertex_mask(tets.astype(np.int32), 9)
    with pytest.raises((TypeError, ValueError)):
        native.tet_boundary_vertex_mask(tets[:, :3], 9)
    invalid = tets.copy()
    invalid[0, 0] = 9
    with pytest.raises((TypeError, ValueError)):
        native.tet_boundary_vertex_mask(invalid, 9)
    invalid = tets.copy()
    invalid[0, 0] = -1
    with pytest.raises((TypeError, ValueError)):
        native.tet_boundary_vertex_mask(invalid, 9)
    invalid = tets.copy()
    invalid[0, 1] = invalid[0, 0]
    with pytest.raises((TypeError, ValueError)):
        native.tet_boundary_vertex_mask(invalid, 9)


def test_analytic_amips_automatically_freezes_current_boundary() -> None:
    points, tets = _cube_star()
    _, moved = smooth_amips_analytic(points, tets, n_iter=2, step_init=0.05)
    np.testing.assert_array_equal(moved[:8], points[:8])
    np.testing.assert_array_equal(
        _boundary_vertex_mask(tets, points.shape[0]), [True] * 8 + [False]
    )


def test_analytic_amips_unions_explicit_and_boundary_locks() -> None:
    points, tets = _cube_star()
    _, moved = smooth_amips_analytic(
        points,
        tets,
        locked_vertex_ids=np.array([8], dtype=np.int64),
        n_iter=2,
        step_init=0.05,
    )
    np.testing.assert_array_equal(moved, points)


def test_finite_difference_amips_automatically_freezes_current_boundary() -> None:
    points, tets = _cube_star()
    _, moved = smooth_amips(points, tets, n_iter=2, step_init=0.05)
    np.testing.assert_array_equal(moved[:8], points[:8])


def test_torch_cpu_amips_automatically_freezes_current_boundary() -> None:
    from core.generator.native_tet.amips_torch import (
        is_available,
        smooth_amips_torch,
    )

    if not is_available():
        pytest.skip("torch optional dependency unavailable; torch AMIPS route unreachable")
    points, tets = _cube_star()
    result, moved = smooth_amips_torch(
        points,
        tets,
        n_iter=1,
        step_init=0.05,
        use_cuda=False,
    )
    np.testing.assert_array_equal(moved[:8], points[:8])
    assert result.n_moved == 1
    assert float(np.max(np.linalg.norm(moved[:8] - points[:8], axis=1))) == 0.0


def test_torch_amips_unions_explicit_and_boundary_locks() -> None:
    from core.generator.native_tet.amips_torch import (
        is_available,
        smooth_amips_torch,
    )

    if not is_available():
        pytest.skip("torch optional dependency unavailable; torch AMIPS route unreachable")
    points, tets = _cube_star()
    result, moved = smooth_amips_torch(
        points,
        tets,
        locked_vertex_ids=np.array([8], dtype=np.int64),
        n_iter=1,
        step_init=0.05,
        use_cuda=False,
    )
    np.testing.assert_array_equal(moved, points)
    assert result.n_moved == 0


def test_torch_cpu_cuda_boundary_lock_parity() -> None:
    from core.generator.native_tet.amips_torch import (
        has_cuda,
        is_available,
        smooth_amips_torch,
    )

    if not is_available():
        pytest.skip("torch optional dependency unavailable; torch AMIPS route unreachable")
    if not has_cuda():
        pytest.skip("CUDA unavailable; CPU torch boundary-lock contract verified separately")
    points, tets = _cube_star()
    _, cpu = smooth_amips_torch(
        points,
        tets,
        n_iter=1,
        step_init=0.05,
        use_cuda=False,
    )
    _, cuda = smooth_amips_torch(
        points,
        tets,
        n_iter=1,
        step_init=0.05,
        use_cuda=True,
    )
    np.testing.assert_array_equal(cpu[:8], points[:8])
    np.testing.assert_array_equal(cuda[:8], points[:8])
    np.testing.assert_allclose(cuda, cpu, rtol=1e-12, atol=1e-12)
