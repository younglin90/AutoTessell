"""Signed-volume barrier tests for the Native Poly C++ transaction."""

from __future__ import annotations

import numpy as np
import pytest

from core.utils.native_extensions import load_native_poly_quality_relocation


def _tetra_inputs(reversed_face: bool = False):
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    faces = np.asarray(
        [[0, 1, 2], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int64
    )
    if not reversed_face:
        faces[0] = [0, 2, 1]
    flat = faces.reshape(-1)
    offsets = np.arange(0, len(flat) + 1, 3, dtype=np.int64)
    owner = np.zeros(len(faces), dtype=np.int64)
    neighbour = np.empty(0, dtype=np.int64)
    locked = np.arange(4, dtype=np.int64)
    return points, flat, offsets, owner, neighbour, locked


def test_signed_orientation_cache_accepts_outward_tetra() -> None:
    kernel = load_native_poly_quality_relocation()
    if kernel is None:
        pytest.skip("native_poly_quality_relocation build is unavailable")
    result = dict(kernel.relocate_poly_quality(*_tetra_inputs(), iterations=0))
    assert result["signed_volume_barrier"] is True
    assert result["orientation_cache"]["primary"] == "geometry_outward_face_centroid"
    assert result["metrics_after"]["min_signed_volume"] > 0.0
    assert result["accepted"] is False
    assert result["reason"] == "no_strict_quality_improvement"


def test_inconsistent_raw_face_winding_is_normalized_before_transaction() -> None:
    kernel = load_native_poly_quality_relocation()
    if kernel is None:
        pytest.skip("native_poly_quality_relocation build is unavailable")
    result = dict(kernel.relocate_poly_quality(
        *_tetra_inputs(reversed_face=True), iterations=1, relax=1.0
    ))
    assert result["signed_volume_barrier"] is True
    assert result["metrics_after"]["min_signed_volume"] > 0.0
    assert result["metrics_after"]["min_signed_face_pyramid_volume"] > 0.0
    assert result["accepted"] is False
    assert result["reason"] == "no_strict_quality_improvement"
