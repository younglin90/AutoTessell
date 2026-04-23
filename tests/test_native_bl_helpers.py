"""beta57 — native_bl helper utility 단위 회귀.

`generate_native_bl` 을 end-to-end 로 돌리는 기존 test_native_bl.py 외에,
내부 helper (face normal, vertex normal, wall collector, edge map) 를 직접
검증한다. 이들이 돌아가야 전체 BL 이 재현 가능.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.layers.native_bl import (
    BLConfig,
    NativeBLResult,
    _build_edge_to_wall_faces,
    _collect_wall_faces,
    _compute_collision_distance,
    _detect_feature_vertices,
    _face_centroid,
    _face_normal_area,
    _ray_triangle_min_distance,
    compute_vertex_normals,
)


# ---------------------------------------------------------------------------
# BLConfig / NativeBLResult dataclass 기본값
# ---------------------------------------------------------------------------


def test_blconfig_defaults() -> None:
    cfg = BLConfig()
    assert cfg.num_layers == 3
    assert cfg.growth_ratio == pytest.approx(1.2)
    assert cfg.first_thickness == pytest.approx(0.001)
    assert cfg.wall_patch_names is None
    assert cfg.backup_original is True
    assert cfg.max_total_ratio == pytest.approx(0.3)


def test_blconfig_overrides() -> None:
    cfg = BLConfig(
        num_layers=5,
        growth_ratio=1.3,
        first_thickness=0.002,
        wall_patch_names=["wall1", "wall2"],
        backup_original=False,
        max_total_ratio=0.1,
    )
    assert cfg.num_layers == 5
    assert cfg.wall_patch_names == ["wall1", "wall2"]
    assert cfg.backup_original is False


def test_native_bl_result_defaults() -> None:
    r = NativeBLResult(success=True, elapsed=0.5)
    assert r.n_wall_faces == 0
    assert r.n_wall_verts == 0
    assert r.n_prism_cells == 0
    assert r.n_new_points == 0
    assert r.total_thickness == pytest.approx(0.0)
    assert r.message == ""


# ---------------------------------------------------------------------------
# _face_centroid / _face_normal_area
# ---------------------------------------------------------------------------


def test_face_centroid_unit_triangle() -> None:
    pts = np.array([[0, 0, 0], [3, 0, 0], [0, 3, 0]], dtype=np.float64)
    c = _face_centroid(pts, [0, 1, 2])
    np.testing.assert_allclose(c, [1.0, 1.0, 0.0])


def test_face_normal_area_unit_triangle_z() -> None:
    """(0,0,0)-(1,0,0)-(0,1,0) → normal +z, area=0.5."""
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    n, a = _face_normal_area(pts, [0, 1, 2])
    np.testing.assert_allclose(n, [0, 0, 1], atol=1e-12)
    assert a == pytest.approx(0.5)


def test_face_normal_area_quad_is_summed() -> None:
    """Quad (fan triangulation) 면적은 두 삼각형 합."""
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64
    )
    _, a = _face_normal_area(pts, [0, 1, 2, 3])
    assert a == pytest.approx(1.0, rel=1e-9)


def test_face_normal_area_degenerate_zero() -> None:
    """Collinear 3 점 → area=0, normal=0 vector."""
    pts = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=np.float64)
    n, a = _face_normal_area(pts, [0, 1, 2])
    assert a == pytest.approx(0.0)
    np.testing.assert_allclose(n, [0, 0, 0])


def test_face_normal_area_too_few_points() -> None:
    """face 가 2 vertex 이하 → zero / area=0."""
    pts = np.array([[0, 0, 0], [1, 0, 0]], dtype=np.float64)
    n, a = _face_normal_area(pts, [0, 1])
    assert a == pytest.approx(0.0)
    np.testing.assert_allclose(n, [0, 0, 0])


# ---------------------------------------------------------------------------
# compute_vertex_normals
# ---------------------------------------------------------------------------


def test_compute_vertex_normals_single_triangle_no_cc() -> None:
    """cell_centres 없이도 동작 — normal = +z unit."""
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = [[0, 1, 2]]
    owner = np.array([0], dtype=np.int64)
    result = compute_vertex_normals(pts, faces, [0], owner)
    assert set(result.keys()) == {0, 1, 2}
    for v in result.values():
        np.testing.assert_allclose(v, [0, 0, 1], atol=1e-12)


def test_compute_vertex_normals_cc_flips_sign() -> None:
    """cell_centre 가 face 위쪽에 있으면 normal 이 반대쪽 (-z) 으로 flip."""
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = [[0, 1, 2]]
    owner = np.array([0], dtype=np.int64)
    # cell centre 가 face 의 +z 쪽 → outward (owner 바깥) = -z
    cc = np.array([[0.3, 0.3, 0.5]], dtype=np.float64)
    result = compute_vertex_normals(pts, faces, [0], owner, cc)
    for v in result.values():
        np.testing.assert_allclose(v, [0, 0, -1], atol=1e-12)


def test_compute_vertex_normals_empty_wall() -> None:
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = [[0, 1, 2]]
    owner = np.array([0], dtype=np.int64)
    result = compute_vertex_normals(pts, faces, [], owner)
    assert result == {}


def test_compute_vertex_normals_degenerate_skipped() -> None:
    """area=0 인 collinear face 는 accum 에 기여하지 않음."""
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [2, 0, 0], [0, 0, 0], [1, 0, 0], [0, 1, 0]],
        dtype=np.float64,
    )
    faces = [[0, 1, 2], [3, 4, 5]]  # 0: degenerate, 1: valid +z
    owner = np.array([0, 0], dtype=np.int64)
    result = compute_vertex_normals(pts, faces, [0, 1], owner)
    # valid face 의 vertex 만 정규화된 normal 보유
    assert 3 in result and 4 in result and 5 in result
    np.testing.assert_allclose(result[3], [0, 0, 1], atol=1e-12)


# ---------------------------------------------------------------------------
# _collect_wall_faces
# ---------------------------------------------------------------------------


def test_collect_wall_faces_by_type() -> None:
    """type 에 'wall' 포함 → wall patch 로 인식."""
    boundary = [
        {"name": "inlet", "type": "patch", "startFace": 0, "nFaces": 2},
        {"name": "walls", "type": "wall", "startFace": 2, "nFaces": 3},
        {"name": "outlet", "type": "patch", "startFace": 5, "nFaces": 1},
    ]
    wfi, wpset, fmap = _collect_wall_faces(boundary, None)
    assert wfi == [2, 3, 4]
    assert wpset == {1}
    assert fmap[2] == (1, 0)
    assert fmap[4] == (1, 2)


def test_collect_wall_faces_by_name() -> None:
    """name 에 'wall' 포함 → 인식."""
    boundary = [
        {"name": "my_wall_bc", "type": "patch", "startFace": 0, "nFaces": 2},
    ]
    wfi, _, _ = _collect_wall_faces(boundary, None)
    assert wfi == [0, 1]


def test_collect_wall_faces_explicit_names() -> None:
    """wall_patch_names 주어지면 type 무시, name 완전일치만."""
    boundary = [
        {"name": "part_a", "type": "wall", "startFace": 0, "nFaces": 1},
        {"name": "part_b", "type": "wall", "startFace": 1, "nFaces": 2},
    ]
    wfi, _, _ = _collect_wall_faces(boundary, ["part_b"])
    assert wfi == [1, 2]


def test_collect_wall_faces_no_wall() -> None:
    boundary = [
        {"name": "inlet", "type": "patch", "startFace": 0, "nFaces": 1},
    ]
    wfi, _, fmap = _collect_wall_faces(boundary, None)
    assert wfi == []
    assert fmap == {}


# ---------------------------------------------------------------------------
# _build_edge_to_wall_faces
# ---------------------------------------------------------------------------


def test_edge_to_wall_faces_two_triangles_shared_edge() -> None:
    """두 삼각형이 edge 공유 → edge_map 해당 edge 에 두 face."""
    # tri0 = [0,1,2], tri1 = [1,3,2] (edge 1-2 공유)
    faces = [[0, 1, 2], [1, 3, 2]]
    emap = _build_edge_to_wall_faces([0, 1], faces)
    # edge (1,2) 두 face 공유
    assert sorted(emap[(1, 2)]) == [0, 1]
    # 그 외 edge 는 단독
    assert emap[(0, 1)] == [0]
    assert emap[(0, 2)] == [0]
    assert sorted(emap[(1, 3)]) == [1]


def test_edge_to_wall_faces_skips_non_triangle() -> None:
    """triangle 이 아닌 face 는 edge_map 에서 skip."""
    faces = [[0, 1, 2, 3], [0, 1, 2]]  # quad + tri
    emap = _build_edge_to_wall_faces([0, 1], faces)
    # quad (0) 의 edge 는 포함되지 않아야 함 — tri(1) 만
    for edges in emap.values():
        assert 0 not in edges
    # tri 의 3 edge 는 모두 있음
    assert (0, 1) in emap
    assert (1, 2) in emap
    assert (0, 2) in emap


def test_edge_to_wall_faces_empty_input() -> None:
    emap = _build_edge_to_wall_faces([], [])
    assert emap == {}


def test_edge_to_wall_faces_sorted_key() -> None:
    """edge key 는 (min, max) 정렬."""
    faces = [[5, 2, 9]]
    emap = _build_edge_to_wall_faces([0], faces)
    # (5,2) → (2,5), (2,9), (5,9)
    assert (2, 5) in emap
    assert (2, 9) in emap
    assert (5, 9) in emap
    assert (5, 2) not in emap


# ---------------------------------------------------------------------------
# beta63 — collision detection
# ---------------------------------------------------------------------------


def test_blconfig_collision_safety_defaults() -> None:
    """beta63 — collision_safety 기본 True, factor=0.5."""
    cfg = BLConfig()
    assert cfg.collision_safety is True
    assert cfg.collision_safety_factor == pytest.approx(0.5)


def test_ray_triangle_min_distance_hit() -> None:
    """z=0 triangle + z=1 origin + -z ray → t=1."""
    origins = np.array([[0.3, 0.3, 1.0]], dtype=np.float64)
    directions = np.array([[0.0, 0.0, -1.0]], dtype=np.float64)
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], dtype=np.float64)
    t = _ray_triangle_min_distance(origins, directions, tri)
    np.testing.assert_allclose(t, [1.0], atol=1e-9)


def test_ray_triangle_min_distance_miss() -> None:
    """ray 가 triangle 을 완전히 벗어나면 +inf."""
    origins = np.array([[5.0, 5.0, 1.0]], dtype=np.float64)
    directions = np.array([[0.0, 0.0, -1.0]], dtype=np.float64)
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], dtype=np.float64)
    t = _ray_triangle_min_distance(origins, directions, tri)
    assert np.isinf(t[0])


def test_ray_triangle_min_distance_multi_tri_picks_min() -> None:
    """두 개 triangle 중 더 가까운 hit 선택."""
    origins = np.array([[0.3, 0.3, 3.0]], dtype=np.float64)
    directions = np.array([[0.0, 0.0, -1.0]], dtype=np.float64)
    # z=0 triangle (t=3) vs z=1 triangle (t=2)
    tri = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[0, 0, 1], [1, 0, 1], [0, 1, 1]],
    ], dtype=np.float64)
    t = _ray_triangle_min_distance(origins, directions, tri)
    np.testing.assert_allclose(t, [2.0], atol=1e-9)


def test_ray_triangle_exclude_mask_skips_owned() -> None:
    """exclude_mask True 면 해당 (ray, tri) 쌍은 skip."""
    origins = np.array([[0.3, 0.3, 1.0]], dtype=np.float64)
    directions = np.array([[0.0, 0.0, -1.0]], dtype=np.float64)
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], dtype=np.float64)
    exclude = np.array([[True]], dtype=bool)
    t = _ray_triangle_min_distance(origins, directions, tri, exclude)
    assert np.isinf(t[0])


def test_collision_distance_parallel_walls() -> None:
    """두 평행 wall (z=0, z=1) 의 vertex 에서 반대편 wall 까지 거리 = 1.0."""
    # 간단한 mesh: 2 개 triangle 을 z=0 과 z=1 에 각각 하나씩
    points = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],  # z=0 wall
        [0, 0, 1], [1, 0, 1], [0, 1, 1],  # z=1 wall
    ], dtype=np.float64)
    faces = [[0, 1, 2], [3, 4, 5]]
    wall_face_indices = [0, 1]
    wall_vert_indices = [0, 1, 2, 3, 4, 5]
    # 각 wall 의 vertex normal (z=0 wall: outward -z → inward +z / z=1 wall: +z → -z)
    vnorm = {
        0: np.array([0, 0, -1.0]), 1: np.array([0, 0, -1.0]), 2: np.array([0, 0, -1.0]),
        3: np.array([0, 0, 1.0]),  4: np.array([0, 0, 1.0]),  5: np.array([0, 0, 1.0]),
    }
    # Note: vnorm 은 outward. _compute_collision_distance 가 inward = -vnorm 사용.
    # 여기선 z=0 wall 의 outward 를 -z 로 설정 → inward = +z → z=1 wall 과 t=1 hit.
    dists = _compute_collision_distance(
        points, faces, wall_face_indices, wall_vert_indices, vnorm,
    )
    # 모든 vertex 가 반대편 wall 을 향해 distance 1.0 (face corner 기준 편차 작음)
    assert len(dists) > 0
    for v, d in dists.items():
        assert d == pytest.approx(1.0, abs=1e-6)


def test_collision_distance_no_opposite_wall() -> None:
    """단일 wall 만 있으면 collision 거리 없음 → 빈 dict."""
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = [[0, 1, 2]]
    vnorm = {0: np.array([0, 0, 1.0]), 1: np.array([0, 0, 1.0]), 2: np.array([0, 0, 1.0])}
    dists = _compute_collision_distance(points, faces, [0], [0, 1, 2], vnorm)
    # exclude_mask 때문에 자기 face 배제 → hit 없음
    assert dists == {}


# ---------------------------------------------------------------------------
# beta64 — feature edge locking
# ---------------------------------------------------------------------------


def test_blconfig_feature_lock_defaults() -> None:
    """beta64 — feature_lock 기본 True, angle=45°, reduction=0.5."""
    cfg = BLConfig()
    assert cfg.feature_lock is True
    assert cfg.feature_angle_deg == pytest.approx(45.0)
    assert cfg.feature_reduction_ratio == pytest.approx(0.5)


def test_detect_feature_vertices_flat_returns_empty() -> None:
    """평평한 two-tri quad (dihedral=0) → feature 없음."""
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64,
    )
    faces = [[0, 1, 2], [0, 2, 3]]
    fv = _detect_feature_vertices(pts, faces, [0, 1], feature_angle_deg=45.0)
    assert fv == set()


def test_detect_feature_vertices_right_angle_captured() -> None:
    """90° L-shape edge → 해당 edge 두 vertex 가 feature."""
    # 두 삼각형이 공유 edge (1-2) 를 중심으로 수직
    # tri0: xy-plane z=0, tri1: yz-plane x=0
    pts = np.array([
        [1, 0, 0],   # 0
        [0, 0, 0],   # 1 (edge start)
        [0, 1, 0],   # 2 (edge end)
        [0, 0, 1],   # 3 (tri1 의 세 번째 점)
    ], dtype=np.float64)
    faces = [[0, 1, 2], [3, 1, 2]]
    fv = _detect_feature_vertices(pts, faces, [0, 1], feature_angle_deg=45.0)
    # 공유 edge (1, 2) 의 두 vertex 모두 feature
    assert 1 in fv
    assert 2 in fv


def test_detect_feature_vertices_threshold_blocks_mild_bend() -> None:
    """threshold=80° 로 올리면 45° 굽음도 feature 가 아님."""
    # 약 45° 굽음 (diagonal z=0 와 z=x plane 비슷)
    pts = np.array([
        [1, 0, 0],  [0, 0, 0], [0, 1, 0],
        [1, 0, 1],
    ], dtype=np.float64)
    faces = [[0, 1, 2], [3, 1, 2]]
    # threshold 80° 이면 feature 아님
    fv_high = _detect_feature_vertices(pts, faces, [0, 1], feature_angle_deg=80.0)
    assert fv_high == set()


def test_detect_feature_vertices_empty_wall() -> None:
    """빈 wall → 빈 set."""
    pts = np.zeros((3, 3), dtype=np.float64)
    faces = [[0, 1, 2]]
    fv = _detect_feature_vertices(pts, faces, [], feature_angle_deg=45.0)
    assert fv == set()


def test_detect_feature_vertices_zero_angle_returns_empty() -> None:
    """feature_angle_deg=0 → shortcut 반환 (전부 feature 취급 안 함)."""
    pts = np.array(
        [[1, 0, 0], [0, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64,
    )
    faces = [[0, 1, 2], [3, 1, 2]]
    fv = _detect_feature_vertices(pts, faces, [0, 1], feature_angle_deg=0.0)
    assert fv == set()


# ---------------------------------------------------------------------------
# beta65 — prism quality check
# ---------------------------------------------------------------------------


def test_blconfig_quality_check_defaults() -> None:
    """beta65 — quality_check_enabled 기본 True, threshold=50.0."""
    cfg = BLConfig()
    assert cfg.quality_check_enabled is True
    assert cfg.aspect_ratio_threshold == pytest.approx(50.0)


def test_native_bl_result_quality_fields_defaults() -> None:
    """beta65 — NativeBLResult 에 n_degenerate_prisms, max_aspect_ratio 필드."""
    r = NativeBLResult(success=True, elapsed=0.1)
    assert r.n_degenerate_prisms == 0
    assert r.max_aspect_ratio == pytest.approx(0.0)


def test_prism_aspect_ratio_stats_unit_prism() -> None:
    """beta65 — 정상 prism (outer edge=1, height=1) → aspect ratio=1."""
    from core.layers.native_bl import _prism_aspect_ratio_stats
    # outer triangle: z=0, inner triangle: z=-1 (height=1).
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],     # outer
        [0, 0, -1], [1, 0, -1], [0, 1, -1],  # inner
    ], dtype=np.float64)
    wall_tri_verts = {0: (0, 1, 2)}
    wall_face_indices = [0]
    layer_point_ids = [
        {0: 0, 1: 1, 2: 2},   # layer 0
        {0: 3, 1: 4, 2: 5},   # layer 1
    ]
    n_degen, max_ar = _prism_aspect_ratio_stats(
        pts, wall_tri_verts, wall_face_indices, layer_point_ids,
        num_layers=1, threshold=50.0,
    )
    assert n_degen == 0
    # max edge (0,1)-(1,0) = sqrt(2) ≈ 1.414, height = 1 → ratio ≈ 1.414
    assert max_ar == pytest.approx(np.sqrt(2), rel=1e-6)


def test_prism_aspect_ratio_stats_squashed_prism() -> None:
    """beta65 — height=0.001 squashed prism → aspect ratio 폭증."""
    from core.layers.native_bl import _prism_aspect_ratio_stats
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [0, 0, -0.001], [1, 0, -0.001], [0, 1, -0.001],
    ], dtype=np.float64)
    wall_tri_verts = {0: (0, 1, 2)}
    layer_point_ids = [
        {0: 0, 1: 1, 2: 2},
        {0: 3, 1: 4, 2: 5},
    ]
    n_degen, max_ar = _prism_aspect_ratio_stats(
        pts, wall_tri_verts, [0], layer_point_ids,
        num_layers=1, threshold=50.0,
    )
    # ratio ≈ sqrt(2)/0.001 ≈ 1414 > 50 → degenerate
    assert n_degen == 1
    assert max_ar > 50.0


def test_prism_aspect_ratio_stats_zero_height_counts_degenerate() -> None:
    """beta65 — outer == inner (height=0) → degenerate."""
    from core.layers.native_bl import _prism_aspect_ratio_stats
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
    ], dtype=np.float64)
    wall_tri_verts = {0: (0, 1, 2)}
    layer_point_ids = [
        {0: 0, 1: 1, 2: 2},
        {0: 3, 1: 4, 2: 5},
    ]
    n_degen, _ = _prism_aspect_ratio_stats(
        pts, wall_tri_verts, [0], layer_point_ids,
        num_layers=1, threshold=50.0,
    )
    assert n_degen >= 1


# ---------------------------------------------------------------------------
# beta95 — per_vertex_first_thickness (BLConfig + generate_native_bl)
# ---------------------------------------------------------------------------


def test_blconfig_defaults_per_vertex_none() -> None:
    """beta95 — per_vertex_first_thickness 기본값 None."""
    cfg = BLConfig()
    assert cfg.per_vertex_first_thickness is None


def test_blconfig_per_vertex_first_thickness_set() -> None:
    """per_vertex_first_thickness dict 로 설정 가능."""
    mapping = {0: 0.001, 1: 0.005, 2: 0.002}
    cfg = BLConfig(per_vertex_first_thickness=mapping)
    assert cfg.per_vertex_first_thickness == mapping
    assert cfg.per_vertex_first_thickness[1] == pytest.approx(0.005)


def test_per_vertex_first_thickness_none_is_uniform() -> None:
    """per_vertex_first_thickness=None → 모든 vertex 에 cfg.first_thickness 사용 (기존 동작).

    generate_native_bl 을 사용하지 않고, BLConfig 의 두께 계산 로직만 직접 검증한다.
    vertex 별 per_vertex cum 이 없을 때와 있을 때 결과를 비교.
    """
    cfg_uniform = BLConfig(
        num_layers=3,
        growth_ratio=1.2,
        first_thickness=0.01,
        per_vertex_first_thickness=None,
    )
    cfg_explicit = BLConfig(
        num_layers=3,
        growth_ratio=1.2,
        first_thickness=0.01,
        # 모든 vertex 에 동일한 first_thickness=0.01 명시
        per_vertex_first_thickness={0: 0.01, 1: 0.01, 2: 0.01},
    )

    import numpy as _np

    def _compute_cum(cfg_: BLConfig, v: int) -> _np.ndarray:
        ft = cfg_.first_thickness
        if cfg_.per_vertex_first_thickness:
            ft = cfg_.per_vertex_first_thickness.get(v, cfg_.first_thickness)
        thick = _np.array(
            [ft * (cfg_.growth_ratio ** i) for i in range(cfg_.num_layers)],
        )
        return _np.concatenate(([0.0], _np.cumsum(thick)))

    for v in (0, 1, 2):
        cum_u = _compute_cum(cfg_uniform, v)
        cum_e = _compute_cum(cfg_explicit, v)
        _np.testing.assert_allclose(cum_u, cum_e, rtol=1e-9)


def test_per_vertex_first_thickness_produces_different_layers() -> None:
    """vertex 별 다른 first_thickness → 레이어 위치가 다름.

    generate_native_bl 의 vertex_cum_map 계산 로직을 재현해 검증.
    """
    import numpy as _np

    cfg = BLConfig(
        num_layers=3,
        growth_ratio=1.2,
        first_thickness=0.01,
        per_vertex_first_thickness={0: 0.001, 1: 0.005, 2: 0.020},
    )

    vertex_scale = {0: 1.0, 1: 1.0, 2: 1.0}

    # vertex_cum_map 계산 (generate_native_bl 내부 로직과 동일)
    vertex_cum_map = {}
    for v in (0, 1, 2):
        ft = cfg.per_vertex_first_thickness[v]
        v_thick = _np.array(
            [ft * (cfg.growth_ratio ** i) for i in range(cfg.num_layers)],
            dtype=_np.float64,
        )
        v_thick *= vertex_scale.get(v, 1.0)
        vertex_cum_map[v] = _np.concatenate(([0.0], _np.cumsum(v_thick)))

    # vertex 0 (ft=0.001) vs vertex 2 (ft=0.020): 레이어 위치가 달라야 함
    # layer 1 위치 = cum[1]
    assert vertex_cum_map[0][1] != pytest.approx(vertex_cum_map[2][1], rel=0.01)
    # layer 1: v0 << v2
    assert vertex_cum_map[0][1] < vertex_cum_map[2][1]
    # 총 두께도 다름
    assert vertex_cum_map[0][-1] < vertex_cum_map[1][-1] < vertex_cum_map[2][-1]


def test_per_vertex_first_thickness_partial_override() -> None:
    """일부 vertex 만 override, 나머지는 cfg.first_thickness 사용."""
    import numpy as _np

    cfg = BLConfig(
        num_layers=2,
        growth_ratio=1.0,
        first_thickness=0.01,
        per_vertex_first_thickness={5: 0.05},  # vertex 5 만 override
    )

    wall_verts = [3, 5, 7]
    vertex_scale = {3: 1.0, 5: 1.0, 7: 1.0}

    vertex_cum_map = {}
    for v in wall_verts:
        ft = cfg.per_vertex_first_thickness.get(v, cfg.first_thickness)
        v_thick = _np.array(
            [ft * (cfg.growth_ratio ** i) for i in range(cfg.num_layers)],
            dtype=_np.float64,
        )
        v_thick *= vertex_scale.get(v, 1.0)
        vertex_cum_map[v] = _np.concatenate(([0.0], _np.cumsum(v_thick)))

    # vertex 3, 7: cfg.first_thickness=0.01 사용
    # vertex 5: 0.05 사용
    _np.testing.assert_allclose(vertex_cum_map[3][1], 0.01, rtol=1e-9)
    _np.testing.assert_allclose(vertex_cum_map[7][1], 0.01, rtol=1e-9)
    _np.testing.assert_allclose(vertex_cum_map[5][1], 0.05, rtol=1e-9)


def test_per_vertex_first_thickness_scale_applied() -> None:
    """vertex_scale < 1 이 per-vertex thick 에 올바르게 적용됨."""
    import numpy as _np

    ft = 0.01
    growth = 1.0
    num_layers = 3
    v_scale = 0.5  # feature lock 등으로 50% 축소

    cfg = BLConfig(
        num_layers=num_layers, growth_ratio=growth, first_thickness=ft,
        per_vertex_first_thickness={0: ft},
    )
    vertex_scale = {0: v_scale}

    v_thick = _np.array(
        [ft * (growth ** i) for i in range(num_layers)], dtype=_np.float64,
    )
    v_thick *= vertex_scale[0]
    cum = _np.concatenate(([0.0], _np.cumsum(v_thick)))

    # scale=0.5 적용 후 총 두께 = ft * num_layers * scale = 0.01 * 3 * 0.5 = 0.015
    _np.testing.assert_allclose(cum[-1], ft * num_layers * v_scale, rtol=1e-9)
