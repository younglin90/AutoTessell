from __future__ import annotations

import numpy as np
import pytest

from core.generator.native_hex.occt_xde_ingress import (
    canonical_semantic_ledger_digest,
)


def _rows() -> list[dict[str, object]]:
    return [
        {
            "source_face": 0,
            "feature": "face-0",
            "patch": "wall-0",
            "physical_group": "group-0",
            "component": "component-0",
            "provenance": "source-0",
        },
        {
            "source_face": 1,
            "feature": "face-1",
            "patch": "wall-1",
            "physical_group": "group-1",
            "component": "component-1",
            "provenance": "source-1",
        },
    ]


def _receipt_payload() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    output = np.asarray(
        [
            [[0.0, 0.0, 0.1], [1.0, 0.0, 0.1], [1.0, 1.0, 0.1], [0.0, 1.0, 0.1]],
            [[0.0, 0.0, 1.1], [1.0, 0.0, 1.1], [1.0, 1.0, 1.1], [0.0, 1.0, 1.1]],
        ],
        dtype=np.float64,
    )
    source = np.asarray(
        [
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]],
        ],
        dtype=np.float64,
    )
    return (
        output,
        source,
        np.asarray([0, 1], dtype=np.int64),
        np.asarray([0, 1], dtype=np.int64),
    )


def test_cpp_and_python_semantic_ledger_digest_are_identical() -> None:
    ingress = pytest.importorskip("native_hex_occt_xde_ingress")
    rows = _rows()
    result = dict(ingress.semantic_ledger_digest(rows))
    assert result["accepted"] is True, result
    assert result["semantic_ledger_sha256"] == canonical_semantic_ledger_digest(rows)


def test_cpp_semantic_ledger_rejects_ordinal_tamper() -> None:
    ingress = pytest.importorskip("native_hex_occt_xde_ingress")
    rows = _rows()
    rows[1]["source_face"] = 0
    result = dict(ingress.semantic_ledger_digest(rows))
    assert result["accepted"] is False
    assert result["reason"] == "semantic_source_face_not_canonical"


def test_boundary_receipt_v3_binds_certificate_and_semantic_digest() -> None:
    receipt = pytest.importorskip("native_hex_boundary_receipt")
    output, source, ordinals, mapping = _receipt_payload()
    rows = _rows()
    semantic_digest = canonical_semantic_ledger_digest(rows)
    result = dict(
        receipt.audit_native_hex_brep_boundary(
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
            None,
            "c" * 64,
            semantic_digest,
            "d" * 64,
        )
    )
    assert result["accepted"] is True, result
    assert result["status"] == "pass_native_hex_brep_boundary_receipt_v3"
    assert result["ingress_certificate_sha256"] == "c" * 64
    assert result["semantic_ledger_sha256"] == semantic_digest


def test_boundary_receipt_v3_refuses_semantic_tamper() -> None:
    receipt = pytest.importorskip("native_hex_boundary_receipt")
    output, source, ordinals, mapping = _receipt_payload()
    rows = _rows()
    digest = canonical_semantic_ledger_digest(rows)
    rows[0]["patch"] = "tampered"
    result = dict(
        receipt.audit_native_hex_brep_boundary(
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
            None,
            "c" * 64,
            digest,
            "d" * 64,
        )
    )
    assert result["accepted"] is False
    assert result["reason"] == "semantic_ledger_digest_mismatch"
