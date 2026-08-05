from __future__ import annotations

import json
from pathlib import Path

from core.evaluator.native_poly_fresh_stage_profile import profile_poly_bl_stage


def _fp(_path: str | Path) -> dict[str, object]:
    return {"tree_sha256": "a" * 64, "entry_count": 2}


def _provenance() -> dict[str, object]:
    return {
        "lineage_complete": True,
        "source_sha256": "1" * 64,
        "candidate_source_sha256": "2" * 64,
        "wall_edge_layer_sha256": "3" * 64,
        "source_face_preservation_sha256": "4" * 64,
        "outer_front_sha256": "5" * 64,
        "producer_mapping_sha256": "6" * 64,
    }


def _partitions() -> dict[str, object]:
    return {
        "counts": {"core": 4, "boundary_layer": 2, "transition": 0},
        "transition_not_applicable": True,
    }


def test_bl0_is_identity_observation_and_skips_callbacks(tmp_path: Path) -> None:
    called = []
    report = profile_poly_bl_stage(
        tmp_path,
        requested_layers=0,
        actual_layers=0,
        baseline_dir=tmp_path,
        stage_callbacks={"expensive_generation": lambda: called.append(True)},
        fingerprint_fn=_fp,
    )
    assert report["status"] == "PASS"
    assert report["reason"] == "bl0_disabled_identity"
    assert report["observation_only"] is True
    assert report["publish_allowed"] is False
    assert called == []


def test_bl1_missing_lineage_refuses_before_expensive_callback(tmp_path: Path) -> None:
    called = []
    report = profile_poly_bl_stage(
        tmp_path,
        requested_layers=1,
        input_sha256="a" * 64,
        build_sha256="b" * 64,
        partitions=_partitions(),
        allow_test_fixtures=True,
        stage_callbacks={"expensive_generation": lambda: called.append(True)},
        fingerprint_fn=_fp,
    )
    assert report["status"] == "REFUSED"
    assert report["reason"] == "bl_lineage_missing"
    assert called == []


def test_all_core_or_missing_transition_certificate_refuses(tmp_path: Path) -> None:
    all_core = {"counts": {"core": 6, "boundary_layer": 0, "transition": 0}}
    report = profile_poly_bl_stage(
        tmp_path,
        requested_layers=1,
        input_sha256="a" * 64,
        build_sha256="b" * 64,
        provenance=_provenance(),
        partitions=all_core,
        allow_test_fixtures=True,
        fingerprint_fn=_fp,
    )
    assert report["status"] == "REFUSED"
    assert report["reason"] == "partition_boundary_layer_empty"


def test_admitted_profile_records_stages_counters_and_readback(tmp_path: Path) -> None:
    report = profile_poly_bl_stage(
        tmp_path,
        requested_layers=1,
        input_sha256="a" * 64,
        build_sha256="b" * 64,
        provenance=_provenance(),
        partitions=_partitions(),
        allow_test_fixtures=True,
        stage_callbacks={
            "collision": lambda: {
                "collision_counters": {
                    "rays": 10,
                    "triangles": 20,
                    "candidates": 30,
                    "max_candidates": 4,
                }
            }
        },
        readback_callbacks={
            "strict_topology": lambda: {"valid": True},
            "quality_witness": lambda: {"accepted": True},
        },
        fingerprint_fn=_fp,
    )
    assert report["status"] == "PASS"
    assert report["publish_allowed"] is False
    assert set(report["stage_timings"]) == {"collision", "quality_witness", "strict_topology"}
    assert report["collision_counters"] == {
        "rays": 10,
        "triangles": 20,
        "candidates": 30,
        "max_candidates": 4,
    }
    assert report["artifact_before"] == report["artifact_after"]
    assert len(report["profile_sha256"]) == 64


def test_timeout_is_localized_and_does_not_publish(tmp_path: Path) -> None:
    report = profile_poly_bl_stage(
        tmp_path,
        requested_layers=1,
        input_sha256="a" * 64,
        build_sha256="b" * 64,
        provenance=_provenance(),
        partitions=_partitions(),
        allow_test_fixtures=True,
        stage_callbacks={"collision": lambda: (_ for _ in ()).throw(TimeoutError("budget"))},
        fingerprint_fn=_fp,
    )
    assert report["status"] == "TIMEOUT"
    assert report["reason"] == "stage_timeout:collision"
    assert report["publish_allowed"] is not True
    assert report["stage_results"]["collision"]["status"] == "TIMEOUT"


def test_mutation_is_regression_and_output_is_external(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    state = {"changed": False}

    def fp(_path: str | Path) -> dict[str, object]:
        return {"tree_sha256": "b" * 64 if state["changed"] else "a" * 64, "entry_count": 2}

    def mutator() -> None:
        state["changed"] = True

    output = tmp_path / "evidence" / "profile.json"
    report = profile_poly_bl_stage(
        stage,
        requested_layers=1,
        input_sha256="a" * 64,
        build_sha256="b" * 64,
        provenance=_provenance(),
        partitions=_partitions(),
        allow_test_fixtures=True,
        stage_callbacks={"unexpected_mutation": mutator},
        fingerprint_fn=fp,
        output_path=output,
    )
    assert report["status"] == "REGRESSION"
    assert report["reason"] == "stage_mutated_after_admission"
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "REGRESSION"


def test_caller_supplied_lineage_is_not_production_evidence(tmp_path: Path) -> None:
    report = profile_poly_bl_stage(
        tmp_path,
        requested_layers=1,
        input_sha256="a" * 64,
        build_sha256="b" * 64,
        provenance=_provenance(),
        partitions=_partitions(),
        fingerprint_fn=_fp,
    )
    assert report["status"] == "REFUSED"
    assert report["reason"] == "caller_lineage_not_producer_evidence"
