"""T-series (BETA2695-2700) unit tests.

T1: normal_smooth (vertex normal Laplacian smoothing).
T2: halton 3D low-discrepancy sequence.
T5: native_ai model_registry (discover/select).
T6: boundary_stats (surface vs interior classification).
"""
from __future__ import annotations

import numpy as np
import pytest


def _unit_tet():
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    F = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int64)
    return V, F


def test_t1_compute_vertex_normals_unit_length():
    from core.preprocessor.normal_smooth import compute_vertex_normals
    V, F = _unit_tet()
    N = compute_vertex_normals(V, F)
    assert N.shape == (4, 3)
    norms = np.linalg.norm(N, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-9)


def test_t1_smooth_vertex_normals_renormalized():
    from core.preprocessor.normal_smooth import smooth_vertex_normals
    V, F = _unit_tet()
    Ns, info = smooth_vertex_normals(V, F, n_iter=3)
    assert Ns.shape == (4, 3)
    norms = np.linalg.norm(Ns, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-6)
    assert info.n_iter == 3


def test_t2_halton_3d_in_unit_cube():
    from core.utils.halton import halton_3d
    pts = halton_3d(64, bbox_min=np.array([0.0] * 3), bbox_max=np.array([1.0] * 3))
    assert pts.shape == (64, 3)
    assert pts.min() >= 0.0
    assert pts.max() <= 1.0


def test_t2_halton_3d_better_than_random():
    """Halton stddev should be close to uniform target ~0.289."""
    from core.utils.halton import halton_3d
    pts = halton_3d(256, bbox_min=np.array([0.0] * 3), bbox_max=np.array([1.0] * 3))
    std = pts.std(axis=0)
    # uniform [0,1]^3 has std = 1/sqrt(12) ≈ 0.289
    assert np.all(std > 0.2)
    assert np.all(std < 0.4)


def test_t5_model_registry_empty_dir(tmp_path):
    from core.generator.native_ai.model_registry import discover_models, select_best_model
    found = discover_models(tmp_path)
    assert found == []
    best = select_best_model(tmp_path)
    assert best is None


def test_t5_model_registry_select_best(tmp_path):
    """Mock 3 .pt files, pick lowest val_loss."""
    pytest.importorskip("torch")
    import torch
    from core.generator.native_ai.model_registry import discover_models, select_best_model

    for name, vl in [("a.pt", 0.1), ("b.pt", 0.5), ("c.pt", 0.05)]:
        ckpt = {
            "model_state_dict": {},
            "architecture": "v1",
            "final_val_loss": vl,
            "n_train": 100,
            "trained_at": "2026-05-01",
        }
        torch.save(ckpt, tmp_path / name)

    found = discover_models(tmp_path)
    assert len(found) == 3
    best = select_best_model(tmp_path, metric="val_loss", direction="lower")
    assert best is not None
    assert best.name == "c"
    assert abs(best.val_loss - 0.05) < 1e-9


def test_t6_boundary_vertex_stats_basic():
    from core.analyzer.boundary_stats import boundary_vertex_stats
    # 4 surface vertices + 1 interior, 4 tets all touching surface.
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [0.25, 0.25, 0.25]],
        dtype=np.float64,
    )
    tets = np.array(
        [[0, 1, 2, 4], [0, 1, 3, 4], [0, 2, 3, 4], [1, 2, 3, 4]],
        dtype=np.int64,
    )
    r = boundary_vertex_stats(pts, tets, n_input_surface_verts=4)
    assert r.n_total_vertices == 5
    assert r.n_surface_vertices == 4
    assert r.n_interior_vertices == 1
    assert r.n_boundary_tets == 4
    assert r.n_interior_tets == 0
    assert abs(r.surface_ratio - 0.8) < 1e-9


def test_t6_boundary_vertex_stats_empty():
    from core.analyzer.boundary_stats import boundary_vertex_stats
    r = boundary_vertex_stats(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 4), dtype=np.int64),
        n_input_surface_verts=0,
    )
    assert r.n_total_vertices == 0


def test_t6_boundary_vertex_stats_all_interior():
    """Synthetic: 1 surface vert + 4 interior, single tet of all-interior."""
    from core.analyzer.boundary_stats import boundary_vertex_stats
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [0.5, 0.5, 0.5]],
        dtype=np.float64,
    )
    # tet uses indices 1,2,3,4 — all interior since n_input=1.
    tets = np.array([[1, 2, 3, 4]], dtype=np.int64)
    r = boundary_vertex_stats(pts, tets, n_input_surface_verts=1)
    assert r.n_surface_vertices == 1
    assert r.n_interior_vertices == 4
    assert r.n_boundary_tets == 0
    assert r.n_interior_tets == 1
