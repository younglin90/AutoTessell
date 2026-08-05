from __future__ import annotations

import numpy as np

from core.evaluator.native_surface_writer_artifact import stage_native_surface_strip_evidence


def _authority() -> dict[str, object]:
    return {
        "source_kind": "synthetic_surface", "source_sha256": "a" * 64,
        "boundary_mapping_sha256": "b" * 64, "physical_group_sha256": "c" * 64,
        "provenance": "d" * 64, "accepted": True, "receipt_sealed": True,
        "direct_lineage": True, "wall_edge_eligible": True,
        "source_authority_status": "SOURCE_VERIFIED",
    }


def test_actual_cpp_writer_is_staged_as_private_deterministic_evidence(tmp_path):
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [-0.5, 0.0, -0.8660254038], [0.5, 0.0, -0.8660254038]], dtype=np.float64,
    )
    result = stage_native_surface_strip_evidence(
        tmp_path / "surface", points, np.asarray([[0, 2, 1]], dtype=np.int64),
        np.asarray([[11, 0, 1, 0]], dtype=np.int64), np.asarray([[[3, 4]]], dtype=np.int64),
        np.asarray([[0.0, 0.0, -1.0]], dtype=np.float64), _authority(), [{
            "source_wall_edge": 11, "source_face": 0, "side": "wall",
            "patch": "wall", "feature": "smooth", "physical_group": "fluid_wall",
            "component": "main", "provenance": "writer-ledger",
        }], 1,
    )
    assert result.published is True
    assert len(result.runs) == 3
    assert all(run["runtime_route"] == "private_default_off" for run in result.runs)
    assert result.artifact_fingerprint and result.artifact_fingerprint["entry_count"] == 1
