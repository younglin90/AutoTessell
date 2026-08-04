from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

native_witness = pytest.importorskip("native_quality_witness")
sys.path.insert(0, str(Path(__file__).parent))
from test_native_quality_witness_v3_cpp23 import _authority, _policy  # noqa: E402


def _two_tet_snapshot(reversed_internal: bool = False) -> dict[str, object]:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]],
        dtype=np.float64,
    )
    internal = [0, 1, 2] if reversed_internal else [0, 2, 1]
    faces = [internal, [0, 3, 1], [1, 3, 2], [2, 3, 0],
             [0, 4, 1], [1, 4, 2], [2, 4, 0]]
    lineage = [
        {
            "writer_entity_id": f"writer-face-{index}",
            "source_face_id": f"source-face-{index}",
            "source_edge_id": f"source-edge-{index}",
            "feature": "tet-face",
            "patch": "internal" if index == 0 else "wall",
            "physical_group": "fluid",
            "component": "two-tet",
            "provenance": "authoritative-cad",
            "role": "internal" if index == 0 else "wall",
        }
        for index in range(len(faces))
    ]
    return {
        "points": points,
        "faces": faces,
        "owner": np.array([0, 0, 0, 0, 1, 1, 1], dtype=np.int64),
        "neighbour": np.array([1], dtype=np.int64),
        "face_uids": [f"face-{index}" for index in range(len(faces))],
        "cell_uids": ["cell-0", "cell-1"],
        "lineage": lineage,
        "cell_volumes": [1.0 / 6.0, 1.0 / 6.0],
        "boundary_layer": {
            "actual_layers": 0,
            "positive_thickness": False,
            "lineage_complete": True,
            "wall_edge_lineage_complete": True,
            "minimum_height": 0.0,
        },
    }


def test_v3_signed_internal_orientation_accepts_correct_owner_to_neighbour_winding() -> None:
    policy = _policy(0)
    policy.update({"max_non_orthogonality": 5.0, "max_skewness": 1.0, "max_aspect_ratio": 5.0,
                   "min_volume": 0.1})
    sealed = native_witness.seal_policy_v3(policy)
    result = native_witness.evaluate_v3(_two_tet_snapshot(), _authority(), sealed, "candidate")
    assert result["accepted"] is True, result
    assert result["quality"]["internal_non_orthogonality"]["max"] == pytest.approx(0.0, abs=1.0e-12)


def test_v3_signed_internal_orientation_refuses_reversed_winding() -> None:
    policy = _policy(0)
    policy.update({"max_non_orthogonality": 30.0, "max_skewness": 1.0, "max_aspect_ratio": 5.0,
                   "min_volume": 0.1})
    sealed = native_witness.seal_policy_v3(policy)
    result = native_witness.evaluate_v3(_two_tet_snapshot(reversed_internal=True), _authority(), sealed, "candidate")
    assert result["accepted"] is False
    assert result["reason"] == "quality_threshold_exceeded"
