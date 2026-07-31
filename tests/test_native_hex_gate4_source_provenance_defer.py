"""Gate-4 evidence: current CAD ingestion has no physical-group mapping."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_STEP_READER = _ROOT / "core" / "analyzer" / "readers" / "step.py"


def test_cad_brep_ingestion_explicitly_withholds_source_face_physical_groups() -> None:
    """Do not mistake XDE display metadata for a source-face group contract."""
    source = _STEP_READER.read_text(encoding="utf-8")

    assert 'status="partial_authority_physical_groups_unavailable"' in source
    assert '"physical_group_authoritative": False' in source
    assert "physical_groups_authoritative = False" in source
    assert "physical_group_names=(None,) * face_ordinal" in source
    assert "face_ordinals_authoritative=True" in source
    assert "face_orientation_authoritative=True" in source
    assert "seam_connectivity_authoritative=True" in source


def test_gate4_defer_evidence_is_deterministic_and_does_not_create_a_mapping() -> None:
    first = _STEP_READER.read_bytes()
    second = _STEP_READER.read_bytes()

    assert first == second
    assert b"physical_groups_authoritative = False" in first
    assert b"physical_group_names=(None,) * face_ordinal" in first
