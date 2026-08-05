"""Deterministic offender witnesses for Native Poly signed/quality receipts."""

from __future__ import annotations

import numpy as np
import pytest

from core.utils.native_extensions import load_native_poly_quality_relocation


def _tetra(reversed_face: bool = False, degenerate: bool = False):
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0 if degenerate else 1.0]],
        dtype=np.float64,
    )
    faces = np.asarray(
        [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int64
    )
    if reversed_face:
        faces[0] = [0, 1, 2]
    flat = faces.reshape(-1)
    offsets = np.arange(0, len(flat) + 1, 3, dtype=np.int64)
    owner = np.zeros(4, dtype=np.int64)
    neighbour = np.empty(0, dtype=np.int64)
    locked = np.arange(4, dtype=np.int64)
    return points, flat, offsets, owner, neighbour, locked


def test_worst_witness_is_deterministic_and_id_bound() -> None:
    kernel = load_native_poly_quality_relocation()
    if kernel is None:
        pytest.skip("native_poly_quality_relocation build is unavailable")
    args = _tetra()
    first = dict(kernel.relocate_poly_quality(*args, iterations=0))
    second = dict(kernel.relocate_poly_quality(*args, iterations=0))
    witness = first["worst_witness"]
    assert witness == second["worst_witness"]
    assert witness["before"]["min_signed_volume_cell"] == 0
    assert witness["before"]["min_signed_face_cell"] == 0
    assert witness["before"]["min_signed_face_id"] >= 0
    assert witness["before"]["max_aspect_cell"] == 0
    assert witness["owner_winding_before"]["negative_face_pyramids"] == 0


def test_raw_owner_winding_is_classified_without_overriding_geometry_barrier() -> None:
    kernel = load_native_poly_quality_relocation()
    if kernel is None:
        pytest.skip("native_poly_quality_relocation build is unavailable")
    result = dict(kernel.relocate_poly_quality(*_tetra(reversed_face=True), iterations=0))
    owner = result["worst_witness"]["owner_winding_before"]
    assert owner["negative_face_pyramids"] > 0
    assert owner["owner_winding_only"] is True
    assert result["signed_topology_valid"] is True


def test_geometric_defect_is_not_misclassified_as_owner_winding_only() -> None:
    kernel = load_native_poly_quality_relocation()
    if kernel is None:
        pytest.skip("native_poly_quality_relocation build is unavailable")
    result = dict(kernel.relocate_poly_quality(*_tetra(degenerate=True), iterations=0))
    owner = result["worst_witness"]["owner_winding_before"]
    assert result["signed_topology_valid"] is False
    assert owner["owner_winding_only"] is False
