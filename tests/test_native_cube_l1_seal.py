from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

native_gate4 = pytest.importorskip("native_gate4_lineage_witness")
from core.evaluator.native_campaign_readiness_v2 import (
    audit_native_campaign_config_v2,
    build_corpus_seal,
)
from core.evaluator.native_semantic_manifest import (
    build_semantic_manifest,
    build_source_certificate,
)


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cube_source() -> Path:
    return Path(__file__).parent / "benchmarks" / "cube.stl"


def _ledger(source: Path) -> dict[str, Any]:
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    payload: dict[str, Any] = {
        "source": {"sha256": source_sha, "size_bytes": source.stat().st_size},
        "source_digest": source_sha,
        "selector_namespaces": {
            "stl_facet": {
                "available": True,
                "count": 12,
                "records": [{"id": index} for index in range(12)],
            }
        },
    }
    payload["ledger_digest"] = _digest(payload)
    return payload


def _semantic_rows() -> list[dict[str, Any]]:
    return [
        {
            "entity_kind": "stl_facet",
            "source_id": index,
            "feature": f"cube-face-{index}",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "cube",
            "provenance": f"tests/benchmarks/cube.stl#facet/{index}",
        }
        for index in range(12)
    ]


def _write_baseline(root: Path, *, positive_bl: bool) -> None:
    root.mkdir()
    for name, text in {
        "points": "points\n",
        "faces": "faces\n",
        "owner": "owner\n",
        "neighbour": "neighbour\n",
    }.items():
        (root / name).write_text(text, encoding="utf-8")
    count = 36 if positive_bl else 12
    start = 100 if positive_bl else 10
    (root / "boundary").write_text(
        f"""1
(
wall
{{
    type wall;
    nFaces {count};
    startFace {start};
}}
)
""",
        encoding="utf-8",
    )


def _lineage_records(*, positive_bl: bool) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source_id in range(12):
        if positive_bl:
            start = 100 + source_id * 3
            chain = (
                ("wall", 0, None, "bl_extrude"),
                ("inner", 1, f"boundary_face_{start}", "bl_extrude"),
                ("outer", 2, f"boundary_face_{start + 1}", "transition"),
            )
        else:
            start = 10 + source_id
            chain = (("wall", 0, None, "identity"),)
        row = _semantic_rows()[source_id]
        for offset, (role, layer, parent, operation) in enumerate(chain):
            records.append(
                {
                    "output_uid": f"boundary_face_{start + offset}",
                    "entity_scope": "output_boundary",
                    "source_ref": {"kind": "stl_facet", "id": source_id},
                    "semantic_owner_id": f"sem/stl_facet/{source_id}",
                    "operation": operation,
                    "boundary_role": role,
                    "layer_index": layer,
                    "parent_uid": parent,
                    **({"positive_measure": 1.0} if positive_bl else {}),
                    **{key: row[key] for key in ("feature", "patch", "physical_group", "component", "provenance")},
                }
            )
    return records


def _case(tmp_path: Path, *, positive_bl: bool) -> tuple[dict[str, str], dict[str, Any]]:
    source = _cube_source()
    ledger = _ledger(source)
    semantic_result = build_semantic_manifest(ledger, "stl_facet", _semantic_rows())
    assert semantic_result["accepted"] is True, semantic_result
    semantic = semantic_result["manifest"]
    authority_result = build_source_certificate(
        source,
        ledger,
        semantic,
        parser_name="native-cube-l1-fixture",
        parser_version="1",
        authority_statement={
            "attested": True,
            "issuer": "AutoTessell repository test fixture owner",
            "basis": "repository-owned cube.stl with explicit 12-facet source ledger",
        },
    )
    assert authority_result["accepted"] is True, authority_result
    authority = authority_result["certificate"]
    provenance = {
        "complete": True,
        "case_id": "cube-l1-bl1" if positive_bl else "cube-l1-bl0",
        "source_sha256": ledger["source_digest"],
        "semantic_manifest_sha256": semantic["manifest_sha256"],
        "certificate_sha256": authority["certificate_sha256"],
        "authority": "explicit repository-owned cube fixture",
    }
    baseline = tmp_path / ("baseline_bl1" if positive_bl else "baseline_bl0")
    _write_baseline(baseline, positive_bl=positive_bl)
    seal_result = build_corpus_seal(
        provenance["case_id"], source, ledger, semantic, authority, provenance, baseline,
    )
    assert seal_result["accepted"] is True, seal_result
    paths: dict[str, str] = {}
    for name, payload in {
        "source_ledger": ledger,
        "semantic": semantic,
        "authority": authority,
        "provenance": provenance,
        "seal": seal_result["seal"],
    }.items():
        path = tmp_path / f"{name}_{'bl1' if positive_bl else 'bl0'}.json"
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        paths[name] = str(path)
    paths.update({"source": str(source), "baseline": str(baseline)})
    case = {"id": provenance["case_id"], **paths}
    return case, {"semantic": semantic, "records": _lineage_records(positive_bl=positive_bl), "baseline": baseline}


def _native_replay(case_data: dict[str, Any], *, positive_bl: bool) -> None:
    expected_layers = 2 if positive_bl else 0
    first = native_gate4.audit_staged_lineage(
        str(case_data["baseline"]), _semantic_rows(), case_data["records"], expected_layers, expected_layers,
    )
    assert first["accepted"] is True, first
    for _ in range(2):
        replay = native_gate4.audit_staged_lineage(
            str(case_data["baseline"]), _semantic_rows(), case_data["records"],
            expected_layers, expected_layers, first["tree_sha256"] if not positive_bl else "",
        )
        assert replay["accepted"] is True, replay
        assert replay["tree_sha256"] == first["tree_sha256"]
        assert replay["lineage_sha256"] == first["lineage_sha256"]


def test_authoritative_cube_l1_bl0_bl1_v2_seal_and_native_replay(tmp_path: Path) -> None:
    cases: list[dict[str, str]] = []
    for positive_bl in (False, True):
        case, data = _case(tmp_path, positive_bl=positive_bl)
        _native_replay(data, positive_bl=positive_bl)
        cases.append(case)
    config = {"schema": "autotessell/native-campaign-readiness/v2", "version": 2, "corpus_id": "cube-l1", "cases": cases}
    config_path = tmp_path / "cube_l1_campaign.json"
    config_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")
    result = audit_native_campaign_config_v2(config_path)
    assert result["accepted"] is True, result
    assert all(case["ready"] is True for case in result["cases"])


def test_authoritative_cube_l1_tampered_provenance_refuses(tmp_path: Path) -> None:
    case, _ = _case(tmp_path, positive_bl=False)
    provenance_path = Path(case["provenance"])
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["authority"] = "tampered"
    provenance_path.write_text(json.dumps(provenance, sort_keys=True), encoding="utf-8")
    config = {"schema": "autotessell/native-campaign-readiness/v2", "version": 2, "corpus_id": "cube-l1", "cases": [case]}
    config_path = tmp_path / "tampered_campaign.json"
    config_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")
    result = audit_native_campaign_config_v2(config_path)
    assert result["accepted"] is False
    assert "cube-l1-bl0:seal_provenance_digest_mismatch" in result["reasons"]
