"""native_ai skeleton unit tests."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.generator.native_ai import (
    AIVolumeConfig,
    AIVolumeResult,
    generate_native_ai_volume,
)


def _unit_cube_mesh() -> tuple[np.ndarray, np.ndarray]:
    V = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
         [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
        dtype=np.float64,
    )
    F = np.array(
        [[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
         [0, 5, 1], [0, 4, 5], [1, 6, 2], [1, 5, 6],
         [2, 7, 3], [2, 6, 7], [3, 4, 0], [3, 7, 4]],
        dtype=np.int64,
    )
    return V, F


def test_native_ai_config_defaults():
    cfg = AIVolumeConfig()
    assert cfg.mesh_type == "tet"
    assert cfg.quality_level == "standard"
    assert cfg.seed_density == 8
    assert cfg.enable_bl is True
    assert cfg.bl_num_layers == 3
    assert cfg.ai_smoothing is False
    assert cfg.ai_surface_repair is False
    assert cfg.ai_collision_predict is False


def test_native_ai_tet_dispatch():
    V, F = _unit_cube_mesh()
    with tempfile.TemporaryDirectory() as td:
        cfg = AIVolumeConfig(mesh_type="tet", enable_bl=False)
        r = generate_native_ai_volume(V, F, Path(td) / "c", cfg)
        assert isinstance(r, AIVolumeResult)
        assert r.success is True
        assert r.mesh_type == "tet"
        assert r.backend == "native_tet"
        assert r.n_cells > 0
        assert r.grade in ("A", "B", "C", "D")
        assert r.elapsed > 0
        # AI not yet applied
        assert r.ai_applied == {
            "smoothing": False,
            "surface_repair": False,
            "collision_predict": False,
        }


def test_native_ai_hex_dispatch():
    V, F = _unit_cube_mesh()
    with tempfile.TemporaryDirectory() as td:
        cfg = AIVolumeConfig(mesh_type="hex", seed_density=4, enable_bl=False)
        r = generate_native_ai_volume(V, F, Path(td) / "c", cfg)
        assert isinstance(r, AIVolumeResult)
        assert r.success is True
        assert r.mesh_type == "hex"
        assert r.backend == "native_hex"
        assert r.n_cells > 0


def test_native_ai_poly_dispatch():
    V, F = _unit_cube_mesh()
    with tempfile.TemporaryDirectory() as td:
        cfg = AIVolumeConfig(mesh_type="poly", seed_density=4, enable_bl=False)
        r = generate_native_ai_volume(V, F, Path(td) / "c", cfg)
        assert isinstance(r, AIVolumeResult)
        assert r.mesh_type == "poly"
        assert r.backend == "native_poly"


def test_native_ai_unknown_mesh_type():
    V, F = _unit_cube_mesh()
    with tempfile.TemporaryDirectory() as td:
        cfg = AIVolumeConfig(mesh_type="xxx", enable_bl=False)  # type: ignore[arg-type]
        r = generate_native_ai_volume(V, F, Path(td) / "c", cfg)
        assert r.success is False
        assert "unknown mesh_type" in r.message


def test_native_ai_with_bl_does_not_crash():
    V, F = _unit_cube_mesh()
    with tempfile.TemporaryDirectory() as td:
        cfg = AIVolumeConfig(mesh_type="tet", enable_bl=True, bl_num_layers=2)
        r = generate_native_ai_volume(V, F, Path(td) / "c", cfg)
        # success may be True (tet OK) — BL might fail on tiny cube, but
        # generate_native_ai_volume catches BL exceptions and continues.
        assert r.mesh_type == "tet"


# ─────────────────────────────────────────────────────────────────────────
# AI-V1 ML-tet smoothing tests (skeleton)
# ─────────────────────────────────────────────────────────────────────────

def test_ml_tet_smoothing_skeleton_skip():
    """skeleton: trained model 미배치 → graceful skip"""
    from core.generator.native_ai import (
        ml_tet_smoothing_apply,
        MLTetSmoothingResult,
    )
    pts = np.random.rand(20, 3)
    tets = np.random.randint(0, 20, (5, 4))
    new_pts, new_tets, r = ml_tet_smoothing_apply(pts, tets)
    assert isinstance(r, MLTetSmoothingResult)
    assert r.success is False  # skeleton — model not trained
    assert "model not yet trained" in r.message or "not available" in r.message
    # Graceful pass-through: input == output
    assert new_pts.shape == pts.shape
    assert new_tets.shape == tets.shape


def test_ml_tet_smoothing_predictor_architecture():
    """predictor MLP architecture sketch는 즉시 build 가능."""
    from core.generator.native_ai import build_quality_predictor_skeleton
    m = build_quality_predictor_skeleton()
    if m is None:
        pytest.skip("torch not available")
    # input 20-dim, output 1-dim with sigmoid
    import torch
    x = torch.randn(4, 20)
    y = m(x)
    assert y.shape == (4, 1)
    assert (y >= 0).all() and (y <= 1).all()  # sigmoid range


# ─────────────────────────────────────────────────────────────────────────
# AI-V3 ML BL collision predict tests (skeleton)
# ─────────────────────────────────────────────────────────────────────────

def test_ml_bl_collision_skeleton_skip():
    """skeleton: graceful skip → infinity distance fallback."""
    from core.generator.native_ai import (
        predict_bl_collision_distances,
        BLCollisionPredictResult,
    )
    pts = np.random.rand(20, 3)
    wall_v = np.array([0, 1, 2, 3], dtype=np.int64)
    wall_f = np.array([0, 1], dtype=np.int64)
    wall_fv = np.array([[0, 1, 2], [1, 2, 3]], dtype=np.int64)
    dist, r = predict_bl_collision_distances(pts, wall_v, wall_f, wall_fv)
    assert isinstance(r, BLCollisionPredictResult)
    assert r.success is False  # skeleton
    assert dist.shape == (4,)
    assert np.isinf(dist).all()  # infinity fallback


def test_ml_bl_collision_predictor_architecture():
    """BL collision predictor MLP."""
    from core.generator.native_ai import build_collision_predictor_skeleton
    m = build_collision_predictor_skeleton()
    if m is None:
        pytest.skip("torch not available")
    import torch
    x = torch.randn(4, 12)
    y = m(x)
    assert y.shape == (4, 1)


# ─────────────────────────────────────────────────────────────────────────
# C8 GPU envelope tests
# ─────────────────────────────────────────────────────────────────────────

def test_gpu_envelope_check_basic():
    """torch.cdist 기반 envelope check — torch 있으면 동작."""
    from core.generator.native_ai import gpu_envelope_check, GPUEnvelopeResult
    np.random.seed(42)
    surf = np.random.rand(20, 3)
    faces = np.random.randint(0, 20, (10, 3))
    query = np.random.rand(50, 3)
    inside, r = gpu_envelope_check(query, surf, faces, eps=2.0)  # large eps
    assert isinstance(r, GPUEnvelopeResult)
    assert r.n_query == 50
    if r.success:
        # All query points within large eps
        assert inside.sum() > 0
        assert r.backend.startswith("torch_")
    else:
        # torch not available — graceful skip
        assert r.backend == "skip"


def test_gpu_envelope_empty_query():
    """0 query — graceful."""
    from core.generator.native_ai import gpu_envelope_check
    surf = np.random.rand(5, 3)
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    query = np.zeros((0, 3), dtype=np.float64)
    inside, r = gpu_envelope_check(query, surf, faces, eps=0.1)
    assert inside.shape == (0,)
    assert r.n_query == 0


# ─────────────────────────────────────────────────────────────────────────
# AI-V1.1 training data generator tests
# ─────────────────────────────────────────────────────────────────────────

def test_extract_tet_features_regular_unit_tet():
    """Regular unit tet → high quality + correct shapes."""
    from core.generator.native_ai import extract_tet_features
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
                   dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    coords, context, q = extract_tet_features(pts, tets, 0)
    assert coords.shape == (12,)
    assert context.shape == (8,)
    assert 0.5 < q <= 1.0  # regular tet → high quality


def test_extract_tet_features_degenerate():
    """Degenerate tet (zero volume) → 0 quality."""
    from core.generator.native_ai import extract_tet_features
    pts = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]],
                   dtype=np.float64)  # all collinear
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    _, _, q = extract_tet_features(pts, tets, 0)
    assert q == 0.0


def test_extract_features_batch():
    """Batch extraction returns correct shapes."""
    from core.generator.native_ai import extract_features_batch
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
        [1, 1, 1], [2, 0, 0], [0, 2, 0], [0, 0, 2],
    ], dtype=np.float64)
    tets = np.array([
        [0, 1, 2, 3],
        [4, 5, 6, 7],
    ], dtype=np.int64)
    coords, contexts, quals = extract_features_batch(pts, tets)
    assert coords.shape == (2, 12)
    assert contexts.shape == (2, 8)
    assert quals.shape == (2,)
    assert (quals >= 0).all() and (quals <= 1).all()


def test_generate_dataset_skeleton_skip():
    """Dataset generator skeleton (legacy) currently stub → not implemented."""
    from core.generator.native_ai import (
        generate_dataset_skeleton, DatasetGenResult,
    )
    r = generate_dataset_skeleton("/tmp/dummy_ai_v11.npz", n_samples=100)
    assert isinstance(r, DatasetGenResult)
    assert r.success is False
    assert "not yet implemented" in r.message


def test_generate_dataset_from_meshes_real():
    """Real dataset generator: multi-mesh → .npz save/load."""
    from core.generator.native_ai import generate_dataset_from_meshes

    pts1 = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]],
                    dtype=np.float64)
    tets1 = np.array([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=np.int64)

    pts2 = np.array([[0, 0, 0], [2, 0, 0], [0, 2, 0], [0, 0, 2]],
                    dtype=np.float64)
    tets2 = np.array([[0, 1, 2, 3]], dtype=np.int64)

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "dataset.npz"
        r = generate_dataset_from_meshes(
            str(out), [pts1, pts2], [tets1, tets2], samples_per_mesh=5,
        )
        assert r.success is True
        assert r.n_samples == 3  # 2 + 1 = 3 total tets, capped by T<5
        assert Path(out).exists()
        d = np.load(str(out))
        assert d["coords"].shape == (3, 12)
        assert d["context"].shape == (3, 8)
        assert d["quality"].shape == (3,)
        assert (d["quality"] >= 0).all() and (d["quality"] <= 1).all()


def test_generate_dataset_length_mismatch():
    """Mesh list length mismatch → graceful error."""
    from core.generator.native_ai import generate_dataset_from_meshes
    pts = [np.zeros((4, 3))]
    tets = []  # mismatch
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "x.npz"
        r = generate_dataset_from_meshes(str(out), pts, tets)
        assert r.success is False
        assert "mismatch" in r.message


def test_generate_dataset_empty():
    """Empty mesh list → 0 samples graceful."""
    from core.generator.native_ai import generate_dataset_from_meshes
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "x.npz"
        r = generate_dataset_from_meshes(str(out), [], [])
        assert r.success is False
        assert "0 samples" in r.message


# ─────────────────────────────────────────────────────────────────────────
# AI-V4 diffusion stub tests
# ─────────────────────────────────────────────────────────────────────────

def test_diffusion_volume_research_stub():
    """Diffusion volume gen returns research_stub backend."""
    from core.generator.native_ai import (
        diffusion_generate_volume, DiffusionVolumeResult,
    )
    V = np.random.rand(10, 3)
    F = np.random.randint(0, 10, (5, 3))
    pts, tets, r = diffusion_generate_volume(V, F)
    assert isinstance(r, DiffusionVolumeResult)
    assert r.success is False
    assert r.backend == "research_stub"
    assert pts.shape == (0, 3)
    assert tets.shape == (0, 4)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
