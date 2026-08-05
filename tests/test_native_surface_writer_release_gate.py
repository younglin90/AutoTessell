from __future__ import annotations

import numpy as np

from core.evaluator.native_surface_bl_strip_writer import (
    write_authoritative_surface_wall_edge_release_candidate,
)


def _authority() -> dict[str, str]:
    return {
        "source_kind": "synthetic_surface",
        "source_sha256": "source-digest",
        "boundary_mapping_sha256": "boundary-digest",
        "physical_group_sha256": "group-digest",
        "provenance": "sealed-ledger",
    }


def test_actual_cpp_writer_receipt_stays_default_off_until_packaged() -> None:
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [-0.5, 0.0, -0.8660254038], [0.5, 0.0, -0.8660254038]],
        dtype=np.float64,
    )
    source = np.asarray([[0, 2, 1]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, -1.0]], dtype=np.float64)
    result = write_authoritative_surface_wall_edge_release_candidate(
        points, source, np.asarray([[11, 0, 1, 0]], dtype=np.int64),
        np.asarray([[[3, 4]]], dtype=np.int64), normals, _authority(),
        [{
            "source_wall_edge": 11, "source_face": 0, "side": "wall",
            "patch": "wall", "feature": "smooth", "physical_group": "fluid_wall",
            "component": "main", "provenance": "writer-ledger",
        }], 1, parameter_digest=None, packaging_receipt=None, explicit_route=True,
    )
    assert result["accepted"] is False
    assert result["reason"] == "candidate_route_default_off"
    assert result["release_eligible"] is False
    assert result["writer_candidate"]["accepted"] is True
    assert result["writer_candidate"]["runtime_route"] == "private_default_off"
