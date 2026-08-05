"""Contracts for the C++23 Native Poly local BL front proposal kernel."""

from __future__ import annotations

import numpy as np
import pytest


kernel = pytest.importorskip("native_poly_bl_local_front_qopt")


def _tetra_probe() -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    original = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    candidate = original.copy()
    candidate[3] = [0.0, 0.0, -0.5]
    faces = [
        [1, 2, 3],
        [0, 3, 2],
        [0, 1, 3],
        [0, 2, 1],
    ]
    flat = np.asarray([vertex for face in faces for vertex in face], dtype=np.int64)
    offsets = np.asarray([0, 3, 6, 9, 12], dtype=np.int64)
    return original, candidate, {
        "flat": flat,
        "offsets": offsets,
        "owner": np.zeros(4, dtype=np.int64),
        "neighbour": np.empty(0, dtype=np.int64),
        "base_vertices": np.asarray([1, 3], dtype=np.int64),
        "layer_points": np.asarray([1, 3], dtype=np.int64),
    }


def _run(original: np.ndarray, candidate: np.ndarray, mesh: dict[str, np.ndarray]) -> dict:
    return dict(
        kernel.optimize_local_front(
            original,
            candidate,
            mesh["flat"],
            mesh["offsets"],
            mesh["owner"],
            mesh["neighbour"],
            mesh["base_vertices"],
            mesh["layer_points"],
            1,
            8,
            0.03125,
        )
    )


def test_local_front_scales_only_the_failing_star_and_is_deterministic() -> None:
    original, candidate, mesh = _tetra_probe()

    first = _run(original, candidate, mesh)
    second = _run(original, candidate, mesh)

    assert first["accepted"] is True
    assert first["n_input_inverted_cells"] == 1
    assert first["n_remaining_inverted_cells"] == 0
    assert first["n_scaled_points"] == 1
    assert np.asarray(first["alpha"])[0] == 1.0
    assert 0.0 < np.asarray(first["alpha"])[1] < 1.0
    assert first["topology_untouched"] is True
    assert first["source_points_untouched"] is True
    assert first["deterministic"] is True
    np.testing.assert_array_equal(first["candidate_points"], second["candidate_points"])
    np.testing.assert_array_equal(first["alpha"], second["alpha"])


def test_local_front_is_an_identity_on_a_healthy_candidate() -> None:
    original, _candidate, mesh = _tetra_probe()

    result = _run(original, original.copy(), mesh)

    assert result["accepted"] is True
    assert result["n_input_inverted_cells"] == 0
    assert result["n_remaining_inverted_cells"] == 0
    assert result["n_scaled_points"] == 0
    np.testing.assert_array_equal(result["candidate_points"], original)
    np.testing.assert_array_equal(result["alpha"], np.ones(2))
