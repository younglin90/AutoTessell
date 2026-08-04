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
    _intent,
    executor,
)


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
