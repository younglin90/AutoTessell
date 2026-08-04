from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_native_transaction_executor_v1_cpp23 import (  # noqa: E402
    _authority,
    _candidate,
    _corridor,
    _disk,
    _intent,
    executor,
)
from test_native_tet_writer_artifact_bridge_cpp23 import _inputs as _tet_inputs


def _surface_authority() -> dict[str, object]:
    return {
        "source_kind": "synthetic_surface",
        "source_sha256": "a" * 64,
        "boundary_mapping_sha256": "b" * 64,
        "physical_group_sha256": "c" * 64,
        "provenance": "d" * 64,
        "accepted": True,
        "receipt_sealed": True,
        "direct_lineage": True,
        "wall_edge_eligible": True,
        "source_authority_status": "SOURCE_VERIFIED",
    }


def test_actual_cpp_surface_writer_is_called_but_uid_gap_refuses_publish() -> None:
    surface_writer = pytest.importorskip("native_surface_bl_strip_writer")
    transaction = executor.begin_transaction_v1(_intent(1, 401), _authority(), _corridor(1))
    assert transaction["accepted"] is True, transaction
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [-0.5, 0.0, -0.8660254038], [0.5, 0.0, -0.8660254038]],
        dtype=np.float64,
    )
    source_triangles = np.asarray([[0, 2, 1]], dtype=np.int64)
    edges = np.asarray([[11, 0, 1, 0]], dtype=np.int64)
    layer_ids = np.asarray([[[3, 4]]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, -1.0]], dtype=np.float64)
    provenance = [{
        "source_wall_edge": 11, "source_face": 0, "patch": "wall",
        "feature": "smooth", "physical_group": "fluid_wall",
        "component": "main", "provenance": "writer-ledger",
    }]

    def writer(_: dict[str, object]) -> dict[str, object]:
        actual = surface_writer.write_authoritative_surface_bl_strip(
            points, source_triangles, edges, layer_ids, normals,
            _surface_authority(), provenance, 1,
        )
        assert actual["accepted"] is True, actual
        candidate = _candidate(transaction, 1)
        candidate.pop("entity_uids")
        return candidate

    refused = executor.run_writer_transaction_v1(transaction, writer, lambda _: {})
    assert refused["accepted"] is False
    assert refused["reason"] == "executor_provenance_or_uid_lost"
    assert refused["published"] is False


def test_actual_cpp_tet_writer_is_called_but_missing_witness_refuses_publish() -> None:
    tet_writer = pytest.importorskip("native_tet_bl_writer")
    transaction = executor.begin_transaction_v1(_intent(1, 402), _authority(), _corridor(1))
    assert transaction["accepted"] is True, transaction
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    triangles = np.asarray([[0, 1, 2]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0]] * 3, dtype=np.float64)

    def writer(_: dict[str, object]) -> dict[str, object]:
        actual = tet_writer.generate(points, triangles, normals, 1, 0.1, 1.0)
        assert actual["accepted"] is True, actual
        candidate = _candidate(transaction, 1)
        candidate.pop("quality")
        return candidate

    refused = executor.run_writer_transaction_v1(transaction, writer, lambda _: {})
    assert refused["accepted"] is False
    assert refused["reason"] == "executor_candidate_receipt_missing"
    assert refused["published"] is False


def test_actual_surface_writer_contract_can_publish_through_aqte() -> None:
    surface_writer = pytest.importorskip("native_surface_bl_strip_writer")
    transaction = executor.begin_transaction_v1(_intent(1, 403), _authority(), _corridor(1))
    assert transaction["accepted"] is True, transaction
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [-0.5, 0.0, -0.8660254038], [0.5, 0.0, -0.8660254038]],
        dtype=np.float64,
    )
    source_triangles = np.asarray([[0, 2, 1]], dtype=np.int64)
    edges = np.asarray([[11, 0, 1, 0]], dtype=np.int64)
    layer_ids = np.asarray([[[3, 4]]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, -1.0]], dtype=np.float64)
    provenance = [{
        "source_wall_edge": 11, "source_face": 0, "patch": "wall",
        "feature": "smooth", "physical_group": "fluid_wall",
        "component": "main", "provenance": "writer-ledger",
    }]
    first_writer_hash: list[str] = []
    candidate_from_writer: dict[str, object] = {}

    def call_actual() -> dict[str, object]:
        return dict(surface_writer.write_authoritative_surface_bl_strip(
            points, source_triangles, edges, layer_ids, normals,
            _surface_authority(), provenance, 1,
        ))

    def writer(value: dict[str, object]) -> dict[str, object]:
        actual = call_actual()
        assert actual["accepted"] is True, actual
        first_writer_hash.append(actual["writer_artifact_sha256"])
        candidate = _candidate(transaction, 1)
        candidate["entity_uids"] = list(actual["entity_uids"])
        candidate["lineage_rows"] = list(actual["lineage_rows"])
        candidate["quality"] = dict(actual["quality"])
        candidate["topology"] = {
            "duplicate": actual["topology"]["duplicate"],
            "non_manifold": actual["topology"]["non_manifold"],
            "inverted": actual["topology"]["inverted"],
        }
        candidate["boundary_layer"] = dict(actual["boundary_layer"])
        for key in ("artifact_schema", "artifact_bytes", "artifact_byte_size", "writer_artifact_sha256"):
            candidate[key] = actual[key]
        candidate["artifact_sha256"] = executor.canonical_artifact_sha256_v1(candidate)["sha256"]
        candidate_from_writer.clear()
        candidate_from_writer.update(candidate)
        return candidate

    def reread(_: dict[str, object]) -> dict[str, object]:
        second = call_actual()
        assert second["writer_artifact_sha256"] == first_writer_hash[0]

        return _disk(candidate_from_writer)
    published = executor.run_writer_transaction_v1(transaction, writer, reread)
    assert published["accepted"] is True, published
    assert published["published"] is True
    assert published["transaction_state"] == "published"


def test_actual_tet_writer_contract_can_publish_through_aqte() -> None:
    tet_writer = pytest.importorskip("native_tet_bl_writer")
    transaction = executor.begin_transaction_v1(_intent(1, 404), _authority(), _corridor(1))
    assert transaction["accepted"] is True, transaction
    points, triangles, normals, authority = _tet_inputs()
    first_writer_hash: list[str] = []
    candidate_from_writer: dict[str, object] = {}

    def call_actual() -> dict[str, object]:
        return dict(tet_writer.generate_authoritative_artifact(
            points, triangles, normals, 1, 0.1, 1.0, 1.0e-14, authority
        ))

    def writer(_: dict[str, object]) -> dict[str, object]:
        actual = call_actual()
        assert actual["accepted"] is True, actual
        first_writer_hash.append(actual["writer_artifact_sha256"])
        candidate = _candidate(transaction, 1)
        candidate["entity_uids"] = list(actual["entity_uids"])
        candidate["lineage_rows"] = list(actual["lineage_rows"])
        candidate["quality"] = dict(actual["quality"])
        candidate["topology"] = dict(actual["topology"])
        candidate["boundary_layer"] = dict(actual["boundary_layer"])
        for key in ("artifact_schema", "artifact_bytes", "artifact_byte_size", "writer_artifact_sha256"):
            candidate[key] = actual[key]
        candidate["artifact_sha256"] = executor.canonical_artifact_sha256_v1(candidate)["sha256"]
        candidate_from_writer.clear()
        candidate_from_writer.update(candidate)
        return candidate

    def reread(_: dict[str, object]) -> dict[str, object]:
        second = call_actual()
        assert second["writer_artifact_sha256"] == first_writer_hash[0]
        return _disk(candidate_from_writer)

    published = executor.run_writer_transaction_v1(transaction, writer, reread)
    assert published["accepted"] is True, published
    assert published["published"] is True
    assert published["transaction_state"] == "published"



def test_actual_surface_bl0_identity_contract_can_publish_through_aqte() -> None:
    surface_writer = pytest.importorskip("native_surface_bl_strip_writer")
    transaction = executor.begin_transaction_v1(_intent(0, 405), _authority(), None)
    assert transaction["accepted"] is True, transaction
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    triangles = np.asarray([[0, 1, 2]], dtype=np.int64)
    edges = np.asarray([[11, 0, 1, 0]], dtype=np.int64)
    layer_ids = np.empty((0, 1, 2), dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0]], dtype=np.float64)
    provenance = [{
        "source_wall_edge": 11, "source_face": 0, "patch": "wall",
        "feature": "smooth", "physical_group": "fluid_wall",
        "component": "main", "provenance": "writer-ledger",
    }]
    actual = surface_writer.write_authoritative_surface_bl_strip(
        points, triangles, edges, layer_ids, normals,
        _surface_authority(), provenance, 0,
    )
    assert actual["accepted"] is True, actual
    candidate = _candidate(transaction, 0)
    candidate["entity_uids"] = list(actual["entity_uids"])
    candidate["lineage_rows"] = list(actual["lineage_rows"])
    candidate["quality"] = dict(actual["quality"])
    candidate["topology"] = dict(actual["topology"])
    candidate["boundary_layer"] = dict(actual["boundary_layer"])
    for key in ("artifact_schema", "artifact_bytes", "artifact_byte_size", "writer_artifact_sha256"):
        candidate[key] = actual[key]
    candidate["artifact_sha256"] = executor.canonical_artifact_sha256_v1(candidate)["sha256"]
    published = executor.run_writer_transaction_v1(
        transaction, lambda _: candidate, lambda _: _disk(candidate)
    )
    assert published["accepted"] is True, published
    assert published["published"] is True
    assert published["transaction_state"] == "published"
