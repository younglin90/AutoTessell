"""Gate4 binding evidence for provisional STL source and BL candidate output."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from core.layers.native_bl_atomic_certificate import sha256
from core.layers.native_tet_hemisphere_authority_artifact import (
    validate_hemisphere_authority_artifact,
)
from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger
from tests.test_native_surface_bl_front_actual_stl import _candidate


SOURCE = Path("tests/benchmarks/hemisphere_open.stl")
ARTIFACT = Path("docs/qa/authority/native_tet_hemisphere_case_authority_v1.json")


def _artifact() -> dict[str, object]:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def _rehash(value: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(value)
    result["artifact_sha256"] = sha256({key: item for key, item in result.items() if key != "artifact_sha256"})
    return result


def test_quality_candidate_binds_to_same_provisional_source_ledger() -> None:
    artifact = _artifact()
    ledger = build_stl_edge_ledger(SOURCE)
    assert validate_hemisphere_authority_artifact(artifact, SOURCE)["valid"] is True
    assert artifact["release_eligible"] is False
    assert artifact["runtime_route"] == "default_off"
    assert artifact["authority"] == {
        "feature_authority": False,
        "physical_group_authority": "user_declared_provisional",
        "wall_edge_authority": False,
    }
    assert artifact["source"]["sha256"] == ledger["source_sha256"]
    assert artifact["edge_ledger"]["edge_digest"] == ledger["edge_digest"]
    _, candidate = _candidate(SOURCE, 1)
    selected_ids = {str(value)[:15] for value in artifact["policy"]["selected_edge_ids"]}
    candidate_ids = {format(int(item["source_wall_edge"]), "x").rjust(15, "0") for item in candidate["provenance"]}
    assert candidate["accepted"] is True
    assert len(candidate["provenance"]) == artifact["policy"]["selected_edge_count"]
    assert candidate_ids == selected_ids
    assert {item["patch"] for item in candidate["provenance"]} == {artifact["policy"]["patch"]}
    assert {item["feature"] for item in candidate["provenance"]} == {"unclassified_boundary"}
    assert {item["physical_group"] for item in candidate["provenance"]} == {artifact["policy"]["physical_group"]}


def test_gate4_mutations_fail_closed_even_after_outer_rehash() -> None:
    artifact = _artifact()
    mutations = (
        lambda value: value["source"].update({"sha256": "stale-source"}),
        lambda value: value["edge_ledger"].update({"boundary_edge_count": 47}),
        lambda value: value["policy"].update({"patch": "intruder-patch"}),
        lambda value: value["policy"].update({"physical_group": "intruder-group"}),
        lambda value: value["authority"].update({"feature_authority": True}),
        lambda value: value.update({"release_eligible": True}),
        lambda value: value.update({"runtime_route": "production"}),
    )
    for mutate in mutations:
        mutated = copy.deepcopy(artifact)
        mutate(mutated)
        assert validate_hemisphere_authority_artifact(_rehash(mutated), SOURCE)["valid"] is False
