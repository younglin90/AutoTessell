"""Fail-closed topology contract for the native-hex writer boundary."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import pytest

from core.generator.native_hex.mesher import _write_polymesh_hex
from core.utils.polymesh_reader import parse_foam_labels


def _two_hex_fixture() -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 1.0),
            (1.0, 1.0, 1.0),
            (0.0, 1.0, 1.0),
            (2.0, 0.0, 0.0),
            (2.0, 1.0, 0.0),
            (2.0, 0.0, 1.0),
            (2.0, 1.0, 1.0),
        ),
        dtype=np.float64,
    )
    hexes = np.asarray(
        (
            (0, 1, 2, 3, 4, 5, 6, 7),
            (1, 8, 9, 2, 5, 10, 11, 6),
        ),
        dtype=np.int64,
    )
    return points, hexes


def _tree_hash(case_dir: Path) -> str:
    digest = hashlib.sha256()
    poly_dir = case_dir / "constant" / "polyMesh"
    for path in sorted(poly_dir.iterdir(), key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_native_hex_writer_preserves_exact_valid_topology_three_runs(
    tmp_path: Path,
) -> None:
    points, hexes = _two_hex_fixture()
    input_hash = hashlib.sha256(points.tobytes() + hexes.tobytes()).hexdigest()
    output_hashes: list[str] = []

    for run in range(3):
        case_dir = tmp_path / f"valid_{run}"
        stats = _write_polymesh_hex(points, hexes, case_dir)
        assert stats == {
            "num_cells": 2,
            "num_points": 12,
            "num_faces": 11,
            "num_internal_faces": 1,
        }
        poly_dir = case_dir / "constant" / "polyMesh"
        assert parse_foam_labels(poly_dir / "owner") == [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1]
        assert parse_foam_labels(poly_dir / "neighbour") == [1]
        boundary = (poly_dir / "boundary").read_text(encoding="utf-8")
        assert "defaultWall" in boundary
        assert re.search(r"nFaces\s+10;", boundary)
        assert re.search(r"startFace\s+1;", boundary)
        output_hashes.append(_tree_hash(case_dir))

    assert len(set(output_hashes)) == 1
    assert hashlib.sha256(points.tobytes() + hexes.tobytes()).hexdigest() == input_hash


@pytest.mark.parametrize("failure", ("degenerate", "non_manifold"))
def test_native_hex_writer_rejects_topology_loss_before_write(
    tmp_path: Path,
    failure: str,
) -> None:
    points, valid_hexes = _two_hex_fixture()
    if failure == "degenerate":
        invalid_hexes = valid_hexes[:1].copy()
        invalid_hexes[0, 4:] = invalid_hexes[0, :4]
        expected = "strict polyMesh contract rejected silent topology loss"
    else:
        invalid_hexes = np.repeat(valid_hexes[:1], 3, axis=0)
        expected = "strict polyMesh contract rejected non-manifold face references"

    input_hash = hashlib.sha256(points.tobytes() + invalid_hexes.tobytes()).hexdigest()
    messages: list[str] = []
    for run in range(3):
        case_dir = tmp_path / f"{failure}_{run}"
        with pytest.raises(ValueError, match=expected) as exc_info:
            _write_polymesh_hex(points, invalid_hexes, case_dir)
        messages.append(str(exc_info.value))
        assert not case_dir.exists()

    assert len(set(messages)) == 1
    assert hashlib.sha256(points.tobytes() + invalid_hexes.tobytes()).hexdigest() == input_hash
