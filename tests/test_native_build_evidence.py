"""Fail-closed first-party native build evidence contracts."""

from __future__ import annotations

import importlib.machinery
import json
import re
from pathlib import Path
from types import ModuleType

import pytest

from scripts import native_build_evidence as subject

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "auto_tessell_core/native_build_contract.json"
CMAKE = ROOT / "auto_tessell_core" / "CMakeLists.txt"


def _release_configuration() -> dict[str, object]:
    return {
        "adapter_builds": {
            "BUILD_CFMESH": False,
            "BUILD_CINOLIB_HEX": False,
            "BUILD_FTETWILD": False,
            "BUILD_ROBUSTHEX": False,
        },
        "build_type": "Release",
        "install_first_party_native": True,
        "os": "Linux",
    }


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


def test_symbolic_linked_extension_binary_is_refused(
    tmp_path: Path,
) -> None:
    suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
    build_dir = tmp_path / "native-build"
    build_dir.mkdir()
    linked_binary = build_dir / f"native_metrics{suffix}"
    outside_binary = tmp_path / f"native_metrics{suffix}"
    outside_binary.write_bytes(b"untrusted-binary")
    try:
        linked_binary.symlink_to(outside_binary)
    except OSError as exc:
        pytest.skip(f"symbolic links unavailable: {exc}")

    with pytest.raises(subject.EvidenceError, match="symbolic-link extension binary is not accepted"):
        subject.find_binary(build_dir, "native_metrics")


def test_install_evidence_requires_regular_staged_metadata(
    tmp_path: Path,
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    manifest_target = tmp_path / subject.MANIFEST_FILENAME
    manifest_target.write_text("{}", encoding="utf-8")
    (stage / subject.MANIFEST_FILENAME).symlink_to(manifest_target)
    (stage / subject.WHEEL_CONTRACT_FILENAME).write_text("{}", encoding="utf-8")

    with pytest.raises(subject.EvidenceError, match="native install metadata must be a regular file"):
        subject.verify_install_evidence(source_root=tmp_path, stage_root=stage)


def test_install_evidence_wires_staged_contract_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    manifest_path = stage / subject.MANIFEST_FILENAME
    contract_path = stage / subject.WHEEL_CONTRACT_FILENAME
    manifest_path.write_text("{}", encoding="utf-8")
    contract_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_verify(**kwargs: object) -> dict[str, str]:
        captured.update(kwargs)
        return {"status": "pass"}

    monkeypatch.setattr(subject, "verify_build_evidence", fake_verify)
    assert subject.verify_install_evidence(source_root=tmp_path, stage_root=stage) == {
        "status": "pass"
    }
    assert captured["contract_path"] == contract_path
    assert captured["manifest_path"] == manifest_path
    assert captured["build_dir"] == stage
    assert captured["source_root"] == tmp_path


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
        configuration=_release_configuration(),
    )
    assert len(manifest["modules"]) == 8
    assert manifest["source_identity"] == archive_identity
    assert manifest["configuration"] == _release_configuration()
    verified = subject.verify_build_evidence(
        contract_path=CONTRACT,
        source_root=ROOT,
        build_dir=build_dir,
        source_identity=archive_identity,
    )
    assert verified == manifest

    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["configuration"]["build_type"] = "Debug"
    manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(subject.EvidenceError, match="release build type must be Release"):
        subject.verify_build_evidence(
            contract_path=CONTRACT,
            source_root=ROOT,
            build_dir=build_dir,
            source_identity=archive_identity,
        )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

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


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda value: value.__setitem__("os", ""), "release build OS is missing"),
        (lambda value: value.__setitem__("build_type", "Debug"), "release build type must be Release"),
        (
            lambda value: value.__setitem__("install_first_party_native", False),
            "install first-party native profile is not enabled",
        ),
        (
            lambda value: value["adapter_builds"].__setitem__("BUILD_CFMESH", True),
            "external adapter build must be disabled",
        ),
    ],
)
def test_release_configuration_matrix_fails_closed(
    mutator: object, message: str
) -> None:
    configuration = _release_configuration()
    mutator(configuration)  # type: ignore[operator]
    assert any(message in error for error in subject.release_configuration_errors(configuration))


def test_cmake_evidence_declares_the_release_install_matrix() -> None:
    cmake = CMAKE.read_text(encoding="utf-8")
    for flag in (
        '--os "${CMAKE_SYSTEM_NAME}"',
        '--build-type "${CMAKE_BUILD_TYPE}"',
        '--install-first-party-native "${AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE}"',
        '--build-cfmesh "${BUILD_CFMESH}"',
        '--build-cinolib-hex "${BUILD_CINOLIB_HEX}"',
        '--build-ftetwild "${BUILD_FTETWILD}"',
        '--build-robusthex "${BUILD_ROBUSTHEX}"',
    ):
        assert flag in cmake


def test_first_party_release_profile_is_statically_complete_and_adapter_free() -> None:
    cmake = CMAKE.read_text(encoding="utf-8")
    targets = [
        "native_metrics",
        "native_bl",
        "native_polymesh",
        "native_snap",
        "native_surface_padding",
        "native_hex_quality",
        "native_tet_predicates",
        "native_tet_qopt",
    ]
    profile_start = cmake.index("if(AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE)\n")
    profile_end = cmake.index("# ── Paths", profile_start)
    profile = cmake[profile_start:profile_end]
    helper_start = cmake.index("function(autotessell_configure_first_party_native target_name)")
    helper_end = cmake.index("endfunction()", helper_start)
    helper = cmake[helper_start:helper_end]
    configured = re.findall(
        r"^\s*autotessell_configure_first_party_native\((native_[a-z0-9_]+)\)",
        cmake,
        flags=re.MULTILINE,
    )

    for adapter in ("BUILD_CFMESH", "BUILD_CINOLIB_HEX", "BUILD_FTETWILD", "BUILD_ROBUSTHEX"):
        assert f'set({adapter} OFF CACHE BOOL "" FORCE)' in profile
    assert [target for target in configured if target in targets] == targets
    assert "target_compile_features(${target_name} PRIVATE cxx_std_23)" in helper
    assert "CXX_EXTENSIONS OFF" in helper
    assert "/WX" in helper
    assert "-Werror" in helper
    assert "add_custom_target(native_build_evidence ALL" in cmake
    assert "DEPENDS\n      ${_AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS}" in cmake
