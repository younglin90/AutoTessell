from __future__ import annotations

import numpy as np
import pytest


partition = pytest.importorskip("native_surface_bl_partition_transaction")


def _square() -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0], [0.5, 0.5, 0.0]],
        dtype=float,
    )
    source = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return points, source


def _lineage(rows: list[tuple[int, str, str]], *, replacement: bool = False) -> list[dict[str, object]]:
    return [
        {
            "output_id": output_id,
            "source_face": source_face,
            "operation": operation,
            "role": role,
            "feature": "smooth",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "square",
            "provenance": f"square#face/{source_face}",
        }
        for output_id, source_face, role in rows
        for operation in ("bl_replacement" if replacement else ("identity" if role == "wall" else "bl_replacement"),)
    ]


def test_surface_partition_bl0_is_exact_identity_and_bl1_replaces_faces() -> None:
    points, source = _square()
    bl0 = partition.validate_surface_partition(
        points, source, source, _lineage([(0, 0, "wall"), (1, 1, "wall")]), 0, True,
    )
    assert bl0["accepted"] is True, bl0
    assert bl0["status"] == "surface_partition_identity_passed"
    output = np.asarray([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]], dtype=np.int64)
    bl1 = partition.validate_surface_partition(
        points, source, output,
        _lineage([(0, 0, "wall"), (1, 0, "inner"), (2, 1, "inner"), (3, 1, "outer")], replacement=True),
        1, True,
    )
    assert bl1["accepted"] is True, bl1.get("reason")
    assert bl1["status"] == "surface_partition_replacement_passed"
    assert bl1["original_surface_prefix_retained"] is False
    assert bl1["quality"]["source_face_coverage"] == 2


def test_surface_partition_rejects_original_prefix_and_duplicate_output() -> None:
    points, source = _square()
    lineage = _lineage([(0, 0, "inner"), (1, 1, "outer")])
    prefix = partition.validate_surface_partition(points, source, source, lineage, 1, True, [0, 1])
    assert prefix["accepted"] is False
    assert prefix["reason"] == "original_surface_prefix_forbidden"
    duplicate = partition.validate_surface_partition(
        points, source, np.asarray([[0, 1, 2], [0, 1, 2]], dtype=np.int64), lineage, 1, True,
    )
    assert duplicate["accepted"] is False
    assert duplicate["reason"] == "output_duplicate_triangle"
