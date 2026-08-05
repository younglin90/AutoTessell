from __future__ import annotations

import numpy as np
import pytest


consumer = pytest.importorskip("native_tet_surface_boundary_receipt_consumer")


def _receipt() -> dict[str, object]:
    return {
        "accepted": True,
        "receipt_sealed": True,
        "runtime_route": "default_off",
        "receipt_digest": "surface-receipt-v1",
        "source_sha256": "source-sha256",
        "canonical_source_face_ids": [3],
        "interface_triangles": [
            {
                "source_face": "3",
                "output_face": "out-3",
                "triangle": [0, 1, 2],
                "feature": "smooth",
                "patch": "wall",
                "physical_group": "fluid-wall",
                "component": "hemisphere",
                "provenance": "surface#3",
            }
        ],
    }


def _binding() -> list[dict[str, object]]:
    return [
        {
            "source_face": "3",
            "output_face": "out-3",
            "volume_boundary_face": "tet-face-0",
            "volume_face_vertices": [0, 1, 2],
            "feature": "smooth",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "hemisphere",
            "provenance": "surface#3",
        }
    ]


def _tet_boundary_faces() -> np.ndarray:
    return np.asarray([[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]], dtype=np.int64)


def test_actual_tet_boundary_receipt_consumption_is_authority_bound() -> None:
    result = consumer.consume_surface_boundary_receipt(_receipt(), _binding(), _tet_boundary_faces(), 1)
    assert result["accepted"] is True, result.get("reason")
    assert result["reason"] == "actual_tet_boundary_receipt_verified"
    assert result["interface_count"] == 1
    assert result["tet_boundary_face_count"] == 4
    assert result["publication_eligible"] is False


def test_tet_boundary_receipt_refuses_geometry_or_source_tampering() -> None:
    bad_binding = _binding()
    bad_binding[0]["volume_face_vertices"] = [0, 1, 3]
    result = consumer.consume_surface_boundary_receipt(_receipt(), bad_binding, _tet_boundary_faces(), 1)
    assert result["accepted"] is False
    assert result["reason"] == "tet_boundary_interface_geometry_mismatch"
    bad_receipt = _receipt()
    bad_receipt["source_sha256"] = ""
    result = consumer.consume_surface_boundary_receipt(bad_receipt, _binding(), _tet_boundary_faces(), 1)
    assert result["accepted"] is False
    assert result["reason"] == "surface_receipt_incomplete"
