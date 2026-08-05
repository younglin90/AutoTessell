from __future__ import annotations

import numpy as np
import pytest

receipt = pytest.importorskip("native_hex_boundary_receipt")


def _payload() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[dict[str, str]]]:
    output_quads = np.asarray(
        [
            [[0.0, 0.0, 0.1], [1.0, 0.0, 0.1], [1.0, 1.0, 0.1], [0.0, 1.0, 0.1]],
            [[0.0, 0.0, 1.1], [1.0, 0.0, 1.1], [1.0, 1.0, 1.1], [0.0, 1.0, 1.1]],
        ],
        dtype=np.float64,
    )
    source_triangles = np.asarray(
        [
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]],
        ],
        dtype=np.float64,
    )
    source_ordinals = np.asarray([0, 1], dtype=np.int64)
    output_mapping = np.asarray([0, 1], dtype=np.int64)
    rows = [
        {"feature": "face-0", "patch": "wall-0", "physical_group": "group-0", "component": "component-0", "provenance": "source-0"},
        {"feature": "face-1", "patch": "wall-1", "physical_group": "group-1", "component": "component-1", "provenance": "source-1"},
    ]
    return output_quads, source_triangles, source_ordinals, output_mapping, rows


def _audit(*, requested_layers: int, actual_layers: int, distance_tolerance: float, mapping: np.ndarray | None = None) -> dict:
    output, source, ordinals, default_mapping, rows = _payload()
    return dict(receipt.audit_native_hex_brep_boundary(
        output,
        source,
        ordinals,
        default_mapping if mapping is None else mapping,
        rows,
        "a" * 64,
        "b" * 64,
        requested_layers,
        actual_layers,
        0.1 if requested_layers else 0.0,
        True,
        True,
        distance_tolerance,
        0.75,
    ))


@pytest.mark.parametrize("layers", [0, 1])
def test_receipt_accepts_identity_and_positive_layer(layers: int) -> None:
    result = _audit(requested_layers=layers, actual_layers=layers, distance_tolerance=0.2)
    assert result["accepted"] is True, result
    assert result["semantic_bijection"] is True
    assert result["mapping_complete"] is True
    assert result["positive_geometry"] is True
    assert result["max_brep_distance"] == pytest.approx(0.1)
    assert result["min_normal_alignment"] == pytest.approx(1.0)
    assert len(result["receipt_sha256"]) == 64


def test_receipt_rejects_distance_and_incomplete_bijection() -> None:
    distance = _audit(requested_layers=1, actual_layers=1, distance_tolerance=0.01)
    missing = _audit(
        requested_layers=1,
        actual_layers=1,
        distance_tolerance=2.0,
        mapping=np.asarray([0, 0], dtype=np.int64),
    )
    assert distance["accepted"] is False
    assert distance["reason"] == "output_brep_distance_or_normal_failed"
    assert missing["accepted"] is False
    assert missing["reason"] == "source_face_semantic_bijection_incomplete"


def test_receipt_accepts_explicit_writer_order_many_to_one() -> None:
    output = np.asarray(
        [
            [[0.0, 0.0, 0.1], [0.5, 0.0, 0.1], [0.5, 0.25, 0.1], [0.0, 0.25, 0.1]],
            [[0.1, 0.5, 0.1], [0.25, 0.5, 0.1], [0.25, 0.75, 0.1], [0.1, 0.75, 0.1]],
            [[0.0, 0.0, 1.1], [1.0, 0.0, 1.1], [1.0, 1.0, 1.1], [0.0, 1.0, 1.1]],
        ],
        dtype=np.float64,
    )
    source = _payload()[1]
    ordinals = np.asarray([0, 1], dtype=np.int64)
    mapping = np.asarray([0, 0, 1], dtype=np.int64)
    rows = _payload()[4]
    writer_rows = [
        {
            "writer_order": 0,
            "output_face_id": 10,
            "source_mesh_face": 20,
            "source_face": 0,
            "feature": "face-0",
            "patch": "wall-0",
            "output_patch": "wall-0",
            "physical_group": "group-0",
            "component": "component-0",
            "provenance": "source-0",
            "direct": True,
        },
        {
            "writer_order": 1,
            "output_face_id": 11,
            "source_mesh_face": 20,
            "source_face": 0,
            "feature": "face-0",
            "patch": "wall-0",
            "output_patch": "wall-0",
            "physical_group": "group-0",
            "component": "component-0",
            "provenance": "source-0",
            "direct": True,
        },
        {
            "writer_order": 2,
            "output_face_id": 12,
            "source_mesh_face": 21,
            "source_face": 1,
            "feature": "face-1",
            "patch": "wall-1",
            "output_patch": "wall-1",
            "physical_group": "group-1",
            "component": "component-1",
            "provenance": "source-1",
            "direct": True,
        },
    ]
    result = dict(receipt.audit_native_hex_brep_boundary(
        output,
        source,
        ordinals,
        mapping,
        rows,
        "a" * 64,
        "b" * 64,
        1,
        1,
        0.1,
        True,
        True,
        0.2,
        0.75,
        writer_rows,
    ))
    assert result["accepted"] is True, result
    assert result["status"] == "pass_native_hex_brep_boundary_receipt_v2"
    assert result["writer_order_bound"] is True
    assert result["mapping_cardinality"] == "explicit_many_to_one"
    assert len(result["writer_order_sha256"]) == 64


def test_receipt_rejects_writer_order_tamper() -> None:
    output, source, ordinals, mapping, rows = _payload()
    writer_rows = [
        {
            "writer_order": 0,
            "output_face_id": 10,
            "source_mesh_face": 20,
            "source_face": 0,
            "feature": "face-0",
            "patch": "wall-0",
            "output_patch": "wall-0",
            "physical_group": "group-0",
            "component": "component-0",
            "provenance": "source-0",
            "direct": True,
        },
        {
            "writer_order": 1,
            "output_face_id": 11,
            "source_mesh_face": 21,
            "source_face": 0,
            "feature": "face-1",
            "patch": "wall-1",
            "output_patch": "wall-1",
            "physical_group": "group-1",
            "component": "component-1",
            "provenance": "source-1",
            "direct": True,
        },
    ]
    result = dict(receipt.audit_native_hex_brep_boundary(
        output,
        source,
        ordinals,
        mapping,
        rows,
        "a" * 64,
        "b" * 64,
        1,
        1,
        0.1,
        True,
        True,
        0.2,
        0.75,
        writer_rows,
    ))
    assert result["accepted"] is False
    assert result["reason"] == "writer_order_binding_mismatch"
