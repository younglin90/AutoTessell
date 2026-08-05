#!/usr/bin/env python3
"""Verify first-party native wheel and corresponding-source archive contents."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

EXPECTED_MODULES = {
    "native_bl",
    "native_hex_quality",
    "native_metrics",
    "native_polymesh",
    "native_snap",
    "native_surface_padding",
    "native_tet_predicates",
    "native_tet_qopt",
}
FORBIDDEN_MODULES = {"cfmesh_native", "cinolib_hex", "ftetwild", "robusthex"}
FORBIDDEN_SOURCE_PREFIXES = (
    "vendor/dependencies/",
    "AlgoHex/",
    "Feature-Preserving-Octree-Hex-Meshing/",
    "HOHQMesh/",
    "pdmt/",
    "voro/",
)
FORBIDDEN_BINDINGS = {
    "auto_tessell_core/cfmesh_bind.cpp",
    "auto_tessell_core/cinolib_hex_bind.cpp",
    "auto_tessell_core/ftetwild_bind.cpp",
    "auto_tessell_core/robusthex_bind.cpp",
}
REQUIRED_SOURCE = {
    "LICENSE",
    "NOTICE",
    "pyproject.toml",
    "auto_tessell_core/CMakeLists.txt",
    "auto_tessell_core/native_build_contract.json",
    "core/utils/_shewchuk/predicates.c",
    "docs/licensing/distribution-dependency-inventory.json",
    "docs/licensing/evidence/python-wheel-core-cp312-manylinux-x86_64.json",
    "docs/licensing/first-party-native-wheel-profile.md",
    "docs/licensing/mit-core-transition-policy.md",
    "docs/licensing/native-core-provenance-manifest.json",
    "scripts/collect_python_wheel_license_evidence.py",
    "scripts/native_build_evidence.py",
    "scripts/verify_distribution_dependency_inventory.py",
    *(f"auto_tessell_core/{name}_bind.cpp" for name in EXPECTED_MODULES),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _module_name(filename: str) -> str | None:
    basename = PurePosixPath(filename).name
    if not (basename.endswith(".so") or basename.endswith(".pyd")):
        return None
    return basename.split(".", 1)[0]


def verify_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        manifest_names = [
            item
            for item in names
            if PurePosixPath(item).name == "autotessell_native_build_manifest.json"
        ]
        contract_names = [
            item
            for item in names
            if PurePosixPath(item).name == "autotessell_native_build_contract.json"
        ]
        assert len(manifest_names) == 1, "wheel must contain exactly one native build manifest"
        assert len(contract_names) == 1, "wheel must contain exactly one native build contract"
        manifest_bytes = archive.read(manifest_names[0])
        contract_bytes = archive.read(contract_names[0])
        manifest = json.loads(manifest_bytes)
        contract = json.loads(contract_bytes)
    modules = {name for item in names if (name := _module_name(item)) is not None}
    assert modules == EXPECTED_MODULES, f"wheel native modules: {sorted(modules)}"
    assert not modules.intersection(FORBIDDEN_MODULES)
    assert not any("/vendor/dependencies/" in f"/{item}" for item in names)
    assert any(item.endswith(".dist-info/licenses/LICENSE") for item in names)
    assert any(item.endswith(".dist-info/licenses/NOTICE") for item in names)
    assert manifest["schema"] == 1
    assert contract["schema"] == 1
    assert set(manifest["modules"]) == EXPECTED_MODULES
    assert set(contract["modules"]) == EXPECTED_MODULES
    assert manifest["contract_sha256"] == hashlib.sha256(contract_bytes).hexdigest()
    assert manifest["compiler"]["cxx_standard"] == 23
    assert manifest["compiler"]["id"]
    assert manifest["compiler"]["version"]
    assert manifest["python_soabi"]
    assert manifest["source_identity"]
    assert manifest["source_tree_clean"] is True
    assert len(manifest["source_aggregate_sha256"]) == 64
    binary_members = {
        name: next(item for item in names if _module_name(item) == name)
        for name in EXPECTED_MODULES
    }
    with zipfile.ZipFile(path) as archive:
        for name in sorted(EXPECTED_MODULES):
            evidence = manifest["modules"][name]
            expected = contract["modules"][name]
            assert PurePosixPath(binary_members[name]).name == evidence["binary_file"]
            assert (
                hashlib.sha256(archive.read(binary_members[name])).hexdigest()
                == evidence["binary_sha256"]
            )
            assert evidence["public_symbols"] == expected["public_symbols"]
            assert len(evidence["binding_source_sha256"]) == 64


def verify_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        raw_names = [member.name for member in archive.getmembers() if member.isfile()]
    names = {
        str(PurePosixPath(*PurePosixPath(item).parts[1:]))
        for item in raw_names
        if len(PurePosixPath(item).parts) > 1
    }
    missing = REQUIRED_SOURCE.difference(names)
    assert not missing, f"sdist missing corresponding source: {sorted(missing)}"
    forbidden = sorted(item for item in names if item.startswith(FORBIDDEN_SOURCE_PREFIXES))
    assert not forbidden, f"sdist contains excluded adapter source: {forbidden[:8]}"
    assert not names.intersection(FORBIDDEN_BINDINGS)
    assert not any(item.endswith((".so", ".pyd", ".pyc")) for item in names)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    args = parser.parse_args()
    verify_wheel(args.wheel)
    verify_sdist(args.sdist)
    print(
        f"wheel={args.wheel.name} bytes={args.wheel.stat().st_size} "
        f"sha256={_sha256(args.wheel)}"
    )
    print(
        f"sdist={args.sdist.name} bytes={args.sdist.stat().st_size} "
        f"sha256={_sha256(args.sdist)}"
    )
    print("native-distribution-artifacts: modules=8 forbidden=0 source=present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
