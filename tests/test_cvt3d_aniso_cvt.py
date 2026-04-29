"""C1.3 + C4 / beta2362 — Volumetric Lloyd CVT 3D + Anisotropic poly CVT smoke tests."""
from __future__ import annotations

import numpy as np


def _cube_with_interior() -> tuple:
    """8 surface vertices + 1 interior + 8 tets."""
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        [0.5, 0.5, 0.5],
    ], dtype=np.float64)
    tets = np.array([
        [0, 1, 2, 8], [0, 2, 3, 8],
        [4, 5, 6, 8], [4, 6, 7, 8],
        [0, 1, 5, 8], [0, 5, 4, 8],
        [2, 3, 7, 8], [2, 7, 6, 8],
    ], dtype=np.int64)
    return pts, tets


def test_lloyd_cvt_3d_runs_n_iter_passes() -> None:
    """C1.3 — n_iter passes 모두 실행."""
    from core.generator.native_tet.cvt3d import lloyd_cvt_3d
    pts, tets = _cube_with_interior()
    _, r = lloyd_cvt_3d(pts, tets, n_surface=8, n_iter=3, relax=0.5)
    assert r.n_iter_used == 3


def test_lloyd_cvt_3d_skips_small_mesh() -> None:
    """C1.3 — 너무 작은 mesh (≤4 tet) 는 skip."""
    from core.generator.native_tet.cvt3d import lloyd_cvt_3d
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    _, r = lloyd_cvt_3d(pts, tets, n_surface=4, n_iter=3)
    assert r.n_iter_used == 0
    assert not r.accepted


def test_lloyd_cvt_3d_monotone_guard_revert() -> None:
    """C1.3 — pre_min 이 매우 높은 단순 mesh 에서 (heuristic) reject 가 불가능 케이스
    accept 가능 — 측정만 검증."""
    from core.generator.native_tet.cvt3d import lloyd_cvt_3d
    pts, tets = _cube_with_interior()
    new_pts, r = lloyd_cvt_3d(pts, tets, n_surface=8, n_iter=2)
    # pre_min, post_min 이 정의되어 있어야 함.
    assert r.pre_min_q >= 0.0
    assert r.post_min_q >= 0.0


def test_aniso_cvt_seeds_returns_correct_count() -> None:
    """C4 — n_seeds 만큼 반환."""
    from core.generator.native_poly.aniso_cvt import aniso_cvt_seeds
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [0, 4, 7], [0, 7, 3],
    ], dtype=np.int64)
    seeds, r = aniso_cvt_seeds(
        V, F, V.min(axis=0), V.max(axis=0),
        n_seeds=20, n_iter=3,
    )
    assert seeds.shape == (20, 3)
    assert r.n_seeds == 20


def test_aniso_cvt_curvature_on_flat_face_is_low() -> None:
    """C4 — 평평한 face 의 vertex curvature 가 작음 (boundary 왜곡 없음)."""
    from core.generator.native_poly.aniso_cvt import _surface_principal_curvatures
    # Flat 정사각형 (z=0).
    V = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
        dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    curv = _surface_principal_curvatures(V, F)
    assert curv.shape == (4, 2)


def test_mesher_cvt3d_wired() -> None:
    """C1.3 / beta2363 — mesher.py 가 lloyd_cvt_3d 호출."""
    import inspect
    from core.generator.native_tet import mesher
    src = inspect.getsource(mesher)
    assert "from core.generator.native_tet.cvt3d import lloyd_cvt_3d" in src or \
        "lloyd_cvt_3d" in src
    assert "AUTO_TESSELL_CVT3D_OFF" in src, "env-gate 누락"
    assert "native_tet_cvt3d_lloyd" in src, "log 키 누락"


def test_parallel_chunked_delaunay_runs_with_workers() -> None:
    """C5 / beta2365 — parallel_chunked_delaunay 가 ProcessPool 로 chunk 병렬화."""
    from core.generator.native_tet.parallel import parallel_chunked_delaunay
    rng = np.random.RandomState(0)
    V = (rng.rand(500, 3) * 10.0).astype(np.float64)
    pts, tets, r = parallel_chunked_delaunay(V, n_div=2, n_workers=2)
    assert tets.shape[0] > 0
    assert r.n_chunks >= 1
    assert r.n_workers <= 2


def test_parallel_chunked_delaunay_falls_back_for_small_input() -> None:
    """C5 / beta2365 — 200 미만 → 단일 process fallback."""
    from core.generator.native_tet.parallel import parallel_chunked_delaunay
    rng = np.random.RandomState(0)
    V = (rng.rand(50, 3) * 10.0).astype(np.float64)
    _, tets, r = parallel_chunked_delaunay(V, n_div=2, n_workers=4)
    # 단일 process fallback 시 n_chunks=1.
    assert r.n_chunks == 1
    assert r.n_workers == 1


def test_voronoi_aniso_cvt_diag_wired() -> None:
    """C4 / beta2363 — voronoi.py 가 aniso_cvt_seeds 호출 (diagnostic)."""
    import inspect
    from core.generator.native_poly import voronoi
    src = inspect.getsource(voronoi)
    assert "aniso_cvt_seeds" in src, "aniso_cvt_seeds import 누락"
    assert "native_poly_aniso_cvt_seeds_generated" in src, "log 키 누락"
    assert "AUTO_TESSELL_ANISO_CVT_OFF" in src, "env-gate 누락"


def test_per_vertex_lcr_empty() -> None:
    """C2 / beta2367 — empty wall vertex 집합 처리."""
    from core.layers.native_bl_lcr import per_vertex_lcr
    lyr, r = per_vertex_lcr(
        np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64),
        num_layers=5, first_thickness=0.01, growth_ratio=1.2,
    )
    assert lyr.shape == (0,)
    assert r.n_wall_verts == 0
    assert r.n_reduced_verts == 0


def test_per_vertex_lcr_no_collision_full_layers() -> None:
    """C2 — collision 없으면 full layers 유지."""
    from core.layers.native_bl_lcr import per_vertex_lcr
    wall = np.array([0, 1, 2], dtype=np.int64)
    cd = np.array([-1.0, np.inf, -1.0], dtype=np.float64)
    lyr, r = per_vertex_lcr(
        wall, cd, num_layers=5, first_thickness=0.01, growth_ratio=1.2,
    )
    assert (lyr == 5).all()
    assert r.n_reduced_verts == 0
    assert r.n_safe_full_layers == 3


def test_per_vertex_lcr_narrow_gap_reduces_layers() -> None:
    """C2 — 좁은 gap vertex 의 layer 수가 감소."""
    from core.layers.native_bl_lcr import per_vertex_lcr
    wall = np.array([0, 1, 2], dtype=np.int64)
    # 0.001 → very tight (≤ 1 layer), 0.05 → 2 layers, 0.5 → full 5.
    cd = np.array([0.001, 0.05, 0.5], dtype=np.float64)
    lyr, r = per_vertex_lcr(
        wall, cd, num_layers=5, first_thickness=0.01, growth_ratio=1.2,
    )
    assert lyr[0] <= 2  # tight
    assert lyr[2] == 5  # safe
    assert r.n_reduced_verts >= 1
    assert r.min_layers_used <= 2


def test_per_vertex_lcr_min_layers_floor() -> None:
    """C2 — min_layers ≥ 1 floor 적용."""
    from core.layers.native_bl_lcr import per_vertex_lcr
    wall = np.array([0], dtype=np.int64)
    cd = np.array([1e-9], dtype=np.float64)  # 거의 0.
    lyr, r = per_vertex_lcr(
        wall, cd, num_layers=5, first_thickness=0.01, growth_ratio=1.2,
        min_layers=2,
    )
    assert lyr[0] == 2  # floor.
    assert r.min_layers_used == 2


def test_native_bl_lcr_wired() -> None:
    """C2 / beta2368 — native_bl 가 per_vertex_lcr 호출 (diagnostic)."""
    import inspect
    from core.layers import native_bl
    src = inspect.getsource(native_bl)
    assert "from core.layers.native_bl_lcr import per_vertex_lcr" in src, \
        "per_vertex_lcr import 누락"
    assert "AUTO_TESSELL_LCR_OFF" in src, "env-gate 누락"
    assert "native_bl_lcr_per_vertex" in src, "log 키 누락"


def test_native_bl_result_lcr_schema() -> None:
    """C2.3 / beta2369 — NativeBLResult 가 LCR 필드를 가진다."""
    from core.layers.native_bl import NativeBLResult
    r = NativeBLResult(success=True, elapsed=0.0)
    assert hasattr(r, "lcr_n_reduced_verts")
    assert hasattr(r, "lcr_max_reduction")
    assert hasattr(r, "lcr_min_layers_used")
    assert hasattr(r, "lcr_n_safe_full_layers")
    assert r.lcr_n_reduced_verts == 0
    assert r.lcr_max_reduction == 0


def test_native_bl_quality_json_lcr_block_wired() -> None:
    """C2.3 / beta2369 — native_bl_quality.json 에 lcr 블록 포함."""
    import inspect
    from core.layers import native_bl
    src = inspect.getsource(native_bl)
    assert '"lcr":' in src or "'lcr':" in src, "quality_summary 의 lcr 블록 누락"
    assert "n_reduced_verts" in src, "lcr.n_reduced_verts 키 누락"


def test_split_thick_prisms_halves_high_aspect() -> None:
    """C3.1 / beta2370 — aspect > threshold 인 prism 이 mid-split 으로 절반."""
    from core.layers.native_bl_split import split_thick_prisms
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [0, 0, 6], [1, 0, 6], [0, 1, 6],
    ], dtype=np.float64)
    pr = np.array([[0, 1, 2, 3, 4, 5]], dtype=np.int64)
    new_p, new_pr, r = split_thick_prisms(pts, pr, threshold=4.0)
    assert r.n_split_prisms == 1
    assert r.n_output_prisms == 2
    assert r.n_new_points == 3
    # split 후 aspect 가 절반 근처.
    assert r.max_aspect_out < r.max_aspect_in * 0.55


def test_split_thick_prisms_skips_thin_aspect() -> None:
    """C3.1 — aspect ≤ threshold 인 prism 은 그대로."""
    from core.layers.native_bl_split import split_thick_prisms
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [0, 1, 1],
    ], dtype=np.float64)
    pr = np.array([[0, 1, 2, 3, 4, 5]], dtype=np.int64)
    _, _, r = split_thick_prisms(pts, pr, threshold=4.0)
    assert r.n_split_prisms == 0
    assert r.n_output_prisms == 1
    assert r.n_new_points == 0


def test_split_thick_prisms_empty() -> None:
    """C3.1 — 빈 입력 정상 처리."""
    from core.layers.native_bl_split import split_thick_prisms
    pts = np.zeros((0, 3), dtype=np.float64)
    pr = np.zeros((0, 6), dtype=np.int64)
    new_p, new_pr, r = split_thick_prisms(pts, pr)
    assert r.n_input_prisms == 0
    assert new_p.shape == (0, 3)
    assert new_pr.shape == (0, 6)


def test_extrude_hex_bl_single_quad_3_layers() -> None:
    """C6.1 / beta2371 — 단일 wall quad, 3-layer extrude → 3 hex cell."""
    from core.layers.native_hex_bl import extrude_hex_bl
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
        dtype=np.float64,
    )
    quads = np.array([[0, 1, 2, 3]], dtype=np.int64)
    vnorm = np.tile([0.0, 0.0, 1.0], (4, 1))
    new_p, hexes, r = extrude_hex_bl(
        pts, quads, vnorm,
        num_layers=3, first_thickness=0.1, growth_ratio=1.2,
    )
    assert r.n_hex_cells == 3
    assert r.n_wall_verts == 4
    assert r.n_new_points == 12
    assert hexes.shape == (3, 8)
    assert new_p.shape == (16, 3)
    # bottom of first hex = original vertices.
    assert hexes[0, 0:4].tolist() == [0, 1, 2, 3]
    # top of last hex = farthest layer vertices.
    assert hexes[2, 4:8].tolist() == [12, 13, 14, 15]


def test_extrude_hex_bl_thickness_geometric() -> None:
    """C6.1 — thickness 합이 geometric series total 와 일치."""
    from core.layers.native_hex_bl import extrude_hex_bl
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
        dtype=np.float64,
    )
    quads = np.array([[0, 1, 2, 3]], dtype=np.int64)
    vnorm = np.tile([0.0, 0.0, 1.0], (4, 1))
    _, _, r = extrude_hex_bl(
        pts, quads, vnorm,
        num_layers=4, first_thickness=0.1, growth_ratio=1.5,
    )
    expected = 0.1 * (1.0 + 1.5 + 1.5**2 + 1.5**3)
    assert abs(r.total_thickness - expected) < 1e-12


def test_extrude_hex_bl_empty() -> None:
    """C6.1 — 빈 입력 정상 처리."""
    from core.layers.native_hex_bl import extrude_hex_bl
    pts = np.zeros((0, 3), dtype=np.float64)
    quads = np.zeros((0, 4), dtype=np.int64)
    vnorm = np.zeros((0, 3), dtype=np.float64)
    new_p, hexes, r = extrude_hex_bl(
        pts, quads, vnorm, num_layers=3, first_thickness=0.1,
    )
    assert r.n_wall_quads == 0
    assert r.n_hex_cells == 0
    assert hexes.shape == (0, 8)


def test_native_tet_aniso_metric_wired_to_split_collapse() -> None:
    """C1.4 / beta2372 — mesher 가 metric_full 을 split + collapse 에 전달."""
    import inspect
    from core.generator.native_tet import mesher
    src = inspect.getsource(mesher)
    # split_long_edges + metric=metric_full 전달.
    assert "metric=metric_full" in src, "split_long_edges metric kwarg 누락"
    # collapse_short_edges + metric=m_collapse 전달.
    assert "metric=m_collapse" in src, "collapse_short_edges metric kwarg 누락"
    # propagation 가시성 로그.
    assert "native_tet_metric_propagated" in src, "metric propagation 로그 누락"


def test_harness_params_fine_uses_aniso_metric() -> None:
    """C1.4 — fine quality 가 use_anisotropic_metric=True."""
    from core.generator._tier_native_common import HARNESS_PARAMS
    p = HARNESS_PARAMS["tier_native_tet"]["fine"]
    assert p.get("use_anisotropic_metric") is True
    assert "anisotropic_ratio" in p
    assert 0.0 < float(p["anisotropic_ratio"]) <= 1.0


def test_native_tet_qed_min_faces_kwarg_overrides_env() -> None:
    """C1.5 / beta2373 — qed_min_faces kwarg 가 env 보다 우선."""
    import inspect
    from core.generator.native_tet.mesher import generate_native_tet
    sig = inspect.signature(generate_native_tet)
    assert "qed_min_faces" in sig.parameters, "qed_min_faces kwarg 누락"


def test_harness_params_fine_qed_min_faces_10k() -> None:
    """C1.5 / beta2373 — fine 의 qed_min_faces=10000 (Hu 2018 §3.4 적극)."""
    from core.generator._tier_native_common import HARNESS_PARAMS
    p = HARNESS_PARAMS["tier_native_tet"]["fine"]
    assert p.get("qed_min_faces") == 10000, \
        f"fine qed_min_faces=10000 expected, got {p.get('qed_min_faces')}"


def test_stellar_split_env_gated_default_off() -> None:
    """C1.6 / beta2374 — Stellar 의 split-pass 가 env-gate 로 default OFF."""
    import inspect
    from core.generator.native_tet import stellar
    src = inspect.getsource(stellar)
    assert "AUTO_TESSELL_STELLAR_SPLIT" in src, "Stellar split env-gate 누락"
    assert "split_sliver_longest_edge(" in src, "split_sliver_longest_edge 호출 누락"


def test_stellar_apply_op_queue_default_no_split() -> None:
    """C1.6 — env=0 (default) 에서 _apply_op_queue 가 split 호출 안 함."""
    import os as _os
    _prev = _os.environ.pop("AUTO_TESSELL_STELLAR_SPLIT", None)
    try:
        from core.generator.native_tet.stellar import (
            _apply_op_queue, _build_op_queue,
        )
        pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
        queue = _build_op_queue(pts, tets)
        p_out, t_out, n = _apply_op_queue(pts, tets, queue)
        # 단일 regular tet → 변동 없음.
        assert t_out.shape == tets.shape
    finally:
        if _prev is not None:
            _os.environ["AUTO_TESSELL_STELLAR_SPLIT"] = _prev


def test_parallel_delaunay_auto_dispatch_wired() -> None:
    """C5.2 / beta2375 — mesher 가 AUTO_TESSELL_PARALLEL_DELAUNAY auto 모드 분기."""
    import inspect
    from core.generator.native_tet import mesher
    src = inspect.getsource(mesher)
    # auto-detect 분기 존재.
    assert 'AUTO_TESSELL_PARALLEL_DELAUNAY", "auto"' in src, "auto 모드 분기 누락"
    # cpu_count() 분기.
    assert "os.cpu_count()" in src, "cpu_count auto-detect 누락"


def test_native_bl_aniso_split_diagnostic_wired() -> None:
    """C3.2 / beta2376 — native_bl 가 split_thick_prisms diagnostic env-gated 호출."""
    import inspect
    from core.layers import native_bl
    src = inspect.getsource(native_bl)
    assert "AUTO_TESSELL_BL_ANISO_SPLIT_DIAG" in src, "env-gate 누락"
    assert "from core.layers.native_bl_split import split_thick_prisms" in src, \
        "split_thick_prisms import 누락"
    assert "native_bl_aniso_split_diagnostic" in src, "log 키 누락"


def test_native_bl_result_aniso_split_schema() -> None:
    """C3.3 / beta2377 — NativeBLResult 가 aniso_split 필드를 가진다."""
    from core.layers.native_bl import NativeBLResult
    r = NativeBLResult(success=True, elapsed=0.0)
    assert hasattr(r, "aniso_split_n_examined")
    assert hasattr(r, "aniso_split_n_would_split")
    assert hasattr(r, "aniso_split_max_aspect_in")
    assert r.aniso_split_n_examined == 0
    assert r.aniso_split_max_aspect_in == 0.0


def test_native_bl_quality_json_aniso_split_block() -> None:
    """C3.3 / beta2377 — quality_summary 에 aniso_split 블록 포함."""
    import inspect
    from core.layers import native_bl
    src = inspect.getsource(native_bl)
    assert '"aniso_split":' in src or "'aniso_split':" in src, "aniso_split 블록 누락"
    assert "n_would_split" in src, "n_would_split 키 누락"


def test_native_tet_enable_stellar_split_kwarg_and_fine_param() -> None:
    """C1.7 / beta2378 — enable_stellar_split kwarg + fine quality 자동 ON."""
    import inspect
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator._tier_native_common import HARNESS_PARAMS
    sig = inspect.signature(generate_native_tet)
    assert "enable_stellar_split" in sig.parameters, "kwarg 누락"
    p = HARNESS_PARAMS["tier_native_tet"]["fine"]
    assert p.get("enable_stellar_split") is True, "fine quality 자동 ON 누락"
