"""HEX-PATCH-LAYER-DIAG1 report-only classification tests."""

from __future__ import annotations

import numpy as np

from core.generator.native_hex.patch_layer_diagnostic import (
    analyze_patch_layer_subsets,
)
from core.generator.native_hex.sheet_diagnostic import _face_records
from tests.test_native_hex_sheet_diagnostic import _valid_pillow_shell


def test_strict_patch_layer_rejects_open_single_face_components() -> None:
    points, cells = _valid_pillow_shell()
    report = analyze_patch_layer_subsets("shell", points, cells, log_only=False)

    assert report.n_wall_exact_one_boundary == 6
    assert report.n_wall_one_q == 6
    assert report.n_eligible_s == 6
    assert report.n_eligible_q == 6
    assert report.n_components == 6
    assert report.edge_incidence_histogram == ((1, 24),)
    assert report.global_edge_incidence_histogram == ((2, 12),)
    assert report.n_open_edges == 24
    assert report.n_nonmanifold_edges == 0
    assert report.n_eligible_q_vertices_on_physical_boundary == 0
    assert report.n_valid_subsets == 0
    assert report.n_approved_operations == 0
    assert report.decision == "KILL"
    assert report.next_card is None


def test_same_patch_closed_subset_is_reported_but_not_executed() -> None:
    points, cells = _valid_pillow_shell()
    records = _face_records(cells)
    labels = {
        key: ("wall_patch", "source_surface")
        for key, (_cyclic, owners) in records.items()
        if len(owners) == 1
    }
    points_before = points.copy()
    cells_before = [[list(face) for face in cell] for cell in cells]

    report = analyze_patch_layer_subsets(
        "shell",
        points,
        cells,
        boundary_patch_provenance=labels,
        log_only=False,
    )

    assert report.n_components == 1
    assert report.n_valid_subsets == 1
    assert report.n_predicted_operations == 1
    assert report.n_approved_operations == 1
    assert report.components[0].n_s == 6
    assert report.components[0].n_q == 6
    assert report.components[0].edge_incidence_histogram == ((2, 12),)
    assert report.components[0].n_open_edges == 0
    assert report.components[0].predicted_operation == "pillow"
    assert report.components[0].predicted_new_points == 8
    assert report.components[0].predicted_new_cells == 6
    assert report.decision == "REPORT_ONLY_NEXT_CARD"
    assert report.next_card == "HEX-PATCH-LAYER-OPS1"
    assert np.array_equal(points, points_before)
    assert cells == cells_before


def test_repeat_measurements_are_equal_and_do_not_mutate_inputs() -> None:
    points, cells = _valid_pillow_shell()
    points_before = points.copy()
    cells_before = [[list(face) for face in cell] for cell in cells]

    first = analyze_patch_layer_subsets("shell", points, cells, log_only=False)
    second = analyze_patch_layer_subsets("shell", points, cells, log_only=False)

    assert first == second
    assert np.array_equal(points, points_before)
    assert cells == cells_before
