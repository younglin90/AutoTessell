from pathlib import Path

from core.evaluator.cad_release_authority import audit_cad_release_authority


def test_cad_authority_rejects_missing_or_symlink_source(tmp_path):
    result = audit_cad_release_authority(
        tmp_path / "missing.step", [], [], None
    )
    assert result.authoritative is False
    assert result.reason == "cad_source_file_invalid"


def test_cad_authority_rejects_invalid_reader_payload(tmp_path):
    path = tmp_path / "bad.step"
    path.write_text("not a STEP file", encoding="ascii")
    result = audit_cad_release_authority(path, [], [], None)
    assert result.authoritative is False
    assert result.status == "unverified"
