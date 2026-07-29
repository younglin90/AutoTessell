"""Report-only regression for the native_hex mixed-level realization audit."""

from __future__ import annotations

import os

import numpy as np
import pytest

from core.generator.native_hex.octree import _build_nlevel_cells
from scripts.diag_hex_transition_realization1 import run_diagnostic


def test_mixed_level_request_and_builder_output_are_reported_separately() -> None:
    report = run_diagnostic()
    assert report["requested_mixed_levels"] is True
    assert report["requested_level_histogram"] == {"1": 8, "2": 56}
    assert report["observed_builder_cells"] == 57
    assert report["realization"] == "observed"
    assert report["face_incidence_histogram"]["1"] == 87
    assert report["face_incidence_histogram"]["2"] == 132
    assert report["coarse_to_fine_interface_faces"] == 12
    observed = report["observed"]
    assert observed["level_histogram"] == {"1": 1, "2": 56}
    assert observed["n_transition_cells"] == 1
    assert observed["n_transition_faces"] == 3


def test_mixed_level_realization_audit_is_deterministic() -> None:
    first = run_diagnostic()
    second = run_diagnostic()
    assert first == second


def test_mixed_level_quality_census_reports_transition_geometry() -> None:
    report = run_diagnostic()
    quality = report["quality"]
    assert isinstance(quality, dict)
    assert quality["mode"] == "report-only"
    assert quality["n_transition_cells"] == 1
    assert quality["n_transition_faces_reported"] == 3
    assert quality["builder_boundary_face_count"] == 87
    assert quality["writer_cells"] is None
    assert quality["predicted_writer_drop_count"] == 0
    assert quality["writer_drop_prediction_matches_actual"] is None
    assert quality["n_negative_signed_volume"] == 0
    assert quality["all_orientation_free_volume"]["minimum"] == 1.0
    assert quality["transition_cell_orientation_free_volume"]["minimum"] == pytest.approx(8.0)
    assert quality["boundary_skew_threshold"] == 2.0
    assert quality["n_boundary_skew_bad_faces"] == 0
    assert quality["bad_face_transition_owner_rate"] is None
    assert quality["bad_face_transition_vertex_adjacent_rate"] is None


def test_transition_subquads_keep_parent_face_winding() -> None:
    """Split transition faces must retain the outward parent-hex orientation."""
    nfx = nfy = nfz = 4
    points = np.asarray(
        [
            [float(i), float(j), float(k)]
            for i in range(nfx + 1)
            for j in range(nfy + 1)
            for k in range(nfz + 1)
        ],
        dtype=np.float64,
    )
    inside = np.ones((nfx, nfy, nfz), dtype=bool)
    levels = np.full((nfx, nfy, nfz), 2, dtype=np.int8)
    levels[:2, :2, :2] = 1
    metadata: list[dict[str, object]] = []
    previous = os.environ.get("AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION")
    os.environ["AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION"] = "1"
    try:
        cells = _build_nlevel_cells(
            points,
            inside,
            levels,
            2,
            nfx,
            nfy,
            nfz,
            nfy + 1,
            nfz + 1,
            cell_metadata=metadata,
        )
    finally:
        if previous is None:
            os.environ.pop("AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION", None)
        else:
            os.environ["AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION"] = previous

    transition_cells = [cell for cell in cells if len(cell) != 6]
    assert len(transition_cells) == 1
    cell = transition_cells[0]
    cell_vertices = sorted({int(v) for face in cell for v in face})
    cell_center = points[np.asarray(cell_vertices)].mean(axis=0)
    outward_dots = []
    for face in cell:
        face_points = points[np.asarray(face)]
        normal = np.cross(face_points[1] - face_points[0], face_points[2] - face_points[0])
        outward_dots.append(float(np.dot(normal, face_points.mean(axis=0) - cell_center)))
    assert min(outward_dots) > 0.0


def test_partial_covered_block_is_promoted_without_internal_boundary_hole() -> None:
    """A finer leaf must not strand the other cells in its coarse block."""
    nfx = nfy = nfz = 4
    points = np.asarray(
        [
            [float(i), float(j), float(k)]
            for i in range(nfx + 1)
            for j in range(nfy + 1)
            for k in range(nfz + 1)
        ],
        dtype=np.float64,
    )
    inside = np.ones((nfx, nfy, nfz), dtype=bool)
    levels = np.ones((nfx, nfy, nfz), dtype=np.int8)
    levels[0, 0, 0] = 2
    metadata: list[dict[str, object]] = []
    previous = os.environ.get("AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION")
    os.environ["AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION"] = "1"
    try:
        cells = _build_nlevel_cells(
            points,
            inside,
            levels,
            2,
            nfx,
            nfy,
            nfz,
            nfy + 1,
            nfz + 1,
            cell_metadata=metadata,
        )
    finally:
        if previous is None:
            os.environ.pop("AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION", None)
        else:
            os.environ["AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION"] = previous

    face_counts: dict[tuple[int, ...], int] = {}
    for cell in cells:
        for face in cell:
            key = tuple(sorted(int(v) for v in face))
            face_counts[key] = face_counts.get(key, 0) + 1

    # Eight promoted fine cells plus seven untouched coarse cells cover the
    # original 4×4×4 volume without an exposed internal interface.  The
    # coarse/fine surface has 33 boundary quads (fewer than an all-fine grid),
    # but every one must lie on the outer box.
    assert len(cells) == 15
    assert {count for count in face_counts.values()} <= {1, 2}
    boundary_keys = [key for key, count in face_counts.items() if count == 1]
    assert len(boundary_keys) == 33
    assert sum(count == 2 for count in face_counts.values()) == 33
    for key in boundary_keys:
        face_points = points[np.asarray(key)]
        on_outer_box = any(
            np.allclose(face_points[:, axis], 0.0)
            or np.allclose(face_points[:, axis], 4.0)
            for axis in range(3)
        )
        assert on_outer_box
