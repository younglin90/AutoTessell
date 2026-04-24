"""Phase A 모듈 단위 + 통합 테스트 (beta104 TetWild-lite 1 단계)."""
from __future__ import annotations

import numpy as np
import pytest


# ======================================================================
# Unit — features.detect_features
# ======================================================================


def test_detect_features_cube_has_12_edges() -> None:
    """단위 큐브 6 face 12 edge 모두 dihedral 90° (fold 90°) 이므로
    feature_angle=30° 설정 시 feature edge ≥ 12."""
    from core.generator.native_tet.features import detect_features
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    info = detect_features(V, F, feature_angle_deg=30.0)
    # cube 는 feature edge 정확히 12 개 (6 face × 4 edge / 2 공유).
    assert info.feature_edges.shape[0] == 12
    # corner 는 8 (각 꼭짓점에 3 feature edge 집합).
    assert info.corner_vertices.shape[0] == 8
    # locked vertex 는 cube 의 8 꼭짓점 전부.
    assert info.locked_vertices.shape[0] == 8


def test_detect_features_sphere_has_few() -> None:
    """sphere 는 smooth 하므로 feature edge 거의 없음."""
    from core.generator.native_tet.features import detect_features
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    info = detect_features(V, F, feature_angle_deg=30.0)
    # icosphere 는 dihedral > 150° — feature edge 0 근처.
    assert info.feature_edges.shape[0] <= 5


# ======================================================================
# Unit — filter.filter_slivers
# ======================================================================


def test_filter_slivers_protects_boundary() -> None:
    """경계 tet 는 interior 보다 관대한 threshold 로 보존됨."""
    from core.generator.native_tet.filter import filter_slivers

    # 4 tet: 3 boundary (surface vertex 포함), 1 interior only.
    # surface vertex id: 0,1,2,3. interior: 4,5.
    tets = np.array(
        [
            [0, 1, 2, 4],   # boundary (surf)
            [0, 1, 3, 4],   # boundary
            [2, 3, 4, 5],   # partially boundary (2,3 surf)
            [4, 5, 4, 5],   # interior degenerate (일부러 sliver)
        ],
        dtype=np.int64,
    )
    # 정사면체 근사 + degenerate tet.
    pts = np.array(
        [
            [0, 0, 0], [1, 0, 0], [0.5, 0.866, 0], [0.5, 0.289, 0.816],
            [0.4, 0.3, 0.2], [0.6, 0.5, 0.4],
        ],
        dtype=np.float64,
    )
    inside = np.ones(4, dtype=bool)

    # interior threshold 높게, boundary 낮게.
    fr = filter_slivers(
        tets, pts, inside,
        n_surface_vertices=4,
        q_threshold_interior=0.5,   # interior tet 은 탈락 유도
        q_threshold_boundary=0.0,   # boundary 는 전부 통과
        protect_boundary_faces=False,
    )
    # 3 개 boundary tet 모두 유지.
    assert fr.keep_mask[:3].all()
    # interior degenerate tet 은 탈락.
    assert not fr.keep_mask[3]


# ======================================================================
# Unit — insertion.find_missing_triangles / recovery_seeds
# ======================================================================


def test_find_missing_triangles_empty_when_no_input() -> None:
    from core.generator.native_tet.insertion import find_missing_triangles

    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    F = np.zeros((0, 3), dtype=np.int64)
    assert find_missing_triangles(F, tets).size == 0


def test_find_missing_triangles_detects_absent() -> None:
    """tet facet 에 없는 triangle 은 missing 으로 리턴."""
    from core.generator.native_tet.insertion import find_missing_triangles

    # tet {0,1,2,3} 은 facet {(0,1,2),(0,1,3),(0,2,3),(1,2,3)}.
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    # (4,5,6) 은 tet 안에 없음 → missing.
    F = np.array([[0, 1, 2], [4, 5, 6]], dtype=np.int64)

    missing = find_missing_triangles(F, tets)
    assert missing.tolist() == [1]


def test_recovery_seeds_returns_barycenters() -> None:
    from core.generator.native_tet.insertion import recovery_seeds

    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    F = np.array([[0, 1, 2]], dtype=np.int64)
    # 현재 tet 에 없는 triangle.
    tets = np.array([[0, 1, 2, 2]], dtype=np.int64)  # degenerate, just placeholder

    rec = recovery_seeds(V, F, tets, bump_distance=0.0)
    # triangle (0,1,2) 는 tet facet (0,1,2,2) 에서 {0,1,2} 로 정렬되므로
    # find_missing_triangles 는 이를 facet 으로 본다 → n_missing=0 기대.
    assert rec.n_missing == 0


# ======================================================================
# Unit — smooth.smooth_interior
# ======================================================================


def test_smooth_interior_locks_surface() -> None:
    from core.generator.native_tet.smooth import smooth_interior

    # 5 pts: 0..3 surface, 4 interior.
    pts = np.array(
        [
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
            [0.9, 0.9, 0.9],  # interior — centroid 로 이동 기대
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 4], [0, 1, 3, 4], [0, 2, 3, 4], [1, 2, 3, 4]], dtype=np.int64)

    original_pts = pts.copy()
    sr = smooth_interior(
        pts, tets,
        locked_vertex_ids=np.array([0, 1, 2, 3], dtype=np.int64),
        n_iter=3, relax=0.5,
    )
    # surface vertex 는 그대로.
    assert np.allclose(pts[:4], original_pts[:4])
    # interior vertex 는 centroid 방향으로 이동.
    assert not np.allclose(pts[4], original_pts[4])
    assert sr.n_iter == 3
    assert sr.max_displacement > 0.0


# ======================================================================
# Integration — generate_native_tet (Phase A on / off 비교)
# ======================================================================


def test_native_tet_phase_a_produces_mesh_on_sphere(tmp_path) -> None:
    """Phase A 활성화된 native_tet 이 sphere 에서 정상 메쉬 생성."""
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    case = tmp_path / "sphere_phaseA"
    res = generate_native_tet(
        V, F, case,
        seed_density=6,
        enable_phase_a=True,
        recovery_iterations=1,
        smooth_iterations=1,
    )
    assert res.success, res.message
    assert res.n_cells > 0
    assert res.n_points >= V.shape[0]


def test_native_tet_phase_a_off_still_works(tmp_path) -> None:
    """Phase A 끄기 — legacy 경로도 동작 유지 (회귀)."""
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    case = tmp_path / "cube_legacy"
    res = generate_native_tet(
        V, F, case,
        seed_density=4,
        enable_phase_a=False,
    )
    assert res.success, res.message
    assert res.n_cells > 0


def test_native_tet_phase_a_improves_cube_boundary(tmp_path) -> None:
    """큐브: Phase A 켜면 8 꼭짓점 전부 최종 메쉬에 포함 (feature 보존)."""
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    case = tmp_path / "cube_phaseA"
    res = generate_native_tet(
        V, F, case,
        seed_density=4,
        enable_phase_a=True,
        feature_angle_deg=30.0,
    )
    assert res.success, res.message
    # tet_points 가 원본 8 corner 를 포함해야 한다 (허용 오차 1e-6).
    assert res.tet_points is not None
    found = 0
    for corner in V:
        d = np.linalg.norm(res.tet_points - corner, axis=1)
        if d.min() < 1e-6:
            found += 1
    assert found == 8, f"cube corner 보존 실패: {found}/8"
