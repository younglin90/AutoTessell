"""C++23 cached Poly adjacency receipt contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.utils.native_extensions import load_native_poly_quality_relocation
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "docs/qa/native_release_campaign_20260803_round093_authority_final/cases/native-poly-gear/run-0"


@pytest.mark.skipif(not CASE.is_dir(), reason="round evidence artifact is unavailable")
def test_native_poly_relocation_builds_deterministic_cached_adjacency() -> None:
    kernel = load_native_poly_quality_relocation()
    if kernel is None:
        pytest.skip("native_poly_quality_relocation build is unavailable")
    poly = CASE / "constant" / "polyMesh"
    points = np.asarray(parse_foam_points_array(poly / "points"), dtype=np.float64)
    faces = parse_foam_faces(poly / "faces")
    owner = np.asarray(parse_foam_labels_array(poly / "owner"), dtype=np.int64)
    neighbour = np.asarray(parse_foam_labels_array(poly / "neighbour"), dtype=np.int64)
    flat = np.asarray([vertex for face in faces for vertex in face], dtype=np.int64)
    offsets = np.zeros(len(faces) + 1, dtype=np.int64)
    offsets[1:] = np.cumsum([len(face) for face in faces], dtype=np.int64)
    locked = np.asarray(
        sorted({vertex for face in faces[len(neighbour) :] for vertex in face}),
        dtype=np.int64,
    )
    first = dict(kernel.relocate_poly_quality(points, flat, offsets, owner, neighbour, locked, 1, 0.001, 0.0))
    second = dict(kernel.relocate_poly_quality(points, flat, offsets, owner, neighbour, locked, 1, 0.001, 0.0))
    assert first["adjacency_cache"]["cached"] is True
    assert first["adjacency_cache"] == second["adjacency_cache"]
    assert first["adjacency_cache"]["face_count"] == len(faces)
    assert first["adjacency_cache"]["cell_count"] > 0
