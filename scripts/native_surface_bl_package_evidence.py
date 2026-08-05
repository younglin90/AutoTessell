#!/usr/bin/env python3
"""Generate a verified manifest for the separate surface BL package."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sysconfig
from pathlib import Path


SCHEMA = "autotessell/native-extension-manifest/v1"
DEFAULT_SOURCES = {
    "native_surface_bl_folded_plate": Path(
        "auto_tessell_core/surface_bl_front_shared/surface_bl_folded_plate_bind.cpp"
    ),
    "native_surface_bl_readback_verifier": Path(
        "auto_tessell_core/surface_bl_front_shared/surface_bl_readback_verifier_bind.cpp"
    ),
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def payload_digest(value: dict[str, object]) -> str:
    payload = dict(value)
    payload.pop("manifest_payload_sha256", None)
    return sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    )


def source_identity(root: Path) -> str:
    try:
        return "git:" + subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "archive:unresolved"


def _source_path(module: str, source: Path | None, repo_root: Path) -> Path:
    candidate = source if source is not None else DEFAULT_SOURCES.get(module)
    if candidate is None:
        raise ValueError(f"source is required for unknown module {module}")
    return (candidate if candidate.is_absolute() else repo_root / candidate).resolve()


def generate(
    binaries: list[tuple[str, Path, Path | None]], output: Path, repo_root: Path
) -> Path:
    output = output.resolve()
    repo_root = repo_root.resolve()
    package_dir = output / "native_extensions"
    package_dir.mkdir(parents=True, exist_ok=True)
    identity = source_identity(repo_root)
    soabi = sysconfig.get_config_var("SOABI") or "unknown"
    extension_suffix = sysconfig.get_config_var("EXT_SUFFIX") or "unknown"
    receipt_rows: list[dict[str, object]] = []
    manifest_rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for module, binary_value, source_value in binaries:
        if module in seen:
            raise ValueError(f"duplicate module {module}")
        seen.add(module)
        binary = binary_value.resolve()
        if not binary.is_file():
            raise FileNotFoundError(binary)
        source = _source_path(module, source_value, repo_root)
        if not source.is_file():
            raise FileNotFoundError(source)
        package_binary = package_dir / binary.name
        shutil.copy2(binary, package_binary)
        binary_digest = sha256_file(package_binary)
        source_relative = str(source.relative_to(repo_root))
        source_digest = sha256_file(source)
        row = {
            "module": module,
            "source": source_relative,
            "source_sha256": source_digest,
            "binary_sha256": binary_digest,
            "python_soabi": soabi,
            "extension_suffix": extension_suffix,
            "compiler": platform.python_compiler(),
            "platform": platform.platform(),
            "cxx_standard": 23,
        }
        receipt_rows.append(row)
        manifest_rows.append({
            "module": module,
            "python_soabi": soabi,
            "extension_suffix": extension_suffix,
            "install_relative_path": f"native_extensions/{binary.name}",
            "binary_sha256": binary_digest,
            "sources": [{"path": source_relative, "sha256": source_digest}],
            "source_identity": identity,
            "build": {"compiler": row["compiler"], "platform": row["platform"], "cxx_standard": 23},
        })
    receipt = {
        "schema": "autotessell/native-surface-bl-package-build/v2",
        "package": "native-surface-bl-front/v1",
        "source_identity": identity,
        "modules": receipt_rows,
    }
    receipt_path = output / "native-surface-bl-build-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt_digest = sha256_file(receipt_path)
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "package": "native-surface-bl-front/v1",
        "modules": manifest_rows,
        "authority_receipt_relative_path": receipt_path.name,
        "authority_receipt_sha256": receipt_digest,
        "source_identity": identity,
    }
    for row in manifest_rows:
        row["authority_receipt_relative_path"] = receipt_path.name
        row["authority_receipt_sha256"] = receipt_digest
    manifest["manifest_payload_sha256"] = payload_digest(manifest)
    manifest_path = output / "native-extension-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def _parse_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        return "native_surface_bl_folded_plate", Path(value)
    module, binary = value.split("=", 1)
    if not module or not binary:
        raise ValueError(f"invalid --binary module=path: {value}")
    return module, Path(binary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("generate", choices=["generate"])
    parser.add_argument("--binary", action="append", required=True,
                        help="binary path, or module=path; repeat for a bundle")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=None,
                        help="legacy/source override for the single binary")
    parser.add_argument("--source-module", action="append", default=[],
                        help="module=source path override; repeat as needed")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    source_overrides: dict[str, Path] = {}
    for item in args.source_module:
        module, source = item.split("=", 1)
        source_overrides[module] = Path(source)
    specs = [_parse_spec(item) for item in args.binary]
    binaries = [
        (module, binary, args.source if len(specs) == 1 and args.source is not None else source_overrides.get(module))
        for module, binary in specs
    ]
    manifest = generate(binaries, args.output, args.repo_root)
    print(json.dumps({"manifest": str(manifest), "release_claim": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
