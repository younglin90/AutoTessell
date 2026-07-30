"""Fail-closed first-party native build evidence contracts."""

from __future__ import annotations

import importlib.machinery
import re
from pathlib import Path
from types import ModuleType

import pytest

from scripts import native_build_evidence as subject

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "auto_tessell_core/native_build_contract.json"


def _dummy_build(tmp_path: Path, module_names: list[str]) -> Path:
    build_dir = tmp_path / "native-build"
    build_dir.mkdir()
    suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
    for index, name in enumerate(module_names):
        (build_dir / f"{name}{suffix}").write_bytes(f"binary-{index}".encode())
    return build_dir


def _module_with_symbols(name: str, symbols: list[str]) -> ModuleType:
    module = ModuleType(name)
    for symbol in symbols:
        setattr(module, symbol, object())
    return module


def test_exact_contract_matches_all_public_pybind_symbols() -> None:
    contract = subject.load_contract(CONTRACT)
    for name, entry in contract["modules"].items():
        source = (ROOT / entry["sources"][0]).read_text(encoding="utf-8")
        initializer = source[source.index("PYBIND11_MODULE") :]
        functions = re.findall(r'(?:module|m)\.def\(\s*"([^"]+)"', initializer)
        classes = re.findall(r'py::class_<[^>]+>\([^,]+,\s*"([^"]+)"', initializer)
        assert sorted(set(functions + classes)) == entry["public_symbols"], name


def test_missing_manifest_still_names_stale_abi_symbols(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = subject.load_contract(CONTRACT)
    names = sorted(contract["modules"])
    build_dir = _dummy_build(tmp_path, names)

    def fake_load(_binary: Path, module_name: str) -> ModuleType:
        symbols = list(contract["modules"][module_name]["public_symbols"])
        if module_name == "native_snap":
            symbols.remove("extract_feature_edges")
        return _module_with_symbols(module_name, symbols)

    monkeypatch.setattr(subject, "load_extension", fake_load)
    with pytest.raises(subject.EvidenceError) as caught:
        subject.verify_build_evidence(contract_path=CONTRACT, build_dir=build_dir)
    message = str(caught.value)
    assert "missing native build manifest" in message
    assert "native_snap: missing public symbols: extract_feature_edges" in message


def test_generated_manifest_verifies_hashes_identity_and_exact_abi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = subject.load_contract(CONTRACT)
    names = sorted(contract["modules"])
    build_dir = _dummy_build(tmp_path, names)
    manifest_path = build_dir / subject.MANIFEST_FILENAME

    monkeypatch.setattr(subject, "_git_identity", lambda _root: (None, None))
    monkeypatch.setattr(
        subject,
        "load_extension",
        lambda _binary, module_name: _module_with_symbols(
            module_name, contract["modules"][module_name]["public_symbols"]
        ),
    )
    _, aggregate_hash = subject.source_evidence(contract, ROOT)
    archive_identity = subject.archive_content_identity(
        subject.sha256_file(CONTRACT), aggregate_hash
    )
    manifest = subject.generate_manifest(
        contract_path=CONTRACT,
        source_root=ROOT,
        build_dir=build_dir,
        output=manifest_path,
        source_identity=archive_identity,
        compiler_id="GNU",
        compiler_version="13.3.0",
        cxx_standard=23,
    )
    assert len(manifest["modules"]) == 8
    assert manifest["source_identity"] == archive_identity
    verified = subject.verify_build_evidence(
        contract_path=CONTRACT,
        source_root=ROOT,
        build_dir=build_dir,
        source_identity=archive_identity,
    )
    assert verified == manifest

    native_snap = subject.find_binary(build_dir, "native_snap")
    native_snap.write_bytes(b"tampered")
    with pytest.raises(subject.EvidenceError, match="native_snap: binary SHA-256 mismatch"):
        subject.verify_build_evidence(
            contract_path=CONTRACT,
            source_root=ROOT,
            build_dir=build_dir,
            source_identity=archive_identity,
        )


def test_archive_build_derives_truthful_content_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subject, "_git_identity", lambda _root: (None, None))
    derived = subject.archive_content_identity("a" * 64, "b" * 64)
    assert subject.resolve_source_identity(tmp_path, None, derived) == (
        derived,
        "archive-content",
        True,
    )
    assert derived != subject.archive_content_identity("a" * 64, "c" * 64)
    with pytest.raises(subject.EvidenceError, match="does not match derived"):
        subject.resolve_source_identity(tmp_path, "archive:sha256:" + "0" * 64, derived)
