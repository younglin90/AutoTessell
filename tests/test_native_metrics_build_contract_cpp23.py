"""Regression ABI ledger tests for native_metrics public C++23 audits."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "auto_tessell_core" / "native_build_contract.json"
SOURCE = ROOT / "auto_tessell_core" / "native_metrics_bind.cpp"


def test_strict_pair_and_tri_topology_audits_are_contracted_no_convert_abi() -> None:
    symbols = json.loads(CONTRACT.read_text(encoding="utf-8"))["modules"][
        "native_metrics"
    ]["public_symbols"]
    source = SOURCE.read_text(encoding="utf-8")
    tri_binding = source[source.index('m.def("triangle_surface_topology_audit"') :]
    strict_binding = source[source.index('m.def("strict_quad_pair_preflight"') :]

    assert "triangle_surface_topology_audit" in symbols
    assert "strict_quad_pair_preflight" in symbols
    assert 'py::arg("vertices").noconvert()' in tri_binding
    assert 'py::arg("faces").noconvert()' in tri_binding
    for name in (
        "source_vertices",
        "candidate_vertices",
        "source_triangles",
        "candidate_triangles",
        "quads",
        "pair_provenance",
        "feature_edges",
    ):
        assert f'py::arg("{name}").noconvert()' in strict_binding
