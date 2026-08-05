from __future__ import annotations

from pathlib import Path

import pytest

from core.evaluator.native_poly_source_ledger import (
    SCHEMA,
    SourceLedgerRefusal,
    ledger_sha256,
    validate_source_ledger,
)


def _ledger(hashes: dict[str, str]) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": SCHEMA,
        "producer": "authoritative-test-ingress",
        "source_kind": "stl",
        "raw_source_sha256": "f" * 64,
        "importer": {"name": "test-stl-reader", "version": "1"},
        "authority_source": {"status": "source_authored", "id": "test-sidecar", "raw_source_sha256": "f" * 64},
        "lineage_mode": "primal_1_to_1",
        "immutable": True,
        "polymesh_sha256": hashes,
        "source_sha256": __import__("core.evaluator.native_poly_bl_producer_certificate", fromlist=["canonical_sha256"]).canonical_sha256(hashes),
        "authority": {name: True for name in ("source_face", "wall_edge", "patch", "feature", "physical_group", "component")},
        "selected_polymesh_face_indices": [4],
        "source_faces": [{
            "polymesh_face_index": 4,
            "source_face_id": 10,
            "ordered_vertex_ids": [2, 1, 0],
            "canonical_vertex_ids": [0, 1, 2],
            "patch_id": "wall",
            "feature_id": "feature-0",
            "physical_group": "wall-group",
            "component_id": "component-0",
        }],
        "wall_edges": [{"edge_id": 1, "vertex_ids": [0, 1], "incident_source_face_ids": [10]}],
    }
    result["ledger_sha256"] = ledger_sha256(result)
    return result


def test_complete_ledger_validates_and_normalizes() -> None:
    hashes = {name: chr(97 + index) * 64 for index, name in enumerate(("points", "faces", "owner", "neighbour", "boundary"))}
    result = validate_source_ledger(_ledger(hashes), hashes)
    assert result["selected_polymesh_face_indices"] == [4]
    assert result["source_faces"][0]["source_face_id"] == 10


@pytest.mark.parametrize("change, reason", [
    (lambda x: x["authority"].update({"physical_group": False}), "source_ledger_authority_incomplete"),
    (lambda x: x.update({"ledger_sha256": "0" * 64}), "source_ledger_digest_invalid"),
    (lambda x: x["source_faces"][0].update({"polymesh_face_index": 5}), "source_ledger_face_bijection_invalid"),
    (lambda x: x["source_faces"][0].update({"canonical_vertex_ids": [0, 1]}), "source_ledger_face_vertices_mismatch"),
    (lambda x: x["wall_edges"][0].update({"incident_source_face_ids": [999]}), "source_ledger_edge_incidence_invalid"),
    (lambda x: x.update({"source_kind": "obj"}), "source_ledger_source_kind_invalid"),
    (lambda x: x.pop("importer"), "source_ledger_importer_missing"),
    (lambda x: x["authority_source"].update({"status": "display_metadata"}), "source_ledger_authority_source_missing"),
    (lambda x: x.update({"lineage_mode": "dual_1_to_n"}), "source_ledger_dual_lineage_not_supported"),
])
def test_incomplete_or_forged_ledger_refuses(change, reason) -> None:
    hashes = {name: chr(97 + index) * 64 for index, name in enumerate(("points", "faces", "owner", "neighbour", "boundary"))}
    value = _ledger(hashes)
    change(value)
    if reason != "source_ledger_digest_invalid":
        value["ledger_sha256"] = ledger_sha256(value)
    with pytest.raises(SourceLedgerRefusal, match=reason):
        validate_source_ledger(value, hashes)
