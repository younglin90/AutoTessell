"""Authority adapter tests: raw files never become physical groups by inference."""

from __future__ import annotations

from pathlib import Path

from core.layers.surface_bl_authority_artifacts import (
    build_cad_authority_snapshot,
    build_real_source_matrix,
    build_stl_authority_snapshot,
    classify_snapshot,
)


def test_real_stl_snapshot_is_stable_but_unverified_without_ledger() -> None:
    path = Path("tests/benchmarks/cube.stl")
    first = build_stl_authority_snapshot(path)
    second = build_stl_authority_snapshot(path)
    assert first["raw_sha256"] == second["raw_sha256"]
    assert first["authority_complete"] is False
    assert classify_snapshot(first) == "UNVERIFIED"
    assert first["reason"] == "missing_explicit_facet_authority_ledger"


def test_explicit_facet_ledger_can_be_authoritative_without_inference() -> None:
    path = Path("tests/benchmarks/cube.stl")
    base = build_stl_authority_snapshot(path)
    ledger = {
        index: {"patch": "wall", "feature": "cube", "physical_group": "fluid", "component": "main"}
        for index in range(base["facet_count"])
    }
    snapshot = build_stl_authority_snapshot(path, ledger=ledger)
    assert snapshot["authority_complete"] is True
    assert classify_snapshot(snapshot) == "PASS_FOR_REVIEW"
    assert len(snapshot["ledger"]) == base["facet_count"]


def test_cad_display_metadata_is_not_physical_group_authority(tmp_path: Path) -> None:
    path = tmp_path / "probe.step"
    path.write_bytes(b"STEP probe")
    snapshot = build_cad_authority_snapshot(path, mapping={"face_edge_mapping": {"0": "face-0"}, "layers": ["wall"]})
    assert snapshot["authority_complete"] is False
    assert snapshot["display_metadata_promoted"] is False
    assert classify_snapshot(snapshot) == "UNVERIFIED"


def test_real_matrix_reports_artifact_gaps_without_substitution() -> None:
    matrix = build_real_source_matrix(".")
    assert len(matrix["rows"]) == 5
    assert matrix["route"] == "default_off"
    assert all(row["status"] == "UNVERIFIED" for row in matrix["rows"])
