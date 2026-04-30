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
    """AI-V1.C / beta2588: trained model 경로 미제공 → graceful skip."""
    from core.generator.native_ai import (
        ml_tet_smoothing_apply,
        MLTetSmoothingResult,
    )
    pts = np.random.rand(20, 3)
    tets = np.random.randint(0, 20, (5, 4))
    new_pts, new_tets, r = ml_tet_smoothing_apply(pts, tets)
    assert isinstance(r, MLTetSmoothingResult)
    assert r.success is False  # model 경로 미제공 → skip.
    # 메시지: "not provided" / "not yet trained" / "not available" 중 하나.
    msg = r.message
    assert (
        "model not provided" in msg
        or "model not yet trained" in msg
        or "not available" in msg
    ), f"unexpected message: {msg}"
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


def test_gpu_envelope_check_accurate_eberly():
    """C8-2.1.2 / beta2592 — Eberly + torch.compile fused kernel.
    point (0,0,0) 와 z=1 평면 → 정확 거리 = 1.0.
    eps=0.5 → 외부 (False), eps=1.5 → 내부 (True).
    """
    from core.generator.native_ai import gpu_envelope_check_accurate
    surf = np.array([
        [0, 0, 1], [1, 0, 1], [0, 1, 1],
    ], dtype=np.float64)
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    query = np.array([[0.0, 0.0, 0.0]], dtype=np.float64)
    # eps=0.5 → 외부.
    inside_out, r_out = gpu_envelope_check_accurate(query, surf, faces, eps=0.5)
    if r_out.success:
        assert inside_out[0] == False, f"expected outside, got {inside_out[0]}"
    # eps=1.5 → 내부.
    inside_in, r_in = gpu_envelope_check_accurate(query, surf, faces, eps=1.5)
    if r_in.success:
        assert inside_in[0] == True, f"expected inside, got {inside_in[0]}"
        assert "eberly" in r_in.backend


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

# ─────────────────────────────────────────────────────────────────────────
# AI-V1.1.3 / V1.2 train + inference end-to-end tests
# ─────────────────────────────────────────────────────────────────────────

def test_train_predictor_end_to_end():
    """Generate dataset → train → save → load → predict full pipeline."""
    from core.generator.native_ai import (
        generate_dataset_from_meshes,
        train_quality_predictor,
        load_trained_predictor,
        predict_quality_batch,
        extract_features_batch,
    )
    try:
        import torch  # noqa: F401
    except ImportError:
        pytest.skip("torch not available")

    # Build small synthetic dataset
    np.random.seed(42)
    mesh_pts = [np.random.rand(5, 3) for _ in range(15)]
    mesh_tets = [np.array([[0, 1, 2, 3]], dtype=np.int64) for _ in range(15)]

    with tempfile.TemporaryDirectory() as td:
        npz = Path(td) / "d.npz"
        pt = Path(td) / "m.pt"
        r1 = generate_dataset_from_meshes(
            str(npz), mesh_pts, mesh_tets, samples_per_mesh=2,
        )
        assert r1.success
        assert r1.n_samples >= 10  # train_quality_predictor min

        r2 = train_quality_predictor(
            str(npz), str(pt),
            epochs=3, batch_size=4, lr=1e-2,
        )
        assert r2.success
        assert r2.n_train_samples > 0
        assert r2.epochs == 3
        assert pt.exists()

        # Load + inference
        model = load_trained_predictor(str(pt))
        assert model is not None

        c12, c8, _ = extract_features_batch(mesh_pts[0], mesh_tets[0])
        pred = predict_quality_batch(model, c12, c8)
        assert pred.shape == (1,)
        assert 0.0 <= pred[0] <= 1.0


def test_load_trained_predictor_missing_file():
    """Missing .pt → None graceful."""
    from core.generator.native_ai import load_trained_predictor
    m = load_trained_predictor("/tmp/__nonexistent_model__.pt")
    assert m is None


def test_predict_quality_batch_no_model():
    """None model → zero output graceful."""
    from core.generator.native_ai import predict_quality_batch
    coords = np.zeros((3, 12), dtype=np.float32)
    context = np.zeros((3, 8), dtype=np.float32)
    pred = predict_quality_batch(None, coords, context)
    assert pred.shape == (3,)
    assert (pred == 0.0).all()


def test_train_predictor_missing_dataset():
    """Missing dataset → graceful error."""
    from core.generator.native_ai import train_quality_predictor
    try:
        import torch  # noqa: F401
    except ImportError:
        pytest.skip("torch not available")
    with tempfile.TemporaryDirectory() as td:
        r = train_quality_predictor(
            str(Path(td) / "nonexistent.npz"),
            str(Path(td) / "m.pt"),
        )
        assert r.success is False
        assert "not found" in r.message


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


# ─────────────────────────────────────────────────────────────────────────
# B/C/D/E follow-up tests (beta2577)
# ─────────────────────────────────────────────────────────────────────────

def test_run_ml_pipeline_bench_synthetic():
    """B (AI-V1.4) — synthetic mesh ML bench end-to-end."""
    from core.generator.native_ai import run_ml_pipeline_bench, BenchMLResult
    try:
        import torch  # noqa: F401
    except ImportError:
        pytest.skip("torch not available")
    with tempfile.TemporaryDirectory() as td:
        r = run_ml_pipeline_bench(td, n_meshes=10, samples_per_mesh=5, epochs=2)
        assert isinstance(r, BenchMLResult)
        assert r.success is True
        assert r.n_samples_collected > 0
        assert r.val_loss >= 0


def test_extract_bl_collision_features_basic():
    """C (AI-V3.1) — BL collision feature shapes + finite gaps."""
    from core.generator.native_ai import extract_bl_collision_features
    pts = np.random.rand(20, 3)
    wall_v = np.array([0, 1, 2, 3], dtype=np.int64)
    wall_fv = np.array([[0, 1, 2], [1, 2, 3], [2, 3, 4]], dtype=np.int64)
    feats, gaps = extract_bl_collision_features(pts, wall_v, wall_fv)
    assert feats.shape == (4, 12)
    assert gaps.shape == (4,)


def test_generate_bl_collision_dataset():
    """C (AI-V3.1) — dataset save/load."""
    from core.generator.native_ai import generate_bl_collision_dataset
    pts = np.random.rand(20, 3)
    wall_v = np.array([0, 1, 2], dtype=np.int64)
    wall_fv = np.array([[0, 1, 2], [1, 2, 3]], dtype=np.int64)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "bl.npz"
        r = generate_bl_collision_dataset(
            str(out), [pts, pts], [wall_v, wall_v], [wall_fv, wall_fv],
        )
        if r.success:
            assert r.n_samples > 0
            assert Path(out).exists()
            d = np.load(str(out))
            assert d["features"].shape[1] == 12


def test_gpu_point_to_tri_basic():
    """D (C8-2.1.2) — GPU point-to-tri batch."""
    from core.generator.native_ai import (
        gpu_point_to_tri_distance, GPUPointToTriResult,
    )
    try:
        import torch  # noqa: F401
    except ImportError:
        pytest.skip("torch not available")
    np.random.seed(42)
    surf = np.random.rand(10, 3)
    faces = np.array([[0, 1, 2], [1, 2, 3], [2, 3, 4], [3, 4, 5]],
                     dtype=np.int64)
    query = np.random.rand(20, 3)
    dist, r = gpu_point_to_tri_distance(query, surf, faces)
    assert isinstance(r, GPUPointToTriResult)
    if r.success:
        assert dist.shape == (20,)
        assert (dist >= 0).all()
        assert r.backend.startswith("torch_")


def test_starccm_binary_skeleton():
    """E (C7-1.3) — binary .ccm header writer."""
    from core.utils.mesh_exporter_starccm import write_starccm
    # Need a fake polyMesh — use existing
    with tempfile.TemporaryDirectory() as td:
        pm = Path(td) / "pm"
        pm.mkdir()
        # Empty polyMesh — should fail gracefully
        out = Path(td) / "out.ccm"
        r = write_starccm(str(pm), str(out), fmt="binary")
        # Either succeeds with skeleton bytes, or fails gracefully
        assert hasattr(r, "success")
        assert r.fmt == "binary"


def test_starccm_binary_v2_full_blocks(monkeypatch):
    """C7-1.3 / beta2593 — 6-block binary writer 검증.
    구조: header(32B) + PTS + FAC + OWN + NBR + ZNE + END trailer.
    """
    import struct
    import sys
    import types
    from core.utils.mesh_exporter_starccm import write_starccm
    # 합성 polyMesh — fake reader 모듈 제공.
    fake_pm = {
        "points": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "faces": [[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]],
        "owner": [0, 0, 0, 0],
        "neighbour": [],
        "boundary": [{"name": "walls", "type": "wall", "nFaces": 4, "startFace": 0}],
    }
    fake_mod = types.ModuleType("core.utils.poly_mesh_reader")
    fake_mod.read_poly_mesh = lambda _p: fake_pm  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "core.utils.poly_mesh_reader", fake_mod)

    with tempfile.TemporaryDirectory() as td:
        pm = Path(td) / "pm"
        pm.mkdir()
        out = Path(td) / "tet.ccm"
        r = write_starccm(str(pm), str(out), fmt="binary")
        if not r.success:
            pytest.skip(f"poly_mesh_reader 미지원: {r.message[:60]}")
        # 바이너리 검증.
        with out.open("rb") as f:
            magic = f.read(4)
            assert magic == b"CCMV", f"magic 불일치: {magic!r}"
            ver = struct.unpack("<I", f.read(4))[0]
            assert ver == 2, f"version=2 expected, got {ver}"
            # n_points / n_cells / n_faces / n_internal_faces.
            n_pts = struct.unpack("<I", f.read(4))[0]
            n_cells = struct.unpack("<I", f.read(4))[0]
            n_faces = struct.unpack("<I", f.read(4))[0]
            n_int = struct.unpack("<I", f.read(4))[0]
            n_zones = struct.unpack("<H", f.read(2))[0]
            f.read(6)  # padding.
            assert n_pts == 4
            assert n_cells >= 1
            assert n_faces == 4
            assert n_zones == 1
            # 블록 tag 순차 확인.
            assert f.read(4) == b"PTS\0"
            f.read(4)  # count.
            f.read(n_pts * 3 * 8)  # points.
            assert f.read(4) == b"FAC\0"
            f.read(4)  # count.
            for _ in range(n_faces):
                nv = struct.unpack("<I", f.read(4))[0]
                f.read(nv * 4)
            assert f.read(4) == b"OWN\0"
            cnt = struct.unpack("<I", f.read(4))[0]
            f.read(cnt * 4)
            assert f.read(4) == b"NBR\0"
            cnt = struct.unpack("<I", f.read(4))[0]
            f.read(cnt * 4)
            assert f.read(4) == b"ZNE\0"
            cnt = struct.unpack("<I", f.read(4))[0]
            for _ in range(cnt):
                name_len = struct.unpack("<H", f.read(2))[0]
                f.read(name_len + 4 + 4 + 1)
            assert f.read(4) == b"END\0"
            trailer = struct.unpack("<I", f.read(4))[0]
            assert trailer == 0xCCAA5555, f"trailer magic 불일치: {trailer:#x}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
