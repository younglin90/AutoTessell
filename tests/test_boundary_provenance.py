"""Tests for multi-surface boundary patch provenance."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.utils.boundary_provenance import (
    SourceSurfacePatchClassifier,
    source_surface_patch_names,
)
from core.utils.stl_writer import write_stl_binary


def _write_triangle(path: Path, z: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    vertices = np.array(
        [[0.0, 0.0, z], [2.0, 0.0, z], [0.0, 2.0, z]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    result = write_stl_binary(vertices, faces, path)
    assert result.success, result.message


def test_source_patch_names_sanitize_stems_and_preserve_order() -> None:
    paths = [Path("Wing body-v2.stl"), Path("42.inlet!.stl"), Path("---.stl")]

    assert source_surface_patch_names(paths) == [
        "source_0_Wing_body_v2",
        "source_1_42_inlet",
        "source_2_surface",
    ]


def test_duplicate_stems_still_produce_unique_names() -> None:
    names = source_surface_patch_names(
        [Path("first/part.stl"), Path("second/part.stl")]
    )

    assert names == ["source_0_part", "source_1_part"]
    assert len(names) == len(set(names))


def test_classify_many_uses_nearest_source_surface(tmp_path: Path) -> None:
    low = tmp_path / "low.stl"
    high = tmp_path / "high.stl"
    _write_triangle(low, 0.0)
    _write_triangle(high, 10.0)
    classifier = SourceSurfacePatchClassifier([low, high])
    vertices = np.array(
        [
            [0.1, 0.1, 0.1],
            [0.4, 0.1, 0.1],
            [0.1, 0.4, 0.1],
            [0.1, 0.1, 9.9],
            [0.4, 0.1, 9.9],
            [0.1, 0.4, 9.9],
        ],
        dtype=np.float64,
    )

    labels = classifier.classify_many([[0, 1, 2], [3, 4, 5]], vertices)

    assert labels == [("source_0_low", "wall"), ("source_1_high", "wall")]
    assert classifier([3, 4, 5], vertices) == ("source_1_high", "wall")


def test_equal_distance_tie_selects_first_source(tmp_path: Path) -> None:
    source = tmp_path / "same.stl"
    _write_triangle(source, 0.0)
    classifier = SourceSurfacePatchClassifier([source, source])
    vertices = np.array(
        [[0.1, 0.1, 1.0], [0.4, 0.1, 1.0], [0.1, 0.4, 1.0]],
        dtype=np.float64,
    )

    assert classifier([0, 1, 2], vertices) == ("source_0_same", "wall")


def test_empty_and_invalid_inputs_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        SourceSurfacePatchClassifier([])
    with pytest.raises(FileNotFoundError):
        SourceSurfacePatchClassifier([tmp_path / "missing.stl"])


def test_empty_face_batch_is_valid(tmp_path: Path) -> None:
    source = tmp_path / "source.stl"
    _write_triangle(source, 0.0)
    classifier = SourceSurfacePatchClassifier([source])

    assert classifier.classify_many([], np.zeros((0, 3), dtype=np.float64)) == []
    with pytest.raises(ValueError, match="at least three"):
        classifier.classify_many([[0, 1]], np.zeros((2, 3), dtype=np.float64))
