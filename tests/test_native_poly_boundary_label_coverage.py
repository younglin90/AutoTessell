"""Fail-closed boundary-label coverage for the native Poly dual."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.generator.native_poly import tet_to_poly_dual
from core.utils.polymesh_reader import parse_foam_boundary

_EXPECTED_HASHES = (
    "fdab8bddd008ad6fc003427a6a153c4ae4898ddb540dee684cc2be2134a25957",
    "e34a8b7e92d198a658ef33227d71ecbba55dba2c9c8ebd66c9db16fa297c854c",
    "2f3f3f3e97e28db3e2c4ad74ec0b55690bb399ab97098b15d97172ae488873ca",
    "8d80df3c7b13898717eb271b3913d3e577179c3f85e9441418159002f9374873",
    "d29e59ca7dede8b5d1b3ecd5e7858923ab3e5ca459dafcf1d8b2ebd0281d88c0",
)
_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")


def _classified_bipyramid() -> tuple[
    np.ndarray,
    np.ndarray,
    dict[tuple[int, int, int], tuple[str, str]],
]:
    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.3, 0.3, 1.0),
            (0.3, 0.3, -1.0),
        ),
        dtype=np.float64,
    )
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)
    labels = {
        (0, 1, 3): ("source_high", "wall"),
        (1, 2, 3): ("source_high", "wall"),
        (0, 2, 3): ("source_high", "wall"),
        (0, 1, 4): ("source_low", "patch"),
        (1, 2, 4): ("source_low", "patch"),
        (0, 2, 4): ("source_low", "patch"),
    }
    return points, tets, labels


def _hashes(case_dir: Path) -> tuple[str, ...]:
    poly_dir = case_dir / "constant" / "polyMesh"
    return tuple(
        hashlib.sha256((poly_dir / name).read_bytes()).hexdigest() for name in _POLYMESH_FILES
    )


def _patch_contract(case_dir: Path) -> tuple[tuple[str, str, int, int], ...]:
    entries = parse_foam_boundary(case_dir / "constant" / "polyMesh" / "boundary")
    return tuple(
        (
            str(entry["name"]),
            str(entry["type"]),
            int(entry["startFace"]),
            int(entry["nFaces"]),
        )
        for entry in entries
    )


def test_partial_boundary_face_labels_mapping_fails_closed_three_times(
    tmp_path: Path,
) -> None:
    points, tets, complete = _classified_bipyramid()
    partial = dict(list(complete.items())[:3])
    points_before = points.copy()
    tets_before = tets.copy()
    expected = (
        "boundary entity classification failed: boundary_face_labels must cover "
        "every extracted boundary triangle; missing canonical triangles: "
        "((0, 1, 4), (0, 2, 4), (1, 2, 4))"
    )

    for run in range(3):
        case_dir = tmp_path / f"partial-labels-{run}"
        result = tet_to_poly_dual(
            points,
            tets,
            case_dir,
            boundary_face_labels=partial,
        )
        assert not result.success
        assert result.message == expected
        assert not case_dir.exists()

    assert np.array_equal(points, points_before)
    assert np.array_equal(tets, tets_before)


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "argument", ("boundary_face_labels", "boundary_face_entities")
)
def test_complete_boundary_mapping_preserves_frozen_provenance_three_times(
    tmp_path: Path,
    argument: str,
) -> None:
    points, tets, complete = _classified_bipyramid()
    expected_patches = (
        ("source_high", "wall", 9, 9),
        ("source_low", "patch", 18, 9),
    )

    for run in range(3):
        case_dir = tmp_path / f"{argument}-{run}"
        kwargs: dict[str, Mapping[tuple[int, int, int], Any]] = {argument: complete}
        result = tet_to_poly_dual(points, tets, case_dir, **kwargs)
        assert result.success, result.message
        assert _hashes(case_dir) == _EXPECTED_HASHES
        assert _patch_contract(case_dir) == expected_patches


def test_boundary_label_mapping_insertion_order_does_not_change_output(
    tmp_path: Path,
) -> None:
    points, tets, complete = _classified_bipyramid()
    reversed_labels = dict(reversed(tuple(complete.items())))

    case_dir = tmp_path / "reversed-labels"
    result = tet_to_poly_dual(
        points,
        tets,
        case_dir,
        boundary_face_labels=reversed_labels,
    )

    assert result.success, result.message
    assert _hashes(case_dir) == _EXPECTED_HASHES


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "classification", ("none", "sequence", "classifier")
)
def test_non_mapping_boundary_classification_paths_remain_supported(
    tmp_path: Path,
    classification: str,
) -> None:
    points, tets, _complete = _classified_bipyramid()
    case_dir = tmp_path / classification
    kwargs: dict[str, Any] = {}
    expected_names = ("defaultWall",)
    if classification == "sequence":
        kwargs["boundary_face_labels"] = [("sequence_patch", "wall")] * 6
        expected_names = ("sequence_patch",)
    elif classification == "classifier":

        def classifier(_triangle: tuple[int, int, int], _points: np.ndarray) -> tuple[str, str]:
            return "classifier_patch", "wall"

        kwargs["boundary_face_classifier"] = classifier
        expected_names = ("classifier_patch",)

    result = tet_to_poly_dual(points, tets, case_dir, **kwargs)

    assert result.success, result.message
    assert (
        tuple(
            entry["name"]
            for entry in parse_foam_boundary(case_dir / "constant" / "polyMesh" / "boundary")
        )
        == expected_names
    )
