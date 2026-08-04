from __future__ import annotations

import sys
from pathlib import Path


_BUILD = Path(__file__).resolve().parents[1] / "auto_tessell_core" / "build"
sys.path.insert(0, str(_BUILD))
import native_tet_receipt_graph as native  # noqa: E402


def _semantic() -> dict[str, str]:
    return {
        "feature": "wall",
        "patch": "wall",
        "physical_group": "fluid_wall",
        "component": "body",
        "provenance": "cad:face:7",
    }


def _source() -> list[dict[str, object]]:
    row = {"source_face_id": "sf-7", "source_vertex_ids": [10, 11, 12]}
    row.update(_semantic())
    return [row]


def _output(cycle: list[int] | None = None) -> list[dict[str, object]]:
    row = {
        "source_face_id": "sf-7",
        "output_face_id": "of-3",
        "output_vertex_ids": cycle or [10, 11, 12],
        "incidence": 1,
    }
    row.update(_semantic())
    return [row]


def test_receipt_graph_accepts_cyclic_rotation_and_emits_digest() -> None:
    result = dict(
        native.build_graph(_source(), _output([11, 12, 10]), "a" * 64, "b" * 64)
    )
    assert result["accepted"] is True
    assert result["publication_eligible"] is False
    assert result["graph_sha256"]
    assert result["orientation_reversal_forbidden"] is True


def test_receipt_graph_rejects_orientation_reversal() -> None:
    result = dict(
        native.build_graph(_source(), _output([10, 12, 11]), "a" * 64, "b" * 64)
    )
    assert result["accepted"] is False
    assert "orientation_or_source_cycle_mismatch" in list(result["reasons"])


def test_receipt_graph_rejects_semantic_tamper_and_incidence_change() -> None:
    output = _output()
    output[0]["physical_group"] = "tampered"
    output[0]["incidence"] = 2
    result = dict(native.build_graph(_source(), output, "a" * 64, "b" * 64))
    assert result["accepted"] is False
    reasons = list(result["reasons"])
    assert "semantic_payload_mismatch" in reasons
    assert "boundary_incidence_mismatch" in reasons


def test_receipt_graph_rejects_duplicate_output_ids() -> None:
    output = _output() * 2
    result = dict(native.build_graph(_source(), output, "a" * 64, "b" * 64))
    assert result["accepted"] is False
    assert "output_face_id_duplicate_or_empty" in list(result["reasons"])
