from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_BUILD = Path(__file__).resolve().parents[1] / "auto_tessell_core" / "build"
if str(_BUILD) not in sys.path:
    sys.path.insert(0, str(_BUILD))

from core.generator.tier_native_tet import _runner


def test_live_tet_runner_receipt_route_reaches_real_harness(tmp_path: Path, monkeypatch) -> None:
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    faces = np.asarray(
        [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], dtype=np.int64
    )
    for key, value in {
        "AUTO_TESSELL_NATIVE_TET_CELL_REBUDGET": "0",
        "AUTO_TESSELL_P4C_PYTETWILD": "0",
        "AUTO_TESSELL_P4C_NUM_OPT_ITER": "1",
        "AUTO_TESSELL_CVT3D_OFF": "1",
        "AUTO_TESSELL_STELLAR_KLINGNER": "0",
        "AUTO_TESSELL_VVV2_QUEUE": "0",
        "AUTO_TESSELL_RRR2_TARGETED": "0",
    }.items():
        monkeypatch.setenv(key, value)
    receipt = {
        "accepted": True,
        "receipt_sealed": True,
        "quality_policy": {
            "max_non_orthogonality": 50.0,
            "max_skewness": 0.5,
            "max_aspect_ratio": 20.0,
            "policy_sha256": "c" * 64,
        },
        "runtime_route": "default_off",
        "receipt_digest": "tet-receipt-live-v1",
        "source_sha256": "a" * 64,
        "semantic_ledger_sha256": "b" * 64,
        "canonical_source_vertices": points.tolist(),
        "canonical_source_faces": faces.tolist(),
        "positive_bl_volume_partition_available": False,
        "interface_triangles": [
            {
                "source_face": str(index),
                "output_face": f"out-{index}",
                "triangle": triangle.tolist(),
                "feature": "smooth",
                "patch": "wall",
                "physical_group": "fluid-wall",
                "component": "tetra",
                "provenance": f"surface#{index}",
            }
            for index, triangle in enumerate(faces)
        ],
    }
    result = _runner(
        points,
        faces,
        tmp_path,
        input_config={"surface_receipt": receipt},
        max_iter=1,
        seed_density=4,
    )
    assert result.route == "native_tet_production_receipt"
    assert result.contract == "receipt_locked_ingress"
    assert result.contract_details["receipt_ingress"]["accepted"] is True
    assert result.contract_details["output_readback"]["accepted"] is True
    assert result.contract_details["publication_eligible"] is False
    assert result.contract_details["output_readback"]["source_face_count"] == len(faces)
    assert result.contract_details["stage"]["published"] is True
    assert result.contract_details["stage"]["destination_audit"]["disk_graph"]["accepted"] is True
    assert result.contract_details["stage"]["destination_audit"]["disk_graph"]["source_output_exact"] is True
    assert result.contract_details["stage"]["audit"]["accepted"] is True
    assert result.contract_details["stage"]["publish"]["atomic"] is True
