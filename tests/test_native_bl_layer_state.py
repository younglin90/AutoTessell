"""Focused native BL thickness, aspect, and layer-count regressions."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import core.layers.native_bl as native_bl
from core.generator.polymesh_writer import write_generic_polymesh
from core.layers.native_bl import BLConfig, generate_native_bl
from core.utils.polymesh_reader import parse_foam_points


def _write_single_tet_case(case_dir: Path) -> np.ndarray:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    write_generic_polymesh(
        points,
        [[
            [0, 1, 2],
            [0, 3, 1],
            [1, 3, 2],
            [2, 3, 0],
        ]],
        case_dir,
        patch_name="wall",
        patch_type="wall",
    )
    return points


def _stable_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_ENABLE", "0")
    monkeypatch.delenv("AUTO_TESSELL_BL_VD_FOR", raising=False)
    monkeypatch.setenv("AUTO_TESSELL_BL_ASPECT_ENFORCE", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANTI_INVERT_CAP", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT_DIAG", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_INNER_SMOOTH", "0")


def test_local_collision_factor_scales_cumulative_path_exactly_once() -> None:
    cumulative = {7: np.array([0.0, 0.2, 0.5])}
    scales, scaled_cumulative = native_bl._apply_local_collision_factors(
        [7],
        np.array([0.5]),
        {7: 0.8},
        cumulative,
        use_per_vertex_cumulative=True,
    )

    assert scales[7] == pytest.approx(0.8)
    assert scaled_cumulative is not None
    np.testing.assert_allclose(scaled_cumulative[7], [0.0, 0.1, 0.25])
    np.testing.assert_allclose(cumulative[7], [0.0, 0.2, 0.5])


@pytest.mark.parametrize("explicit", [False, True])
def test_front_collision_halves_adaptive_and_explicit_cumulative_offsets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    explicit: bool,
) -> None:
    original = _write_single_tet_case(tmp_path)
    _stable_environment(monkeypatch)
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT", "0")
    monkeypatch.setattr(
        native_bl,
        "_nearby_opposite_front_mask",
        lambda _normals, points, **_kwargs: np.ones(len(points), dtype=bool),
    )
    if not explicit:
        monkeypatch.setattr(
            native_bl,
            "_curvature_adaptive_thickness",
            lambda *_args, **_kwargs: np.full(4, 0.02),
        )
        monkeypatch.setattr(
            native_bl,
            "_relative_first_thickness",
            lambda *_args, **_kwargs: np.full(4, 0.02),
        )

    config = BLConfig(
        num_layers=2,
        first_thickness=0.02,
        growth_ratio=1.2,
        per_vertex_first_thickness=(
            {vertex: 0.02 for vertex in range(4)} if explicit else None
        ),
        collision_safety=False,
        feature_lock=False,
        quality_check_enabled=False,
        backup_original=False,
    )
    result = generate_native_bl(tmp_path, config)

    assert result.success, result.message
    disk_points = np.asarray(
        parse_foam_points(tmp_path / "constant" / "polyMesh" / "points"),
        dtype=np.float64,
    )
    displacement = np.linalg.norm(disk_points[:4] - original, axis=1)
    expected_total = 0.5 * 0.02 * (1.0 + 1.2)
    np.testing.assert_allclose(displacement, expected_total, atol=1e-8, rtol=0.0)


def test_evaluator_aspect_increases_when_layer_is_shrunk() -> None:
    base_edges = np.array([1.0, 0.8, 0.6])
    aspect = native_bl._evaluator_prism_aspect(base_edges, np.full(3, 0.1))
    shrunk = native_bl._evaluator_prism_aspect(base_edges, np.full(3, 0.05))

    assert aspect == pytest.approx(10.0)
    assert shrunk == pytest.approx(20.0)


def test_feature_size_smoothing_uses_local_caps_instead_of_global_min_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GLFS keeps open-wall layers thick while capping the narrow-gap vertex."""
    original = _write_single_tet_case(tmp_path)
    _stable_environment(monkeypatch)
    monkeypatch.setenv("AUTO_TESSELL_BL_EXTRUSION_LINE_SEARCH", "0")
    monkeypatch.setattr(
        native_bl,
        "_nearby_opposite_front_mask",
        lambda _normals, points, **_kwargs: np.zeros(len(points), dtype=bool),
    )
    monkeypatch.setattr(
        native_bl,
        "_compute_collision_distance",
        lambda *_args, **_kwargs: {0: 0.01, 1: 0.1, 2: 0.1, 3: 0.1},
    )

    result = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            first_thickness=0.1,
            growth_ratio=1.0,
            collision_safety=True,
            feature_size_smoothing=True,
            feature_size_gradient_limit=0.02,
            feature_lock=False,
            quality_check_enabled=False,
            backup_original=False,
        ),
    )

    assert result.success, result.message
    disk_points = np.asarray(
        parse_foam_points(tmp_path / "constant" / "polyMesh" / "points"),
        dtype=np.float64,
    )
    displacement = np.linalg.norm(disk_points[:4] - original, axis=1)
    assert displacement[0] == pytest.approx(0.005, abs=1.0e-8)
    np.testing.assert_allclose(displacement[1:], 0.025, atol=1.0e-8, rtol=0.0)
    quality = json.loads((tmp_path / "native_bl_quality.json").read_text())
    assert quality["feature_size"]["enabled"] is True
    assert quality["feature_size"]["n_limited"] == 3


def test_feature_size_smoothing_runs_through_positive_volume_line_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_single_tet_case(tmp_path)
    _stable_environment(monkeypatch)
    monkeypatch.setattr(
        native_bl,
        "_nearby_opposite_front_mask",
        lambda _normals, points, **_kwargs: np.zeros(len(points), dtype=bool),
    )
    monkeypatch.setattr(
        native_bl,
        "_compute_collision_distance",
        lambda *_args, **_kwargs: {0: 0.01, 1: 0.1, 2: 0.1, 3: 0.1},
    )

    result = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            first_thickness=0.02,
            growth_ratio=1.0,
            collision_safety=True,
            feature_size_smoothing=True,
            feature_size_gradient_limit=0.02,
            feature_lock=False,
            quality_check_enabled=False,
            backup_original=False,
        ),
    )

    assert result.success, result.message
    quality = json.loads((tmp_path / "native_bl_quality.json").read_text())
    line_search = quality["extrusion_line_search"]
    assert line_search["enabled"] is True
    assert line_search["accepted"] is True
    assert line_search["negative_post"] == 0


def test_real_normal_split_is_rejected_when_it_would_worsen_evaluator_aspect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_single_tet_case(tmp_path)
    _stable_environment(monkeypatch)
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT", "1")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT_THRESH", "4.0")
    monkeypatch.setattr(
        native_bl,
        "_nearby_opposite_front_mask",
        lambda _normals, points, **_kwargs: np.zeros(len(points), dtype=bool),
    )

    result = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            first_thickness=0.01,
            per_vertex_first_thickness={vertex: 0.01 for vertex in range(4)},
            collision_safety=False,
            feature_lock=False,
            quality_check_enabled=False,
            backup_original=False,
        ),
    )

    assert result.success, result.message
    assert result.n_prism_cells == 4
    quality = json.loads((tmp_path / "native_bl_quality.json").read_text())
    assert quality["requested_layers"] == 1
    assert quality["used_layers"] == 1


def test_shrink_iteration_does_not_reduce_thin_layer_height(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _write_single_tet_case(tmp_path)
    _stable_environment(monkeypatch)
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT", "0")
    monkeypatch.setattr(
        native_bl,
        "_nearby_opposite_front_mask",
        lambda _normals, points, **_kwargs: np.zeros(len(points), dtype=bool),
    )

    result = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            first_thickness=0.01,
            per_vertex_first_thickness={vertex: 0.01 for vertex in range(4)},
            collision_safety=False,
            feature_lock=False,
            quality_check_enabled=False,
            backup_original=False,
            shrink_iterations=2,
            shrink_factor=0.5,
            shrink_aspect_threshold=1.0,
        ),
    )

    assert result.success, result.message
    disk_points = np.asarray(
        parse_foam_points(tmp_path / "constant" / "polyMesh" / "points"),
        dtype=np.float64,
    )
    displacement = np.linalg.norm(disk_points[:4] - original, axis=1)
    np.testing.assert_allclose(displacement, 0.01, atol=1e-8, rtol=0.0)


def test_lcr_reduction_synchronizes_arrays_totals_and_reported_layers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _write_single_tet_case(tmp_path)
    _stable_environment(monkeypatch)
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT", "0")
    monkeypatch.setenv("AUTO_TESSELL_LCR_AUTO_REDUCE", "1")
    monkeypatch.setattr(
        native_bl,
        "_compute_collision_distance",
        lambda _points, _faces, _wall_faces, wall_vertices, _vnorm, **_kwargs: {
            int(vertex): 0.05 for vertex in wall_vertices
        },
    )
    monkeypatch.setattr(
        native_bl,
        "_nearby_opposite_front_mask",
        lambda _normals, points, **_kwargs: np.zeros(len(points), dtype=bool),
    )
    monkeypatch.setattr(
        native_bl,
        "_curvature_adaptive_thickness",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("disabled")),
    )

    config = BLConfig(
        num_layers=3,
        first_thickness=0.01,
        growth_ratio=1.2,
        collision_safety=True,
        collision_safety_factor=0.5,
        feature_lock=False,
        quality_check_enabled=False,
        backup_original=False,
    )
    result = generate_native_bl(tmp_path, config)

    assert result.success, result.message
    assert config.num_layers == 2
    assert result.n_prism_cells == 8
    quality = json.loads((tmp_path / "native_bl_quality.json").read_text())
    assert quality["requested_layers"] == 3
    assert quality["used_layers"] == 2
    assert quality["config"]["num_layers"] == 2
    assert quality["total_thickness"] == pytest.approx(result.total_thickness)
    disk_points = np.asarray(
        parse_foam_points(tmp_path / "constant" / "polyMesh" / "points"),
        dtype=np.float64,
    )
    displacement = np.linalg.norm(disk_points[:4] - original, axis=1)
    np.testing.assert_allclose(
        displacement,
        result.total_thickness,
        atol=1e-8,
        rtol=0.0,
    )


def test_bounded_extrusion_line_search_keeps_layers_and_removes_bulk_inversion(
) -> None:
    original = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [10.0, 0.0, 0.0],
            [11.0, 0.0, 0.0],
            [10.0, 1.0, 0.0],
            [10.01, 0.01, 0.001],
        ],
        dtype=np.float64,
    )
    full = np.vstack((original.copy(), original[:3], original[:3]))
    full[:3, 2] = 2.0
    full[11:14, 2] = 0.5
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
        [4, 5, 6],
        [4, 7, 5],
        [5, 7, 6],
        [6, 7, 4],
    ]
    layer_ids = [
        {0: 8, 1: 9, 2: 10},
        {0: 11, 1: 12, 2: 13},
        {0: 0, 1: 1, 2: 2},
    ]

    candidate, diagnostic = native_bl._bounded_bl_extrusion_line_search(
        original,
        full,
        faces,
        [0, 0, 0, 0, 1, 1, 1, 1],
        [],
        [0, 1, 2],
        layer_ids,
        base_n_cells=2,
        max_rounds=8,
    )
    metrics = native_bl._bl_extrusion_metrics(
        candidate,
        original,
        faces,
        [0, 0, 0, 0, 1, 1, 1, 1],
        [],
        base_n_cells=2,
    )

    assert diagnostic["mode"] == "per_vertex"
    assert diagnostic["negative_pre"] == 1
    assert diagnostic["negative_post"] == 0
    assert diagnostic["n_scaled_vertices"] == 3
    assert metrics.inverted_cells == ()
    assert metrics.max_boundary_skewness <= diagnostic["boundary_skew_pre"]
    assert metrics.max_non_orthogonality <= diagnostic["non_ortho_pre"]
    np.testing.assert_allclose(candidate[8:11], original[:3], atol=0.0, rtol=0.0)
    assert len(layer_ids) - 1 == 2


def test_bounded_extrusion_line_search_expands_until_face_weight_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = np.array([[0.0, 0.0, 0.0]], dtype=np.float64)
    full = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)

    def fake_metrics(points: np.ndarray, *_args: object, **_kwargs: object):
        scale = float(points[1, 2])
        return native_bl._BLExtrusionMetrics(
            (),
            1.0,
            50.0,
            0.04 + 0.05 * (scale - 1.0),
        )

    monkeypatch.setattr(native_bl, "_bl_extrusion_metrics", fake_metrics)

    candidate, diagnostic = native_bl._bounded_bl_extrusion_line_search(
        original,
        full,
        [],
        [],
        [],
        [0],
        [{0: 0}, {0: 1}],
        base_n_cells=0,
        max_rounds=5,
        allow_quality_expansion=True,
    )

    assert diagnostic["mode"] == "global_expand"
    assert diagnostic["accepted"] is True
    assert diagnostic["face_weight_pre"] == pytest.approx(0.04)
    assert diagnostic["face_weight_post"] >= 0.05
    assert diagnostic["max_scale"] == pytest.approx(1.2)
    assert candidate[1, 2] == pytest.approx(1.2)


def test_triangle_interface_hole_audit_adds_missing_tet_wall_face() -> None:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, -1.0],
            [1.0, 1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [0.2, 0.2, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [2, 1, 0],
        [1, 2, 6],
        [0, 6, 1],
        [2, 6, 0],
        [0, 1, 3],
        [1, 2, 3],
        [2, 0, 3],
    ]
    owner = np.array([0, 3, 3, 3, 0, 1, 2], dtype=np.int64)
    neighbour = np.array([1], dtype=np.int64)
    wall_faces = [4, 5, 6]
    face_to_patch = {
        4: (0, 0),
        5: (0, 1),
        6: (0, 2),
    }

    owner_out, wall_out, diagnostic = (
        native_bl._repair_triangular_selected_wall_holes(
            points,
            faces,
            owner,
            neighbour,
            wall_faces,
            face_to_patch,
        )
    )

    assert diagnostic["n_open_edges_pre"] == 3
    assert diagnostic["n_open_edges_post"] == 0
    assert diagnostic["n_repaired_triangles"] == 1
    repair = diagnostic["repairs"][0]
    assert repair["canonical_key"] == [0, 1, 2]
    assert repair["canonical_matches"] == [
        {"face": 0, "owner": 0, "neighbour": 1}
    ]
    assert repair["missing_owner"] == 3
    assert wall_out[-1] == len(faces) - 1
    assert tuple(sorted(faces[-1])) == (0, 1, 2)
    assert int(owner_out[-1]) == 3


def test_relative_ratio_defaults_to_tet_sweet_spot_from_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTO_TESSELL_BL_REL_RATIO", raising=False)
    (tmp_path / "generator_log.json").write_text(
        json.dumps({"selected_tier": "tier_native_tet"}),
        encoding="utf-8",
    )

    ratio, source = native_bl._relative_thickness_ratio(tmp_path, "generic")

    assert ratio == pytest.approx(0.08)
    assert source == "native_tet_default"


def test_relative_ratio_preserves_other_engines_and_explicit_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTO_TESSELL_BL_REL_RATIO", raising=False)
    ratio, source = native_bl._relative_thickness_ratio(tmp_path, "hex")
    assert ratio == pytest.approx(0.3)
    assert source == "default"

    monkeypatch.setenv("AUTO_TESSELL_BL_REL_RATIO", "0.125")
    ratio, source = native_bl._relative_thickness_ratio(tmp_path, "tet")
    assert ratio == pytest.approx(0.125)
    assert source == "environment"


def test_relative_ratio_uses_convex_extrusion_transition_thickness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTO_TESSELL_BL_REL_RATIO", raising=False)
    (tmp_path / "native_tet_convex_extrusion.marker").write_text(
        "1\n", encoding="ascii"
    )

    ratio, source = native_bl._relative_thickness_ratio(tmp_path, "tet")

    assert ratio == pytest.approx(0.25)
    assert source == "native_tet_convex_extrusion"


def test_native_tet_dominant_caps_select_thin_axis_faces() -> None:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [10.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 0.1],
            [10.0, 0.0, 0.1],
            [10.0, 1.0, 0.1],
            [0.0, 1.0, 0.1],
        ]
    )
    faces = [
        [0, 1, 2, 3],
        [4, 7, 6, 5],
        [0, 4, 5, 1],
        [1, 5, 6, 2],
        [2, 6, 7, 3],
        [3, 7, 4, 0],
    ]

    selected, diagnostic = native_bl._select_native_tet_dominant_cap_faces(
        points,
        faces,
        list(range(6)),
        engine_tag="native_tet",
    )

    assert selected == [0, 1]
    assert diagnostic["applied"] is True
    assert diagnostic["thin_axis"] == 2


def test_dominant_caps_use_area_after_coplanar_face_merge() -> None:
    points = np.array(
        [
            [0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 2.0, 0.0], [0.0, 2.0, 0.0],
            [0.0, 0.0, 0.01], [2.0, 0.0, 0.01], [2.0, 2.0, 0.01], [0.0, 2.0, 0.01],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 3, 2, 1], [4, 5, 6, 7],
        [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7],
    ]

    selected, diagnostic = native_bl._select_native_tet_dominant_cap_faces(
        points, faces, list(range(len(faces))), engine_tag="native_tet"
    )

    assert diagnostic["applied"] is True
    assert diagnostic["thin_axis"] == 2
    assert selected == [0, 1]


def test_dominant_caps_leave_generic_and_compact_meshes_unchanged() -> None:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    faces = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]

    generic, generic_diag = native_bl._select_native_tet_dominant_cap_faces(
        points, faces, list(range(4)), engine_tag="generic"
    )
    compact, compact_diag = native_bl._select_native_tet_dominant_cap_faces(
        points, faces, list(range(4)), engine_tag="native_tet"
    )

    assert generic == list(range(4))
    assert compact == list(range(4))
    assert generic_diag["applied"] is False
    assert compact_diag["applied"] is False


def test_dominant_caps_honor_generator_extrusion_axis() -> None:
    points = np.array(
        [
            [0, 0, 0], [3, 0, 0], [3, 2, 0], [0, 2, 0],
            [0, 0, 1], [3, 0, 1], [3, 2, 1], [0, 2, 1],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 3, 2, 1], [4, 5, 6, 7],
        [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7],
    ]

    selected, diagnostic = native_bl._select_native_tet_dominant_cap_faces(
        points,
        faces,
        list(range(6)),
        engine_tag="native_tet",
        min_bbox_aspect=0.9,
        preferred_axis=0,
    )

    assert diagnostic["thin_axis"] == 0
    assert selected == [3, 5]


def test_dominant_caps_choose_planar_ends_of_long_extrusion() -> None:
    points = np.array(
        [
            [0.0, 0.0, 0.0], [0.02, 0.0, 0.0],
            [0.02, 0.02, 0.0], [0.0, 0.02, 0.0],
            [0.0, 0.0, 10.0], [0.02, 0.0, 10.0],
            [0.02, 0.02, 10.0], [0.0, 0.02, 10.0],
        ]
    )
    faces = [
        [0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1],
        [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0],
    ]

    selected, diagnostic = native_bl._select_native_tet_dominant_cap_faces(
        points, faces, list(range(6)), engine_tag="native_tet"
    )

    assert selected == [0, 1]
    assert diagnostic["thin_axis"] == 2
    assert diagnostic["axis_extent_ratio"] == pytest.approx(500.0)


def test_small_disconnected_wall_component_is_excluded_from_bl() -> None:
    large_points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64
    )
    small_points = 0.01 * large_points + np.array([2.0, 0.0, 0.0])
    points = np.vstack((large_points, small_points))
    faces = [
        [0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3],
        [4, 6, 5], [4, 5, 7], [5, 6, 7], [6, 4, 7],
    ]

    selected, diagnostic = native_bl._filter_small_native_tet_wall_components(
        points, faces, list(range(8))
    )

    assert selected == [0, 1, 2, 3]
    assert diagnostic["applied"] is True
