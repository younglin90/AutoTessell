"""Focused tests for numpy-returning polyMesh parsers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.utils import polymesh_reader as reader
from core.utils.polymesh_reader import (
    parse_foam_labels,
    parse_foam_labels_array,
    parse_foam_points,
    parse_foam_points_array,
)


def test_parse_foam_points_array_matches_list_parser(tmp_path: Path) -> None:
    points_file = tmp_path / "points"
    points_file.write_text(
        "/* header comment */\n3\n(\n(0 1 2)\n// middle comment\n(3.5 -4 5e-1)\n(6 7 8)\n)\n",
        encoding="utf-8",
    )

    points = parse_foam_points_array(points_file)

    assert points.dtype == np.dtype(np.float64)
    assert points.shape == (3, 3)
    assert points.tolist() == parse_foam_points(points_file)
    assert isinstance(parse_foam_points(points_file), list)


def test_parse_foam_labels_array_multiline_matches_list_parser(
    tmp_path: Path,
) -> None:
    labels_file = tmp_path / "owner"
    labels_file.write_text(
        "// owner labels\n4\n(\n0\n2\n2\n5\n)\n",
        encoding="utf-8",
    )

    labels = parse_foam_labels_array(labels_file)

    assert labels.dtype == np.dtype(np.int64)
    assert labels.shape == (4,)
    assert labels.tolist() == [0, 2, 2, 5]
    assert labels.tolist() == parse_foam_labels(labels_file)
    assert isinstance(parse_foam_labels(labels_file), list)


def test_parse_foam_labels_array_same_line_matches_list_parser(
    tmp_path: Path,
) -> None:
    labels_file = tmp_path / "owner"
    labels_file.write_text("4\n(\n0 2 2 5\n)\n", encoding="utf-8")

    labels = parse_foam_labels_array(labels_file)

    assert labels.dtype == np.dtype(np.int64)
    assert labels.shape == (4,)
    assert labels.tolist() == [0, 2, 2, 5]
    assert labels.tolist() == parse_foam_labels(labels_file)


def test_parse_foam_points_array_malformed_is_empty(tmp_path: Path) -> None:
    points_file = tmp_path / "points"
    points_file.write_text("1\n(\n(1 2)\n)\n", encoding="utf-8")

    points = parse_foam_points_array(points_file)

    assert points.dtype == np.dtype(np.float64)
    assert points.shape == (0, 3)
    assert parse_foam_points(points_file) == []


def test_parse_foam_points_array_empty_has_coordinate_shape(tmp_path: Path) -> None:
    points_file = tmp_path / "points"
    points_file.write_text("0\n(\n)\n", encoding="utf-8")

    points = parse_foam_points_array(points_file)

    assert points.dtype == np.dtype(np.float64)
    assert points.shape == (0, 3)
    assert parse_foam_points(points_file) == []


def test_parse_foam_labels_array_empty_is_one_dimensional(tmp_path: Path) -> None:
    labels_file = tmp_path / "neighbour"
    labels_file.write_text("0\n(\n)\n", encoding="utf-8")

    labels = parse_foam_labels_array(labels_file)

    assert labels.dtype == np.dtype(np.int64)
    assert labels.shape == (0,)
    assert parse_foam_labels(labels_file) == []


def test_parse_foam_labels_array_malformed_is_empty(tmp_path: Path) -> None:
    labels_file = tmp_path / "owner"
    labels_file.write_text("not a label list\n", encoding="utf-8")

    labels = parse_foam_labels_array(labels_file)

    assert labels.dtype == np.dtype(np.int64)
    assert labels.shape == (0,)
    assert parse_foam_labels(labels_file) == []


def test_parse_foam_labels_array_falls_back_after_native_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels_file = tmp_path / "owner"
    labels_file.write_text("4\n(\n0 2 2 5\n)\n", encoding="utf-8")

    class FailingNativeMetrics:
        @staticmethod
        def parse_foam_labels_file(_path: Path) -> np.ndarray:
            raise RuntimeError("forced native parser failure")

    monkeypatch.setattr(reader, "_NATIVE_METRICS", FailingNativeMetrics())
    monkeypatch.setattr(reader, "_NATIVE_METRICS_IMPORT_ATTEMPTED", True)

    labels = reader.parse_foam_labels_array(labels_file)

    assert labels.dtype == np.dtype(np.int64)
    assert labels.shape == (4,)
    assert labels.tolist() == [0, 2, 2, 5]
    assert reader.parse_foam_labels(labels_file) == [0, 2, 2, 5]
