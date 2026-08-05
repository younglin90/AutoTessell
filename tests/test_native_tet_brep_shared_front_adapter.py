"""v2 witness preflight followed by the existing C++ quality stack."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.layers.native_tet_brep_front_evidence_v2 import build_brep_front_evidence_v2
from core.layers.native_tet_brep_shared_front_adapter import (
    plan_brep_shared_surface_wall_edge_front,
)
from tests.test_cad_xde_physical_authority import _write_styled_box
from tests.test_native_tet_brep_front_evidence_v2 import _explicit_owner_map


def _case(tmp_path: Path):
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    evidence = build_brep_front_evidence_v2(
        cad,
        source_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
        owner_face_by_edge=_explicit_owner_map(cad),
    )
    edge = evidence["edges"][0]
    p0, p1 = [evidence["canonical_positions"][index] for index in edge["canonical_endpoints"]]
    candidate = {
        "edge_id": edge["brep_edge_id"],
        "candidate_face_id": edge["owner_face_id"],
        "vertices": [p0, p1, [p0[0] + 0.17, p0[1] + 0.23, p0[2] + 0.31]],
    }
    kwargs = {
        "points": np.asarray(evidence["canonical_positions"], dtype=np.float64),
        "edges": np.asarray([[edge["brep_edge_id"], *edge["canonical_endpoints"], 0]], dtype=np.int64),
        "face_normals": np.asarray([[1.0, 0.0, 0.0]], dtype=np.float64),
        "patch_names": ["owner"],
        "feature_names": ["edge"],
        "physical_groups": [""],
        "requested_layers": 1,
        "first_height": 0.1,
        "growth_ratio": 1.0,
    }
    return evidence, candidate, kwargs


def test_brep_adapter_runs_witness_then_cpp_quality_stack(tmp_path: Path) -> None:
    evidence, candidate, kwargs = _case(tmp_path)
    result = plan_brep_shared_surface_wall_edge_front(
        evidence, requested_layers=1, candidates=[candidate], raw_planner_kwargs=kwargs
    )
    assert result["accepted"] is True
    assert result["status"] == "candidate_plan_ready"
    assert result["runtime_route"] == "default_off_brep_diagnostic"
    assert result["brep_witness_transaction"]["witnesses_computed_in_cpp"] is True
    assert result["source_immutable"] is True


def test_brep_adapter_refuses_witness_before_quality_stack(tmp_path: Path) -> None:
    evidence, candidate, kwargs = _case(tmp_path)
    candidate = dict(candidate)
    candidate["vertices"] = [candidate["vertices"][0], candidate["vertices"][1], candidate["vertices"][0]]
    result = plan_brep_shared_surface_wall_edge_front(
        evidence, requested_layers=1, candidates=[candidate], raw_planner_kwargs=kwargs
    )
    assert result["accepted"] is False
    assert result["status"] == "refused_brep_transaction"
    assert result["actual_layers"] == 0
