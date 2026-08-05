"""C37 structured OCCT SDK admission/refusal witness tests."""

from __future__ import annotations

import sys

sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")

from native_brep_front_evidence_v2 import (  # noqa: E402
    audit_occt_sdk_manifest_v2,
)


def test_missing_sdk_manifest_is_structured_and_deterministic() -> None:
    args = (
        "/tmp/does-not-contain-occt-sdk",
        "/home/younglin90/.local/lib/python3.12/site-packages/OCP",
        "7.8.1",
        "cadquery-ocp==7.8.1.1.post1",
    )
    first = audit_occt_sdk_manifest_v2(*args)
    second = audit_occt_sdk_manifest_v2(*args)
    assert first["ready"] is False
    assert first["status"] == "occt_native_ingress_unavailable"
    assert first["reason"] == "sdk_manifest_incomplete"
    assert first["runtime_metadata_complete"] is True
    assert "BRep_Tool.hxx" in first["missing_artifacts"]
    assert "TKBRep" in first["missing_artifacts"]
    assert first["manifest_digest"] == second["manifest_digest"]
