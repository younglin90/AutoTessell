from __future__ import annotations

import numpy as np
import pytest

from core.utils.native_extensions import import_native_extension


def test_metric_bcc_candidates_are_deterministic_and_interior():
    kernel = import_native_extension("native_tet_metric_seed")
    args = (
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 2.0, 3.0]),
        np.array([1.0, 4.0, 9.0]),
        0.5,
        1000,
    )
    first = np.asarray(kernel.generate_metric_bcc_candidates(*args))
    second = np.asarray(kernel.generate_metric_bcc_candidates(*args))
    assert first.shape == second.shape
    assert np.array_equal(first, second)
    assert first.ndim == 2 and first.shape[1] == 3
    assert np.all(first > np.array([0.0, 0.0, 0.0]))
    assert np.all(first < np.array([1.0, 2.0, 3.0]))


def test_metric_spacing_and_budget_are_explicit_hard_inputs():
    kernel = import_native_extension("native_tet_metric_seed")
    with pytest.raises(ValueError):
        kernel.generate_metric_bcc_candidates(
            np.zeros(3), np.ones(3), np.ones(3), 0.0, 100
        )
    with pytest.raises(ValueError):
        kernel.generate_metric_bcc_candidates(
            np.zeros(3), np.ones(3), np.ones(3), 0.25, 1
        )


def test_mesher_metric_seed_route_requires_explicit_inputs(tmp_path):
    import trimesh

    from core.generator.native_tet.mesher import generate_native_tet

    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    with pytest.raises(ValueError, match="requires metric_seed"):
        generate_native_tet(
            vertices,
            faces,
            tmp_path / "missing_metric_inputs",
            target_edge_length=0.4,
            enable_phase_a=False,
            enable_metric_seed=True,
        )


def test_mesher_uses_explicit_cpp_metric_seed_route(tmp_path):
    import trimesh

    from core.generator.native_tet.mesher import generate_native_tet

    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    result = generate_native_tet(
        vertices,
        faces,
        tmp_path / "metric_cube",
        target_edge_length=0.4,
        sliver_quality_threshold=0.0,
        enable_phase_a=False,
        recovery_iterations=0,
        smooth_iterations=0,
        enable_same_side_retriangulation=False,
        allow_external_fallback=False,
        enable_metric_seed=True,
        metric_seed_diagonal=(1.0, 1.0, 1.0),
        metric_seed_spacing=0.4,
        metric_seed_max_candidates=1000,
    )
    assert result.success, result.message
    assert result.tet_points is not None and result.tets is not None
    assert result.debug_info is not None
