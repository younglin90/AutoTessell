from __future__ import annotations

from core.preprocessor.native_tri_quad.independent_quality_readback import (
    audit_native_tri_quad_actual_mixed_bl_artifact,
    commit_native_tri_quad_producer_auditor_quality_gate,
)
from tests.test_native_tri_quad_actual_mixed_bl_transaction import (
    CO_NORMALS,
    POINTS,
    QUADS,
    SOURCE,
    TRIANGLES,
    WALL_LOOP,
    _receipt,
    _run,
)


def _audit(layers: int):
    produced = _run(layers, heights=[] if layers == 0 else [0.1] * layers)
    return audit_native_tri_quad_actual_mixed_bl_artifact(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS,
        [] if layers == 0 else [0.1] * layers, produced, layers, 1.0,
    )


def test_fresh_process_audits_bl0_bl1_bl3_geometry_independently():
    for layers in (0, 1, 3):
        result = _audit(layers)
        assert result["accepted"] is True
        assert result["fresh_process"] is True
        assert result["auditor_schema"] == "TriQuadIndependentQualityCertificate/v4"
        assert result["producer_quality_ignored"] is True
        assert result["publication_eligible"] is False
        assert result["topology"] == {"duplicate": 0, "non_manifold": 0, "inverted": 0, "degenerate": 0}
        assert result["quality"]["max_skewness"] <= 0.50
        assert result["quality"]["max_tangential_aspect_ratio"] <= 10.0
        assert result["quality"]["coordinate_metrics"] is True
        assert result["quality"]["wall_front_tangential_leakage"]["applicable"] is (layers > 0)
        assert result["quality"]["wall_front_tangential_leakage"]["max"] == 0.0


def test_auditor_does_not_trust_producer_quality_rows():
    produced = _run(1)
    produced["quality"]["rows"][0]["skewness"] = 999.0
    result = audit_native_tri_quad_actual_mixed_bl_artifact(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS, [0.1], produced, 1, 1.0,
    )
    assert result["accepted"] is True
    assert result["quality"]["max_skewness"] < 999.0


def test_connectivity_tamper_refuses_without_repair():
    produced = _run(1)
    produced["strip_quads"][0] = [0, 1, 2, 3]
    result = audit_native_tri_quad_actual_mixed_bl_artifact(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS, [0.1], produced, 1, 1.0,
    )
    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["publication_eligible"] is False


def test_semantic_map_tamper_refuses():
    produced = _run(1)
    produced["triangle_map"][0]["physical_group"] = "wrong-group"
    result = audit_native_tri_quad_actual_mixed_bl_artifact(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS, [0.1], produced, 1, 1.0,
    )
    assert result["accepted"] is False
    assert result["reason"] == "triangle_lineage_mismatch"


    
def test_strip_semantic_map_tamper_refuses():
    produced = _run(1)
    produced["strip_map"][0]["provenance"] = "wrong-source"
    result = audit_native_tri_quad_actual_mixed_bl_artifact(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS, [0.1], produced, 1, 1.0,
    )
    assert result["accepted"] is False
    assert result["reason"] == "strip_lineage_semantics_mismatch"

    
def test_all_or_nothing_gate_commits_only_after_v4_certificate():
    for layers in (0, 1, 3):
        produced = _run(layers, heights=[] if layers == 0 else [0.1] * layers)
        certificate = _audit(layers)
        result = commit_native_tri_quad_producer_auditor_quality_gate(
            POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS,
            [] if layers == 0 else [0.1] * layers, produced, certificate, layers, 1.0,
        )
        assert result["accepted"] is True
        assert result["committed"] is True
        assert result["publication_eligible"] is False
        assert result["runtime_route"] == "private_default_off"
        assert result["actual_layers"] == layers


def test_gate_rolls_back_tampered_certificate_distribution():
    produced = _run(1)
    certificate = _audit(1)
    certificate["quality"]["distributions"]["aggregate"]["skewness"]["max"] = 99.0
    result = commit_native_tri_quad_producer_auditor_quality_gate(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS,
        [0.1], produced, certificate, 1, 1.0,
    )
    assert result["accepted"] is False
    assert result["committed"] is False
    assert result["candidate_discarded"] is True
    assert result["actual_layers"] == 0


def test_gate_rolls_back_binding_digest_mismatch():
    produced = _run(1)
    certificate = _audit(1)
    certificate["canonical_input_digest"] = "0" * 64
    result = commit_native_tri_quad_producer_auditor_quality_gate(
        POINTS, TRIANGLES, QUADS, _receipt(), WALL_LOOP, CO_NORMALS,
        [0.1], produced, certificate, 1, 1.0,
    )
    assert result["accepted"] is False
    assert result["reason"] == "certificate_input_digest_mismatch"
