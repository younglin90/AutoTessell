"""Report-only native_hex transition provenance census tests."""

from __future__ import annotations

import numpy as np

from core.generator.native_hex.octree import build_octree_hex_cells


def _unit_cube_surface() -> tuple[np.ndarray, np.ndarray]:
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
        ],
        dtype=np.float64,
    )
    triangles = np.asarray(
        [
            [0, 1, 2], [0, 2, 3],
            [4, 6, 5], [4, 7, 6],
            [0, 4, 5], [0, 5, 1],
            [1, 5, 6], [1, 6, 2],
            [2, 6, 7], [2, 7, 3],
            [4, 0, 3], [4, 3, 7],
        ],
        dtype=np.int64,
    )
    return points, triangles


def _build(monkeypatch, enabled: bool):
    if enabled:
        monkeypatch.setenv("AUTO_TESSELL_HEX_TRANSITION_PROVENANCE_DIAG", "1")
    else:
        monkeypatch.delenv("AUTO_TESSELL_HEX_TRANSITION_PROVENANCE_DIAG", raising=False)
    points, faces = _unit_cube_surface()
    return build_octree_hex_cells(
        points,
        faces,
        np.zeros(3),
        np.ones(3),
        target_edge=0.25,
        max_cells_per_axis=4,
        n_levels=2,
        refinement_distance_factor=2.0,
    )


def test_provenance_census_is_opt_in_and_mesh_output_is_unchanged(monkeypatch) -> None:
    points_off, cells_off, stats_off = _build(monkeypatch, enabled=False)
    points_on, cells_on, stats_on = _build(monkeypatch, enabled=True)

    assert np.array_equal(points_off, points_on)
    assert cells_off == cells_on
    assert "transition_provenance" not in stats_off

    summary = stats_on["transition_provenance"]
    assert summary["mode"] == "report-only"
    assert summary["n_cell_metadata"] == len(cells_on)
    assert summary["n_output_cells_at_builder"] == len(cells_on)
    assert summary["n_unique_grid_origins"] == len(cells_on)
    assert summary["authoritative_provenance"] is False
    assert summary["missing_authoritative_fields"]


def test_provenance_census_is_deterministic(monkeypatch) -> None:
    _points_a, cells_a, stats_a = _build(monkeypatch, enabled=True)
    _points_b, cells_b, stats_b = _build(monkeypatch, enabled=True)

    assert cells_a == cells_b
    assert stats_a["transition_provenance"] == stats_b["transition_provenance"]
