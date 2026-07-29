"""HEX-TRANSITION-DIAG1 input-audit and geometry-baseline tests."""

from __future__ import annotations

import numpy as np

from core.generator.native_hex.transition_diagnostic import audit_transition_inputs


def _unit_cube() -> tuple[np.ndarray, list[list[list[int]]]]:
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
            [0.0, 1.0, 1.0],
        ]
    )
    cell = [
        [0, 3, 2, 1],
        [4, 5, 6, 7],
        [0, 1, 5, 4],
        [3, 7, 6, 2],
        [0, 4, 7, 3],
        [1, 2, 6, 5],
    ]
    return points, [cell]


def test_transition_audit_blocks_without_lineage_metadata() -> None:
    points, cells = _unit_cube()
    points_before = points.copy()
    cells_before = [[list(face) for face in cell] for cell in cells]

    report = audit_transition_inputs("cube", points, cells)

    assert report.status == "BLOCKED"
    assert len(report.blocker_reasons) == 4
    assert any("transition-chain IDs" in reason for reason in report.blocker_reasons)
    assert report.patch_layer.n_physical_boundary_faces == 6
    assert report.patch_layer.decision == "KILL"
    assert np.array_equal(points, points_before)
    assert cells == cells_before


def test_geometry_baselines_are_measured_without_transition_claims() -> None:
    points, cells = _unit_cube()

    report = audit_transition_inputs("cube", points, cells)

    assert report.all_face_warpage == report.boundary_face_warpage
    assert report.all_face_warpage.minimum == 0.0
    assert report.all_face_warpage.maximum == 0.0
    assert report.cell_local_scaled_jacobian_magnitude.minimum == 1.0
    assert report.cell_local_scaled_jacobian_magnitude.maximum == 1.0
    assert report.patch_provenance_mode.endswith("(reconstructed)")
