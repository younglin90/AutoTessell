"""Regression coverage for the report-only POLY-CONCAVE-SPLIT1 census."""

from __future__ import annotations

import json

from scripts.diagnose_native_poly_concave_split import _json_safe, build_census


def test_concave_split_census_is_deterministic_and_conservatively_blocked() -> None:
    """The synthetic non-manifold witness must never authorize a split."""
    first = _json_safe(build_census())
    second = _json_safe(build_census())

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["mode"] == "report_only"
    assert first["target"]["reproduced"] is True
    assert first["legacy_union_candidate"]["invalid_cells"] == 2
    assert first["legacy_union_candidate"]["invalid_subtets"] == 18
    assert first["current_fan_component_reference"]["invalid_cells"] == 0
    assert first["current_fan_component_reference"]["invalid_subtets"] == 0

    feasibility = first["conical_decomposition_feasibility"]
    assert feasibility["geometric_candidate"] is True
    assert feasibility["split_feasible"] is False
    assert feasibility["classification"] == "STRUCTURAL_UNRESOLVED"
    assert feasibility["status"] == "blocked_pending_provenance_and_transactional_topology"
    assert first["surface_vertex_invariant"]["unchanged"] is True
    assert first["solid_gate"]["changed"] is False
