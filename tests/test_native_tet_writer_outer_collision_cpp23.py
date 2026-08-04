from __future__ import annotations

import numpy as np

import native_tet_bl_admission as native

from tests.test_native_tet_bl_admission_cpp23 import _authority
from tests.test_native_tet_writer_outer_admission_cpp23 import _outer_ledger, _sealed_policy


def test_writer_owned_outer_surface_reports_deterministic_collision_evidence() -> None:
    base = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    points = np.vstack([base, base + np.asarray([0.2, 0.2, 0.2])])
    tets = np.asarray([[0, 1, 2, 3], [4, 5, 6, 7]], dtype=np.int64)
    policy = _sealed_policy()
    params = dict(
        policy["input_parameters"],
        min_signed_volume=0.001,
        min_scaled_jacobian=0.01,
        max_skewness=0.9,
        max_non_orthogonality=90.0,
        max_aspect_ratio=10.0,
    )
    policy["input_parameters"] = params
    policy["input_parameters_sha256"] = native.canonical_input_parameters_sha256(params)
    ledger = _outer_ledger()
    ledger["outer_face_authority"] = [
        {
            "source_face_id": f"face-{index}",
            "source_edge_id": f"edge-{index}",
            "feature": "feature-0",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "component-0",
            "provenance": "source-cad-0",
        }
        for index in range(8)
    ]

    result = dict(native.admit_writer_owned_outer_surface(
        points, tets, policy, 1, ledger, _authority()
    ))

    assert result["accepted"] is False
    assert result["refusal_stage"] == "collision"
    assert result["refusal_reason"] == "writer_owned_outer_surface_self_intersection"
    assert result["collision_broad_phase_pairs"] > 0
    assert result["collision_narrow_phase_hits"] > 0
    assert result["collision_first_pair"] is not None
    assert len(result["collision_digest"]) == 64
