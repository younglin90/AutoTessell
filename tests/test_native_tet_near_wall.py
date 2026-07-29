from __future__ import annotations

from collections import Counter

import numpy as np

from core.generator.native_tet.near_wall import (
    TetQualityMetrics,
    _quality_rejection,
    boundary_face_keys,
    detect_boundary_face_owners,
    find_containing_tet,
    grow_visibility_cavity,
    max_boundary_skew,
    refine_near_wall,
)
from core.generator.native_tet.mesher import _run_near_wall_prewrite


def _flat_cap_mesh() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    surface_vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    surface_faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
    points = np.vstack([surface_vertices, [0.75, 0.10, 0.02]])
    tets = np.array(
        [[0, 1, 2, 4], [0, 1, 4, 3], [0, 4, 2, 3], [4, 1, 2, 3]],
        dtype=np.int64,
    )
    return points, tets, surface_vertices, surface_faces


def test_flat_cap_cavity_materially_improves_boundary_skew() -> None:
    points, tets, surface_vertices, surface_faces = _flat_cap_mesh()
    result = refine_near_wall(points, tets, surface_vertices, surface_faces)
    assert result.attempted > 0
    assert result.accepted >= 1
    assert result.after_skew < result.before_skew * 0.5


def test_owner_apex_direction_does_not_require_surface_winding() -> None:
    points, tets, _, _ = _flat_cap_mesh()
    result = refine_near_wall(
        points,
        tets,
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 3), dtype=np.int64),
        max_owners=1,
    )
    assert result.accepted == 1
    assert result.after_skew < result.before_skew


def test_regular_tetrahedron_is_noop_and_inputs_are_unchanged() -> None:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, np.sqrt(3.0) / 2.0, 0.0],
            [0.5, np.sqrt(3.0) / 6.0, np.sqrt(2.0 / 3.0)],
        ]
    )
    faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
    tets = np.array([[0, 1, 2, 3]])
    points_before = points.copy()
    tets_before = tets.copy()
    result = refine_near_wall(points, tets, points, faces)
    assert result.attempted == result.accepted == 0
    assert np.array_equal(result.points, points_before)
    assert np.array_equal(result.tets, tets_before)
    assert np.array_equal(points, points_before)
    assert np.array_equal(tets, tets_before)


def test_outside_point_has_no_containing_tet() -> None:
    points, tets, _, _ = _flat_cap_mesh()
    assert find_containing_tet(points, tets, np.array([2.0, 2.0, 2.0])) is None


def test_containing_tet_uses_batched_column_rhs(monkeypatch) -> None:
    points, tets, _, _ = _flat_cap_mesh()
    original_solve = np.linalg.solve
    observed_shapes: list[tuple[tuple[int, ...], tuple[int, ...]]] = []

    def recording_solve(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        observed_shapes.append((a.shape, b.shape))
        return original_solve(a, b)

    monkeypatch.setattr(np.linalg, "solve", recording_solve)
    containing = find_containing_tet(points, tets, np.array([0.2, 0.2, 0.2]))

    assert containing is not None
    assert observed_shapes
    assert observed_shapes[0][0][1:] == (3, 3)
    assert observed_shapes[0][1][1:] == (3, 1)


def test_acceptance_preserves_boundary_volume_and_validity() -> None:
    points, tets, surface_vertices, surface_faces = _flat_cap_mesh()
    original_boundary = boundary_face_keys(tets)
    result = refine_near_wall(points, tets, surface_vertices, surface_faces)
    assert boundary_face_keys(result.tets) == original_boundary
    assert np.isclose(result.volume_after, result.volume_before, rtol=1e-10, atol=1e-14)
    vertices = result.points[result.tets]
    volumes6 = np.einsum(
        "ij,ij->i",
        vertices[:, 1] - vertices[:, 0],
        np.cross(vertices[:, 2] - vertices[:, 0], vertices[:, 3] - vertices[:, 0]),
    )
    assert np.all(np.abs(volumes6) > 1e-13)
    assert np.array_equal(result.points[: points.shape[0]], points)


def test_boundary_gain_that_worsens_internal_skew_is_rejected() -> None:
    before = TetQualityMetrics(10.0, 2.0, 60.0, 0.2, 0.2)
    after = TetQualityMetrics(5.0, 2.1, 60.0, 0.2, 0.2)

    assert _quality_rejection(before, after) == "internal_skew"


def test_flat_owner_detection_uses_boundary_multiplicity() -> None:
    points, tets, _, _ = _flat_cap_mesh()
    owners = detect_boundary_face_owners(points, tets)
    assert owners
    assert owners[0].face == (0, 1, 2)
    assert owners[0].owner == 0


def test_visibility_growth_repairs_non_star_seed_cavity() -> None:
    points, tets, _, _ = _flat_cap_mesh()
    point = np.array([1.0 / 3.0, 1.0 / 3.0, 0.10])
    assert find_containing_tet(points, tets, point) == 2

    def cavity_volumes(cavity: set[int]) -> tuple[float, float]:
        counts: Counter[tuple[int, int, int]] = Counter()
        for tet_id in cavity:
            tet = tets[tet_id]
            for omitted in range(4):
                counts[tuple(sorted(np.delete(tet, omitted).tolist()))] += 1
        boundary = [face for face, count in counts.items() if count == 1]
        trial_points = np.vstack([points, point])
        fan = np.array([(*face, points.shape[0]) for face in boundary])

        def volume(mesh_points: np.ndarray, mesh_tets: np.ndarray) -> float:
            vertices = mesh_points[mesh_tets]
            volumes6 = np.einsum(
                "ij,ij->i",
                vertices[:, 1] - vertices[:, 0],
                np.cross(
                    vertices[:, 2] - vertices[:, 0],
                    vertices[:, 3] - vertices[:, 0],
                ),
            )
            return float(np.abs(volumes6).sum() / 6.0)

        return volume(points, tets[sorted(cavity)]), volume(trial_points, fan)

    seed_removed, seed_fan = cavity_volumes({0})
    assert not np.isclose(seed_removed, seed_fan, rtol=1e-10, atol=1e-14)

    cavity, reason = grow_visibility_cavity(points, tets, point, {0})
    assert reason == "visible"
    assert cavity == {0, 1, 2, 3}
    grown_removed, grown_fan = cavity_volumes(cavity)
    assert np.isclose(grown_removed, grown_fan, rtol=1e-10, atol=1e-14)


def test_mesher_prewrite_integration_applies_guarded_refinement(monkeypatch) -> None:
    points, tets, surface_vertices, surface_faces = _flat_cap_mesh()
    monkeypatch.delenv("AUTO_TESSELL_NEAR_WALL_OFF", raising=False)
    monkeypatch.setenv("AUTO_TESSELL_NEAR_WALL", "1")
    monkeypatch.setenv("AUTO_TESSELL_NEAR_WALL_SKEW_THRESHOLD", "0")
    monkeypatch.setenv("AUTO_TESSELL_NEAR_WALL_MAX_OWNERS", "8")

    new_points, new_tets, applied = _run_near_wall_prewrite(
        points, tets, surface_vertices, surface_faces, target_cells=4
    )

    assert applied
    assert max_boundary_skew(new_points, new_tets) < max_boundary_skew(points, tets)
    assert boundary_face_keys(new_tets) == boundary_face_keys(tets)
    assert np.array_equal(new_points[: points.shape[0]], points)


def test_mesher_prewrite_opt_out_and_target_floor_are_exact_noops(monkeypatch) -> None:
    points, tets, surface_vertices, surface_faces = _flat_cap_mesh()
    monkeypatch.setenv("AUTO_TESSELL_NEAR_WALL_OFF", "1")
    out_points, out_tets, applied = _run_near_wall_prewrite(
        points, tets, surface_vertices, surface_faces, target_cells=4
    )
    assert not applied
    assert out_points is points
    assert out_tets is tets

    monkeypatch.setenv("AUTO_TESSELL_NEAR_WALL_OFF", "0")
    monkeypatch.setenv("AUTO_TESSELL_NEAR_WALL_SKEW_THRESHOLD", "0")
    out_points, out_tets, applied = _run_near_wall_prewrite(
        points, tets, surface_vertices, surface_faces, target_cells=1000
    )
    assert not applied
    assert out_points is points
    assert out_tets is tets
