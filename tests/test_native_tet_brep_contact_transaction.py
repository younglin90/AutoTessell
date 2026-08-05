"""Default-off all-or-nothing B-Rep witness transaction."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")
from native_brep_front_evidence_v2 import (  # noqa: E402
    plan_brep_shared_surface_wall_edge_front,
)

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.layers.native_tet_brep_front_evidence_v2 import (
    build_brep_front_evidence_v2,
)
from tests.test_cad_xde_physical_authority import _write_styled_box
from tests.test_native_tet_brep_front_evidence_v2 import _explicit_owner_map


def _payload(tmp_path: Path) -> dict:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    return build_brep_front_evidence_v2(
        cad,
        source_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
        owner_face_by_edge=_explicit_owner_map(cad),
    )


def test_transaction_bl0_is_identity_without_evidence_parse() -> None:
    result = plan_brep_shared_surface_wall_edge_front({}, 0, [])
    assert result == {
        "accepted": True,
        "status": "disabled_identity",
        "requested_layers": 0,
        "actual_layers": 0,
        "generated_faces": [],
        "source_immutable": True,
        "runtime_route": "default_off",
        "atomic_rollback": True,
    }


def test_transaction_commits_all_witnesses_or_rolls_back_everything(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    edge = payload["edges"][0]
    p0, p1 = [payload["canonical_positions"][index] for index in edge["canonical_endpoints"]]
    third = [p0[0] + 0.17, p0[1] + 0.23, p0[2] + 0.31]
    candidates = [{
        "edge_id": edge["brep_edge_id"],
        "candidate_face_id": edge["owner_face_id"],
        "vertices": [p0, p1, third],
    }]
    accepted = plan_brep_shared_surface_wall_edge_front(payload, 1, candidates)
    assert accepted["accepted"] is True
    assert accepted["status"] == "candidate_plan_ready"
    assert accepted["actual_layers"] == 1
    assert len(accepted["generated_faces"]) == 1
    bad = dict(candidates[0])
    bad["vertices"] = [p0, p1, p0]
    rolled_back = plan_brep_shared_surface_wall_edge_front(payload, 1, [candidates[0], bad])
    assert rolled_back["accepted"] is False
    assert rolled_back["status"] == "refused_brep_transaction"
    assert rolled_back["actual_layers"] == 0
    assert rolled_back["generated_faces"] == []
    assert rolled_back["atomic_rollback"] is True
    assert rolled_back["source_immutable"] is True
