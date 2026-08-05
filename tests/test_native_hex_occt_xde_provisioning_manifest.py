from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core.generator.native_hex.occt_xde_ingress import (
    read_authoritative_step_xde,
)


def _manifest(tmp_path: Path) -> tuple[Path, Path, str]:
    sdk = tmp_path / "occt-sdk"
    header = sdk / "include" / "opencascade" / "STEPCAFControl_Reader.hxx"
    library = sdk / "lib" / "libTKSTEPCAF.so"
    header.parent.mkdir(parents=True)
    library.parent.mkdir(parents=True)
    header.write_bytes(b"fake STEPCAF header C110")
    library.write_bytes(b"fake TKSTEPCAF library C110")
    lines = [
        "schema=autotessell/native-hex-occt-provisioning/v1\n",
        f"sdk_root={sdk.resolve()}\n",
        "occt_version=7.8.1\n",
        "occt_abi=occt-7.8.1\n",
        "compiler_abi=GNU-13.2.0\n",
        "build_identity=Linux-GNU-13.2.0\n",
        "header.STEPCAFControl_Reader.hxx=include/opencascade/STEPCAFControl_Reader.hxx|"
        + hashlib.sha256(header.read_bytes()).hexdigest()
        + "\n",
        "library.TKSTEPCAF=lib/libTKSTEPCAF.so|"
        + hashlib.sha256(library.read_bytes()).hexdigest()
        + "\n",
    ]
    canonical = "".join(lines).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    manifest = tmp_path / "native_hex_occt_provisioning.manifest"
    manifest.write_text("".join(lines) + f"manifest_sha256={digest}\n")
    return sdk, manifest, digest


def _kernel():
    return pytest.importorskip("native_hex_occt_xde_ingress")


def test_valid_manifest_is_verified_but_not_authority_without_occt(tmp_path: Path) -> None:
    sdk, manifest, digest = _manifest(tmp_path)
    result = dict(
        _kernel().audit_provisioning_manifest(
            str(sdk), str(manifest), "7.8.1", "occt-7.8.1", "GNU-13.2.0", "Linux-GNU-13.2.0"
        )
    )
    assert result["accepted"] is True, result
    assert result["authoritative"] is False
    assert result["compiled_with_occt"] is False
    assert result["manifest_sha256"] == digest
    assert result["header_count"] == 1
    assert result["library_count"] == 1


def test_manifest_file_tamper_is_refused(tmp_path: Path) -> None:
    sdk, manifest, _ = _manifest(tmp_path)
    (sdk / "lib" / "libTKSTEPCAF.so").write_bytes(b"tampered")
    result = dict(_kernel().audit_provisioning_manifest(str(sdk), str(manifest)))
    assert result["accepted"] is False
    assert "file_hash_mismatch" in result["reason"]


def test_manifest_identity_and_required_file_fail_closed(tmp_path: Path) -> None:
    sdk, manifest, _ = _manifest(tmp_path)
    mismatch = dict(
        _kernel().audit_provisioning_manifest(
            str(sdk), str(manifest), "7.7.0", "occt-7.7.0", "", ""
        )
    )
    assert mismatch["accepted"] is False
    assert mismatch["reason"] == "provisioning_manifest_expected_identity_mismatch"
    (sdk / "lib" / "libTKSTEPCAF.so").unlink()
    missing = dict(_kernel().audit_provisioning_manifest(str(sdk), str(manifest)))
    assert missing["accepted"] is False
    assert "file_hash_mismatch" in missing["reason"]


def test_manifest_digest_tamper_and_sdk_absent_ingress_refuse(tmp_path: Path) -> None:
    sdk, manifest, _ = _manifest(tmp_path)
    text = manifest.read_text()
    manifest.write_text(text.replace("manifest_sha256=", "manifest_sha256=" + "0", 1))
    result = dict(_kernel().audit_provisioning_manifest(str(sdk), str(manifest)))
    assert result["accepted"] is False
    assert result["reason"] == "provisioning_manifest_digest_missing_or_invalid"

    step = tmp_path / "fixture.step"
    step.write_bytes(b"C110-step")
    refused = read_authoritative_step_xde(
        step,
        sdk_root=sdk,
        provisioning_manifest_path=manifest,
    )
    assert refused["accepted"] is False
    assert refused["authoritative"] is False
    assert refused["reason"] == "occt_sdk_not_linked_or_manifest_mismatch"
    assert refused["candidate_discarded"] is True
