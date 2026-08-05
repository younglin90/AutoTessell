from __future__ import annotations

from core.evaluator.native_gate4_lineage import build_lineage_witness, validate_lineage_witness


def _manifest() -> dict:
    return {
        "entity_kind": "stl_facet",
        "rows": [
            {"source_id": 0, "feature": "f0", "patch": "wall", "physical_group": "fluid", "component": "body", "provenance": "p0"},
            {"source_id": 1, "feature": "f1", "patch": "wall", "physical_group": "fluid", "component": "body", "provenance": "p1"},
        ],
    }


def _record(uid: str, source_id: int, *, role: str = "wall", operation: str = "identity", parent: str | None = None, layer: int = 0) -> dict:
    row = _manifest()["rows"][source_id]
    return {
        "output_uid": uid, "entity_scope": "output_boundary", "source_ref": {"kind": "stl_facet", "id": source_id},
        "semantic_owner_id": f"sem/stl_facet/{source_id}", "operation": operation, "boundary_role": role,
        "layer_index": layer, "parent_uid": parent, **{key: row[key] for key in ("feature", "patch", "physical_group", "component", "provenance")},
    }


def test_bl0_identity_and_source_to_output_fanout_are_valid() -> None:
    records = [_record("out-0", 0), _record("out-1a", 1), _record("out-1b", 1)]
    witness = build_lineage_witness(records, requested_layers=0, actual_layers=0, baseline_tree_sha256="a" * 64, output_tree_sha256="a" * 64)
    result = validate_lineage_witness(witness, _manifest(), actual_output_uids=["out-0", "out-1a", "out-1b"])
    assert result["accepted"] is True, result
    assert result["source_to_output_fanout"]["sem/stl_facet/1"] == 2


def test_lineage_rejects_duplicate_uid_owner_ambiguity_and_tamper() -> None:
    records = [_record("out", 0), _record("out", 1)]
    witness = build_lineage_witness(records, requested_layers=0, actual_layers=0, baseline_tree_sha256="a" * 64, output_tree_sha256="a" * 64)
    witness["records"][1]["semantic_owner_id"] = "sem/stl_facet/0"
    result = validate_lineage_witness(witness, _manifest(), actual_output_uids=["out"])
    assert result["accepted"] is False
    assert "output_uid_duplicate" in result["reasons"]
    assert "lineage_digest_mismatch" in result["reasons"]


def test_positive_bl_requires_role_chain_and_monotone_same_owner_parent() -> None:
    records = [
        _record("wall", 0, role="wall", operation="bl_extrude", layer=0),
        _record("inner", 0, role="inner", operation="bl_extrude", parent="wall", layer=1),
        _record("outer", 0, role="outer", operation="transition", parent="inner", layer=2),
    ]
    witness = build_lineage_witness(records, requested_layers=2, actual_layers=2, baseline_tree_sha256="a" * 64, output_tree_sha256="b" * 64)
    result = validate_lineage_witness(witness, _manifest(), actual_output_uids=["wall", "inner", "outer"])
    assert result["accepted"] is True, result


def test_lineage_rejects_parent_owner_switch_and_sidewall_guess() -> None:
    records = [_record("a", 0, role="wall"), _record("b", 1, role="sidewall", parent="a")]
    witness = build_lineage_witness(records, requested_layers=1, actual_layers=1, baseline_tree_sha256="a" * 64, output_tree_sha256="b" * 64)
    result = validate_lineage_witness(witness, _manifest(), actual_output_uids=["a", "b"])
    assert result["accepted"] is False
    assert "sidewall_source_ambiguous" in result["reasons"]
    assert "parent_owner_switch" in result["reasons"]
