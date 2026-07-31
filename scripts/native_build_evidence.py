#!/usr/bin/env python3
"""Generate and verify fail-closed evidence for first-party native modules."""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import re
import subprocess
import sys
import sysconfig
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any, cast

MANIFEST_FILENAME = "autotessell_native_build_manifest.json"
WHEEL_CONTRACT_FILENAME = "autotessell_native_build_contract.json"
_GIT_IDENTITY = re.compile(r"git:[0-9a-f]{40}\Z")
_ARCHIVE_IDENTITY = re.compile(r"archive:sha256:[0-9a-f]{64}\Z")


class EvidenceError(RuntimeError):
    """Raised when native build evidence is incomplete or inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_contract(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != 1 or not isinstance(raw.get("modules"), dict):
        raise EvidenceError(f"invalid native build contract: {path}")
    modules = raw["modules"]
    if len(modules) != 8:
        raise EvidenceError(f"native build contract requires exactly 8 modules, got {len(modules)}")
    for name, entry in modules.items():
        if not isinstance(name, str) or not name.startswith("native_"):
            raise EvidenceError(f"invalid native module name in contract: {name!r}")
        if not isinstance(entry, dict):
            raise EvidenceError(f"invalid native module contract: {name}")
        sources = entry.get("sources")
        symbols = entry.get("public_symbols")
        if not isinstance(sources, list) or not sources:
            raise EvidenceError(f"{name}: sources must be a non-empty list")
        if not isinstance(symbols, list) or not symbols:
            raise EvidenceError(f"{name}: public_symbols must be a non-empty list")
        if sources != sorted(set(sources)):
            raise EvidenceError(f"{name}: sources must be unique and sorted")
        if symbols != sorted(set(symbols)):
            raise EvidenceError(f"{name}: public_symbols must be unique and sorted")
    return cast(dict[str, Any], raw)


def _combined_hash(items: Sequence[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for name, value in items:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def source_evidence(
    contract: Mapping[str, Any], source_root: Path
) -> tuple[dict[str, dict[str, Any]], str]:
    modules: dict[str, dict[str, Any]] = {}
    aggregate_items: list[tuple[str, str]] = []
    for name, entry in sorted(contract["modules"].items()):
        source_rows: list[dict[str, str]] = []
        module_items: list[tuple[str, str]] = []
        for relative in entry["sources"]:
            path = source_root / relative
            if not path.is_file():
                raise EvidenceError(f"{name}: missing binding source: {relative}")
            digest = sha256_file(path)
            source_rows.append({"path": relative, "sha256": digest})
            module_items.append((relative, digest))
        module_hash = _combined_hash(module_items)
        modules[name] = {
            "binding_source_sha256": module_hash,
            "sources": source_rows,
        }
        aggregate_items.append((name, module_hash))
    return modules, _combined_hash(aggregate_items)


def archive_content_identity(contract_hash: str, aggregate_source_hash: str) -> str:
    digest = _combined_hash(
        [("contract", contract_hash), ("binding-sources", aggregate_source_hash)]
    )
    return f"archive:sha256:{digest}"


def _git_identity(source_root: Path) -> tuple[str | None, bool | None]:
    probe = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=False,
        text=True,
    )
    if probe.returncode != 0:
        return None, None
    head = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(source_root), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return f"git:{head}", not bool(status.strip())


def resolve_source_identity(
    source_root: Path,
    explicit: str | None,
    archive_identity: str,
) -> tuple[str, str, bool]:
    git_identity, git_clean = _git_identity(source_root)
    if git_identity is not None:
        if explicit is not None and explicit != git_identity:
            raise EvidenceError(
                f"explicit source identity {explicit!r} does not match checkout {git_identity!r}"
            )
        assert git_clean is not None
        return git_identity, "git", git_clean
    if _ARCHIVE_IDENTITY.fullmatch(archive_identity) is None:
        raise EvidenceError("derived archive content identity is invalid")
    if explicit is not None and explicit != archive_identity:
        raise EvidenceError(
            f"explicit archive identity {explicit!r} does not match derived {archive_identity!r}"
        )
    return archive_identity, "archive-content", True


def _extension_candidates(directory: Path, module_name: str) -> list[Path]:
    return sorted(
        {
            candidate
            for suffix in importlib.machinery.EXTENSION_SUFFIXES
            if (candidate := directory / f"{module_name}{suffix}").is_file()
        }
    )


def find_binary(directory: Path, module_name: str) -> Path:
    candidates = _extension_candidates(directory, module_name)
    symbolic_links = [path for path in candidates if path.is_symlink()]
    if symbolic_links:
        rendered = ", ".join(str(path) for path in symbolic_links)
        raise EvidenceError(
            f"{module_name}: symbolic-link extension binary is not accepted: {rendered}"
        )
    if len(candidates) != 1:
        rendered = ", ".join(str(path) for path in candidates) or "none"
        raise EvidenceError(f"{module_name}: expected one extension binary, found {rendered}")
    return candidates[0]


def public_symbols(module: ModuleType) -> list[str]:
    return sorted(name for name in vars(module) if not name.startswith("_"))


def load_extension(binary: Path, module_name: str) -> ModuleType:
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, binary)
    if spec is None or spec.loader is None:
        raise EvidenceError(f"{module_name}: cannot create import specification for {binary}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _symbol_errors(module_name: str, expected: Sequence[str], actual: Sequence[str]) -> list[str]:
    missing = sorted(set(expected).difference(actual))
    extra = sorted(set(actual).difference(expected))
    errors: list[str] = []
    if missing:
        errors.append(f"{module_name}: missing public symbols: {', '.join(missing)}")
    if extra:
        errors.append(f"{module_name}: unexpected public symbols: {', '.join(extra)}")
    return errors


def generate_manifest(
    *,
    contract_path: Path,
    source_root: Path,
    build_dir: Path,
    output: Path,
    source_identity: str | None,
    compiler_id: str,
    compiler_version: str,
    cxx_standard: int,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    source_rows, aggregate_hash = source_evidence(contract, source_root)
    contract_hash = sha256_file(contract_path)
    archive_identity = archive_content_identity(contract_hash, aggregate_hash)
    identity, identity_kind, source_clean = resolve_source_identity(
        source_root, source_identity, archive_identity
    )
    modules: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name, entry in sorted(contract["modules"].items()):
        binary = find_binary(build_dir, name)
        try:
            symbols = public_symbols(load_extension(binary, name))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: import failed: {exc}")
            continue
        errors.extend(_symbol_errors(name, entry["public_symbols"], symbols))
        modules[name] = {
            **source_rows[name],
            "binary_file": binary.name,
            "binary_sha256": sha256_file(binary),
            "public_symbols": symbols,
        }
    if errors:
        raise EvidenceError("\n".join(errors))
    manifest = {
        "compiler": {
            "cxx_standard": cxx_standard,
            "id": compiler_id,
            "version": compiler_version,
        },
        "contract_sha256": contract_hash,
        "modules": modules,
        "python_soabi": sysconfig.get_config_var("SOABI"),
        "schema": 1,
        "source_aggregate_sha256": aggregate_hash,
        "source_identity": identity,
        "source_identity_kind": identity_kind,
        "source_tree_clean": source_clean,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _load_manifest(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"missing native build manifest: {path}")
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid native build manifest {path}: {exc}")
        return None
    if not isinstance(raw, dict) or raw.get("schema") != 1:
        errors.append(f"native build manifest schema mismatch: {path}")
        return None
    return raw


def verify_build_evidence(
    *,
    contract_path: Path,
    build_dir: Path,
    source_root: Path | None = None,
    source_identity: str | None = None,
    manifest_path: Path | None = None,
    require_clean_source: bool = True,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    errors: list[str] = []
    manifest_file = manifest_path or build_dir / MANIFEST_FILENAME
    manifest = _load_manifest(manifest_file, errors)

    expected_names = sorted(contract["modules"])
    source_rows: dict[str, dict[str, Any]] | None = None
    aggregate_hash: str | None = None
    expected_identity: str | None = source_identity
    if source_root is not None:
        try:
            source_rows, aggregate_hash = source_evidence(contract, source_root)
            archive_identity = archive_content_identity(sha256_file(contract_path), aggregate_hash)
            expected_identity, _, clean = resolve_source_identity(
                source_root, source_identity, archive_identity
            )
            if require_clean_source and not clean:
                errors.append("tracked source tree is dirty; fresh tracked build evidence required")
        except EvidenceError as exc:
            errors.append(str(exc))

    manifest_modules: Mapping[str, Any] = {}
    if manifest is not None:
        manifest_modules_raw = manifest.get("modules")
        if not isinstance(manifest_modules_raw, dict):
            errors.append("native build manifest modules must be an object")
        else:
            manifest_modules = manifest_modules_raw
            if sorted(manifest_modules) != expected_names:
                errors.append(
                    "manifest module set mismatch: " + ", ".join(sorted(manifest_modules))
                )
        if manifest.get("contract_sha256") != sha256_file(contract_path):
            errors.append("manifest contract SHA-256 mismatch")
        if manifest.get("python_soabi") != sysconfig.get_config_var("SOABI"):
            errors.append("manifest Python SOABI mismatch")
        compiler = manifest.get("compiler")
        if not isinstance(compiler, dict):
            errors.append("manifest compiler identity is missing")
        else:
            if compiler.get("cxx_standard") != 23:
                errors.append("manifest C++ standard is not 23")
            if not compiler.get("id") or not compiler.get("version"):
                errors.append("manifest compiler id/version is missing")
        identity = manifest.get("source_identity")
        kind = manifest.get("source_identity_kind")
        if kind == "git":
            if not isinstance(identity, str) or _GIT_IDENTITY.fullmatch(identity) is None:
                errors.append("manifest Git source identity is invalid")
        elif kind == "archive-content":
            if not isinstance(identity, str) or _ARCHIVE_IDENTITY.fullmatch(identity) is None:
                errors.append("manifest archive content identity is invalid")
        else:
            errors.append("manifest source identity kind is invalid")
        if expected_identity is not None and identity != expected_identity:
            errors.append(
                "manifest source identity mismatch: "
                f"expected {expected_identity!r}, got {identity!r}"
            )
        if require_clean_source and manifest.get("source_tree_clean") is not True:
            errors.append("manifest does not prove a clean tracked/archive source")
        if aggregate_hash is not None and manifest.get("source_aggregate_sha256") != aggregate_hash:
            errors.append("manifest aggregate source SHA-256 mismatch")

    for name in expected_names:
        entry = contract["modules"][name]
        try:
            binary = find_binary(build_dir, name)
        except EvidenceError as exc:
            errors.append(str(exc))
            continue
        try:
            symbols = public_symbols(load_extension(binary, name))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: import failed: {exc}")
            continue
        errors.extend(_symbol_errors(name, entry["public_symbols"], symbols))
        manifest_entry = manifest_modules.get(name)
        if manifest is None:
            continue
        if not isinstance(manifest_entry, dict):
            errors.append(f"{name}: missing manifest module entry")
            continue
        if manifest_entry.get("binary_file") != binary.name:
            errors.append(f"{name}: manifest binary filename mismatch")
        if manifest_entry.get("binary_sha256") != sha256_file(binary):
            errors.append(f"{name}: binary SHA-256 mismatch")
        if manifest_entry.get("public_symbols") != entry["public_symbols"]:
            errors.append(f"{name}: manifest public symbol contract mismatch")
        if source_rows is not None:
            expected_source = source_rows[name]
            if (
                manifest_entry.get("binding_source_sha256")
                != expected_source["binding_source_sha256"]
            ):
                errors.append(f"{name}: binding source SHA-256 mismatch")
            if manifest_entry.get("sources") != expected_source["sources"]:
                errors.append(f"{name}: binding source file evidence mismatch")

    native_binaries = {
        path.name.split(".", 1)[0]
        for path in build_dir.iterdir()
        if path.is_file()
        and any(path.name.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES)
        and path.name.startswith("native_")
    }
    unexpected = sorted(native_binaries.difference(expected_names))
    if unexpected:
        errors.append("unexpected first-party native binaries: " + ", ".join(unexpected))
    if errors:
        raise EvidenceError("\n".join(errors))
    assert manifest is not None
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--contract", type=Path, required=True)
    generate.add_argument("--source-root", type=Path, required=True)
    generate.add_argument("--build-dir", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--source-identity")
    generate.add_argument("--compiler-id", required=True)
    generate.add_argument("--compiler-version", required=True)
    generate.add_argument("--cxx-standard", type=int, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--contract", type=Path, required=True)
    verify.add_argument("--source-root", type=Path, required=True)
    verify.add_argument("--build-dir", type=Path, required=True)
    verify.add_argument("--manifest", type=Path)
    verify.add_argument("--source-identity")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate_manifest(
                contract_path=args.contract.resolve(),
                source_root=args.source_root.resolve(),
                build_dir=args.build_dir.resolve(),
                output=args.output.resolve(),
                source_identity=args.source_identity,
                compiler_id=args.compiler_id,
                compiler_version=args.compiler_version,
                cxx_standard=args.cxx_standard,
            )
        else:
            manifest = verify_build_evidence(
                contract_path=args.contract.resolve(),
                source_root=args.source_root.resolve(),
                build_dir=args.build_dir.resolve(),
                manifest_path=args.manifest.resolve() if args.manifest else None,
                source_identity=args.source_identity,
            )
    except EvidenceError as exc:
        print(f"native-build-evidence: FAIL\n{exc}", file=sys.stderr)
        return 1
    if args.command == "generate":
        print(
            "native-build-evidence: GENERATED "
            f"modules={len(manifest['modules'])} source={manifest['source_identity']} "
            f"clean={str(manifest['source_tree_clean']).lower()}"
        )
    else:
        print(
            "native-build-evidence: PASS "
            f"modules={len(manifest['modules'])} source={manifest['source_identity']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
