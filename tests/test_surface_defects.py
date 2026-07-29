"""Focused tests for deterministic surface-defect localization."""

from __future__ import annotations

import json

import numpy as np

from core.preprocessor.surface_defects import (
    apply_surface_defect_repair,
    detect_surface_defects,
)


def _of_type(defects: list[dict[str, object]], defect_type: str) -> list[dict[str, object]]:
    return [defect for defect in defects if defect["type"] == defect_type]


def test_exact_degenerate_and_duplicate_face_ids() -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [2, 1, 0], [0, 0, 1]], dtype=np.int64)

    defects = detect_surface_defects(vertices, faces)

    assert [defect["defect_id"] for defect in _of_type(defects, "degenerate_face")] == [
        "degenerate_face:2"
    ]
    duplicates = _of_type(defects, "duplicate_faces")
    assert [defect["defect_id"] for defect in duplicates] == ["duplicate_faces:0-1"]
    assert duplicates[0]["face_ids"] == [0, 1]
    assert duplicates[0]["vertex_ids"] == [0, 1, 2]


def test_boundary_edges_group_into_deterministic_loops() -> None:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [10.0, 0.0, 0.0],
            [11.0, 0.0, 0.0],
            [10.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)

    loops = _of_type(detect_surface_defects(vertices, faces), "boundary_loop")

    assert [loop["defect_id"] for loop in loops] == ["boundary_loop:0-1", "boundary_loop:3-4"]
    assert loops[0]["edge_vertex_ids"] == [[0, 1], [0, 2], [1, 2]]
    assert loops[0]["face_ids"] == [0]


def test_branched_open_edges_form_one_boundary_component() -> None:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [0, 3, 4]], dtype=np.int64)

    components = _of_type(detect_surface_defects(vertices, faces), "boundary_component")

    assert [component["defect_id"] for component in components] == ["boundary_component:0-1"]
    assert components[0]["face_ids"] == [0, 1]
    assert components[0]["vertex_ids"] == [0, 1, 2, 3, 4]


def test_non_manifold_edge_includes_exact_incident_face_ids() -> None:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, -1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [1, 0, 3], [0, 1, 4]], dtype=np.int64)

    defects = _of_type(detect_surface_defects(vertices, faces), "non_manifold_edge")

    assert [defect["defect_id"] for defect in defects] == ["non_manifold_edge:0-1"]
    assert defects[0]["face_ids"] == [0, 1, 2]
    assert defects[0]["edge_vertex_ids"] == [[0, 1]]


def test_inconsistent_adjacent_winding_has_exact_edge_id() -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [0, 3, 2]], dtype=np.int64)

    defects = _of_type(detect_surface_defects(vertices, faces), "inconsistent_winding")

    assert [defect["defect_id"] for defect in defects] == ["inconsistent_winding:0-2"]
    assert defects[0]["face_ids"] == [0, 1]
    assert defects[0]["edge_vertex_ids"] == [[0, 2]]


def test_existing_detector_supplies_self_intersection_pair() -> None:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 1.0, 0.0],
            [0.5, 0.0, -1.0],
            [0.5, 0.0, 1.0],
            [0.5, 1.0, 0.5],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)

    defects = _of_type(detect_surface_defects(vertices, faces), "self_intersection")

    assert [defect["defect_id"] for defect in defects] == ["self_intersection:0-1"]
    assert defects[0]["face_ids"] == [0, 1]
    assert defects[0]["vertex_ids"] == [0, 1, 2, 3, 4, 5]


def test_result_is_deterministic_json_safe_and_input_is_immutable() -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [0, 3, 2]], dtype=np.int64)
    original_vertices = vertices.copy()
    original_faces = faces.copy()
    vertices.setflags(write=False)
    faces.setflags(write=False)

    first = detect_surface_defects(vertices, faces)
    second = detect_surface_defects(vertices, faces)

    assert first == second
    expected_keys = {
        "defect_id",
        "type",
        "severity",
        "face_ids",
        "edge_vertex_ids",
        "vertex_ids",
        "bounds",
        "repair_actions",
    }
    assert all(set(defect) == expected_keys for defect in first)
    assert json.dumps(first, allow_nan=False, sort_keys=True) == json.dumps(
        second, allow_nan=False, sort_keys=True
    )
    np.testing.assert_array_equal(vertices, original_vertices)
    np.testing.assert_array_equal(faces, original_faces)


def test_empty_mesh_has_no_defects() -> None:
    vertices = np.empty((0, 3), dtype=np.float64)
    faces = np.empty((0, 3), dtype=np.int64)

    assert detect_surface_defects(vertices, faces) == []


def test_repair_removes_only_selected_duplicate_faces() -> None:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [10.0, 0.0, 0.0],
            [11.0, 0.0, 0.0],
            [10.0, 1.0, 0.0],
        ]
    )
    faces = np.array([[0, 1, 2], [2, 1, 0], [3, 4, 5], [5, 4, 3]])

    _, repaired = apply_surface_defect_repair(
        vertices, faces, "duplicate_faces:0-1", "remove_duplicate_faces"
    )

    assert repaired.tolist() == [[0, 1, 2], [3, 4, 5], [5, 4, 3]]


def test_repair_fills_only_selected_boundary_loop() -> None:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [10.0, 0.0, 0.0],
            [11.0, 0.0, 0.0],
            [10.0, 1.0, 0.0],
        ]
    )
    faces = np.array([[0, 1, 2], [3, 4, 5]])

    _, repaired = apply_surface_defect_repair(vertices, faces, "boundary_loop:0-1", "fill_hole")
    remaining_loops = _of_type(detect_surface_defects(vertices, repaired), "boundary_loop")

    assert len(repaired) == 3
    assert [item["defect_id"] for item in remaining_loops] == ["boundary_loop:3-4"]


def test_repair_splits_only_extra_non_manifold_incidence() -> None:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, -1.0, 0.0],
        ]
    )
    faces = np.array([[0, 1, 2], [1, 0, 3], [0, 1, 4]])

    repaired_vertices, repaired_faces = apply_surface_defect_repair(
        vertices,
        faces,
        "non_manifold_edge:0-1",
        "split_non_manifold_edge",
    )

    assert len(repaired_vertices) == 7
    assert repaired_faces[:2].tolist() == faces[:2].tolist()
    assert not _of_type(
        detect_surface_defects(repaired_vertices, repaired_faces), "non_manifold_edge"
    )
