from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_native_tet_persisted_volume_artifact_cpp23 import (  # noqa: E402
    _authority as persisted_authority,
    _write_tetra_poly_mesh,
)
from test_native_transaction_executor_v1_cpp23 import (  # noqa: E402
    _authority,
    _candidate,
    _disk,
    _intent,
    executor,
)


tet_writer = pytest.importorskip("native_tet_bl_writer")


def test_persisted_bl0_artifact_can_publish_through_aqte(tmp_path: Path) -> None:
    poly_mesh = tmp_path / "polyMesh"
    _write_tetra_poly_mesh(poly_mesh)
    transaction = executor.begin_transaction_v1(_intent(0, 406), _authority(), None)
    assert transaction["accepted"] is True, transaction
    first_hash: list[str] = []
    candidate_from_disk: dict[str, object] = {}

    def read_actual() -> dict[str, object]:
        return dict(tet_writer.generate_authoritative_persisted_volume_artifact(
            str(poly_mesh), persisted_authority()
        ))

    def writer(_: dict[str, object]) -> dict[str, object]:
        actual = read_actual()
        assert actual["accepted"] is True, actual
        first_hash.append(actual["writer_artifact_sha256"])
        candidate = _candidate(transaction, 0)
        candidate["entity_uids"] = list(actual["entity_uids"])
        candidate["lineage_rows"] = list(actual["lineage_rows"])
        candidate["quality"] = dict(actual["quality"])
        candidate["topology"] = dict(actual["topology"])
        candidate["boundary_layer"] = dict(actual["boundary_layer"])
        for key in ("artifact_schema", "artifact_bytes", "artifact_byte_size", "writer_artifact_sha256"):
            candidate[key] = actual[key]
        candidate["artifact_sha256"] = executor.canonical_artifact_sha256_v1(candidate)["sha256"]
        candidate_from_disk.clear()
        candidate_from_disk.update(candidate)
        return candidate

    def reread(_: dict[str, object]) -> dict[str, object]:
        second = read_actual()
        assert second["writer_artifact_sha256"] == first_hash[0]
        return _disk(candidate_from_disk)

    published = executor.run_writer_transaction_v1(transaction, writer, reread)
    assert published["accepted"] is True, published
    assert published["published"] is True
    assert published["transaction_state"] == "published"
