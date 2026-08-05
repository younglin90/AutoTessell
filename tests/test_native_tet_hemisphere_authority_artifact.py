"""Durable actual-corpus artifact replay and fail-closed mutation tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from core.layers.native_bl_atomic_certificate import sha256
from core.layers.native_tet_hemisphere_authority_artifact import (
    build_hemisphere_authority_artifact,
    validate_hemisphere_authority_artifact,
)


_STL = Path("tests/benchmarks/hemisphere_open.stl")
_ARTIFACT = Path("docs/qa/authority/native_tet_hemisphere_case_authority_v1.json")


def _stored() -> dict[str, object]:
    return json.loads(_ARTIFACT.read_text(encoding="utf-8"))


def _rehash(artifact: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(artifact)
    result["artifact_sha256"] = sha256({key: value for key, value in result.items() if key != "artifact_sha256"})
    return result


def test_committed_artifact_replays_live_and_builder_is_deterministic() -> None:
    artifact = _stored()
    assert validate_hemisphere_authority_artifact(artifact, _STL)["valid"] is True
    first = build_hemisphere_authority_artifact(_STL)
    second = build_hemisphere_authority_artifact(_STL)
    assert first == second == artifact


def test_artifact_digest_count_and_status_mutations_refuse() -> None:
    artifact = _stored()
    for mutate in (
        lambda value: value["source"].update({"sha256": "stale"}),
        lambda value: value["edge_ledger"].update({"boundary_edge_count": 47}),
        lambda value: value["policy"].update({"selected_edge_digest": "stale"}),
        lambda value: value.update({"release_eligible": True}),
        lambda value: value["authority"].update({"feature_authority": True}),
    ):
        mutated = copy.deepcopy(artifact)
        mutate(mutated)
        result = validate_hemisphere_authority_artifact(_rehash(mutated), _STL)
        assert result["valid"] is False
