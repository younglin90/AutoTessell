from __future__ import annotations

import json
from pathlib import Path

from core.evaluator.native_tet_cube_authority import validate_cube_authority_ledger


def test_pinned_cube_ledger_is_authoritative() -> None:
    result = validate_cube_authority_ledger()
    assert result["accepted"]
    assert result["source_sha256"] == "e930f60a32009db799542620bcb492895dbc86c172fdb3c2f39a0445f63fbc81"
    assert result["facet_count"] == 12
    assert result["patches"] == ["wall"]
    assert result["physical_groups"] == ["wall"]


def test_cube_ledger_refuses_raw_source_mutation(tmp_path: Path) -> None:
    source = tmp_path / "cube.stl"
    source.write_bytes(Path("tests/benchmarks/cube.stl").read_bytes() + b"\n")
    result = validate_cube_authority_ledger(source_path=source)
    assert not result["accepted"]
    assert result["reason"] == "raw_sha256_mismatch"


def test_cube_ledger_refuses_facet_binding_mutation(tmp_path: Path) -> None:
    ledger = json.loads(Path("docs/qa/authority/native_tet_cube_stl_authority_v1.json").read_text())
    ledger["facets"][0]["physical_group"] = "wrong"
    changed = tmp_path / "ledger.json"
    changed.write_text(json.dumps(ledger), encoding="utf-8")
    result = validate_cube_authority_ledger(changed)
    assert not result["accepted"]
    assert result["reason"] == "facet_binding"
