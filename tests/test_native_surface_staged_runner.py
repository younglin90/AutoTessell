from __future__ import annotations

import json

from core.evaluator.native_surface_staged_runner import run_surface_artifact_in_private_stage


def _authority() -> dict[str, object]:
    return {
        "accepted": True, "receipt_sealed": True, "direct_lineage": True,
        "wall_edge_eligible": True, "source_authority_status": "SOURCE_VERIFIED",
        "source_sha256": "a" * 64,
    }


def test_bl0_publishes_identity_without_bl_sidecar(tmp_path):
    def writer(stage, _run):
        (stage / "surface.json").write_text(json.dumps({"identity": True}), encoding="utf-8")
        return {"accepted": True, "actual_layers": 0, "bl_sidecar_created": False}

    result = run_surface_artifact_in_private_stage(
        tmp_path / "surface", writer_callback=writer,
        audit_callback=lambda _stage, _result: {"accepted": True},
        source_authority=None, requested_layers=0,
    )
    assert result.published is True
    assert result.publish and result.publish["atomic"] is True


def test_positive_bl_requires_authority_before_any_stage(tmp_path):
    result = run_surface_artifact_in_private_stage(
        tmp_path / "surface", writer_callback=lambda _stage, _run: {"accepted": True, "actual_layers": 1},
        audit_callback=lambda _stage, _result: {"accepted": True},
        source_authority=None, requested_layers=1,
    )
    assert result.published is False
    assert result.refused_reason == "surface_positive_bl_authority_missing"


def test_positive_bl_repeats_and_publishes_after_audit(tmp_path):
    def writer(stage, _run):
        (stage / "surface.json").write_text(json.dumps({"layers": 1}, sort_keys=True), encoding="utf-8")
        (stage / "boundary-layer.json").write_text(json.dumps({"thickness": 0.1}), encoding="utf-8")
        return {
            "accepted": True, "actual_layers": 1, "source_authority_bound": True,
            "positive_thickness": 0.1, "provenance": [{"source_wall_edge": "edge-1", "layer": 1}],
        }

    result = run_surface_artifact_in_private_stage(
        tmp_path / "surface", writer_callback=writer,
        audit_callback=lambda _stage, _result: {"accepted": True},
        source_authority=_authority(), requested_layers=1,
    )
    assert result.published is True
    assert len(result.runs) == 3
    assert len(result.audits) == 3
