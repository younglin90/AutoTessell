"""Wall-edge policy to BL provenance contract tests."""

from pathlib import Path

from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger
from core.layers.native_tet_surface_wall_edge_policy import apply_user_wall_edge_policy
from core.layers.native_tet_wall_edge_provenance_contract import validate_wall_edge_provenance


def test_numeric_only_plan_refuses_and_hash_bound_lineage_is_ready() -> None:
    policy = apply_user_wall_edge_policy(build_stl_edge_ledger(Path("tests/benchmarks/hemisphere_open.stl")))
    edge_id = policy["selected_edge_ids"][0]
    numeric_only = {"provenance": [{"source_wall_edge": 17, "source_face": 0, "side": "left", "layer": 1}]}
    refused = validate_wall_edge_provenance(policy, numeric_only)
    assert refused["status"] == "REFUSED"
    assert refused["reason"] == "missing_policy_edge_identity_or_lineage"

    complete = {
        "provenance": [{
            "policy_edge_id": edge_id, "source_face": 0, "side": "left", "layer": 1,
            "patch": "wall", "feature": "unclassified_boundary", "physical_group": "fluid_wall", "component": "hemisphere",
        }]
    }
    ready = validate_wall_edge_provenance(policy, complete)
    assert ready["status"] == "PROVISIONAL_PROVENANCE_READY"
    assert ready["bound_edge_count"] == 1
    assert ready["release_eligible"] is False


def test_closed_shell_has_no_edge_provenance_to_bind() -> None:
    policy = apply_user_wall_edge_policy(build_stl_edge_ledger(Path("tests/benchmarks/cube.stl")))
    result = validate_wall_edge_provenance(policy, {"provenance": [{"policy_edge_id": "none"}]})
    assert result["status"] == "REFUSED"
    assert result["reason"] == "no_selected_wall_edges"
