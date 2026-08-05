"""User wall policy binding tests for topological boundary candidates."""

from pathlib import Path

from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger
from core.layers.native_tet_surface_wall_edge_policy import apply_user_wall_edge_policy


def test_open_boundary_candidates_can_receive_explicit_provisional_wall_policy() -> None:
    ledger = build_stl_edge_ledger(Path("tests/benchmarks/hemisphere_open.stl"))
    first = apply_user_wall_edge_policy(ledger)
    second = apply_user_wall_edge_policy(ledger)
    assert first["status"] == "USER_DECLARED_PROVISIONAL_WALL_EDGE_POLICY"
    assert first["selected_edge_count"] == 48
    assert first["selected_edge_digest"] == second["selected_edge_digest"]
    assert first["feature"] == "unclassified_boundary"
    assert first["feature_authority"] is False
    assert first["wall_edge_authority"] is False
    assert first["release_eligible"] is False


def test_closed_shells_select_no_wall_edges() -> None:
    ledger = build_stl_edge_ledger(Path("tests/benchmarks/cube.stl"))
    policy = apply_user_wall_edge_policy(ledger)
    assert policy["status"] == "USER_DECLARED_PROVISIONAL_WALL_EDGE_POLICY"
    assert policy["selected_edge_count"] == 0
    assert policy["selected_edge_ids"] == []
