from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core.generator.native_hex.occt_xde_ingress import (
    read_authoritative_step_xde,
)
from core.utils.native_extensions import import_native_extension


def _kernel():
    return pytest.importorskip("native_hex_occt_xde_ingress")


def test_sdk_absent_is_deterministic_fail_closed(tmp_path: Path) -> None:
    step = tmp_path / "fixture.step"
    step.write_bytes(b"ISO-10303-21;HEADER;C107;ENDSEC;END-ISO-10303-21;")
    result = _kernel().read_step_xde(str(step), "", "", "", [])
    assert result["accepted"] is False
    assert result["authoritative"] is False
    assert result["reason"] == "occt_sdk_unavailable"
    assert result["step_sha256"] == hashlib.sha256(step.read_bytes()).hexdigest()
    assert result["candidate_discarded"] is True
    assert result["publication_eligible"] is False


def test_sdk_root_without_linked_manifest_refuses(tmp_path: Path) -> None:
    step = tmp_path / "fixture.step"
    step.write_bytes(b"C107-sdk-probe")
    result = _kernel().read_step_xde(str(step), str(tmp_path / "sdk"), "", "", [])
    assert result["accepted"] is False
    assert result["reason"] == "occt_sdk_not_linked_or_manifest_mismatch"


def test_missing_step_is_refused_without_authority(tmp_path: Path) -> None:
    result = _kernel().read_step_xde(str(tmp_path / "missing.step"), "", "", "", [])
    assert result["accepted"] is False
    assert result["reason"] == "step_file_missing_or_symlink"
    assert result["authoritative"] is False


def test_python_adapter_never_falls_back_to_ocp(tmp_path: Path) -> None:
    step = tmp_path / "fixture.step"
    step.write_bytes(b"C107-python-adapter")
    result = read_authoritative_step_xde(step)
    assert result["accepted"] is False
    assert result["authoritative"] is False
    assert result["authority_contract"] == (
        "autotessell/native-hex-occt-xde-ingress/v1"
    )
    assert result["reason"] == "occt_sdk_unavailable"


def test_extension_is_first_party_native_module() -> None:
    module = import_native_extension("native_hex_occt_xde_ingress")
    assert hasattr(module, "read_step_xde")
