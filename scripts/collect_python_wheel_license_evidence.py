#!/usr/bin/env python3
"""Reproduce exact PyPI wheel license evidence without license inference."""

from __future__ import annotations

import argparse
import email.policy
import hashlib
import json
import sys
import urllib.request
import zipfile
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "AutoTessell-license-audit/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return bytes(response.read())


def _release_artifact(seed: dict[str, Any]) -> dict[str, str]:
    pypi_json_url = seed["pypi_json_url"]
    release = json.loads(_download(pypi_json_url))
    artifact_record = seed["artifact"]
    artifact = {key: str(artifact_record[key]) for key in ("filename", "url", "sha256")}
    matches = [
        item
        for item in release.get("urls", [])
        if item.get("filename") == artifact["filename"]
        and item.get("url") == artifact["url"]
        and item.get("digests", {}).get("sha256") == artifact["sha256"]
    ]
    if len(matches) != 1:
        raise ValueError(f"{seed['id']}: artifact is not uniquely declared by {pypi_json_url}")
    if release.get("info", {}).get("version") != seed["version"]:
        raise ValueError(f"{seed['id']}: PyPI release version mismatch")
    return artifact


def _metadata_record(seed: dict[str, Any], wheel_data: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(BytesIO(wheel_data)) as archive:
        metadata_paths = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise ValueError(f"{seed['id']}: expected exactly one wheel METADATA")
        metadata_path = metadata_paths[0]
        metadata_data = archive.read(metadata_path)
        metadata = BytesParser(policy=email.policy.default).parsebytes(metadata_data)
        if metadata.get("Name", "").lower().replace("_", "-") != seed["name"]:
            raise ValueError(f"{seed['id']}: wheel METADATA name mismatch")
        if metadata.get("Version") != seed["version"]:
            raise ValueError(f"{seed['id']}: wheel METADATA version mismatch")

        dist_info = str(PurePosixPath(metadata_path).parent)
        license_files: list[dict[str, str]] = []
        for declared_path in metadata.get_all("License-File", []):
            candidates = (
                f"{dist_info}/licenses/{declared_path}",
                f"{dist_info}/{declared_path}",
            )
            archive_path = next((path for path in candidates if path in archive.namelist()), None)
            if archive_path is None:
                raise ValueError(
                    f"{seed['id']}: declared license file missing from wheel: {declared_path}"
                )
            license_files.append(
                {
                    "declared_path": declared_path,
                    "archive_path": archive_path,
                    "sha256": _sha256(archive.read(archive_path)),
                }
            )

    license_field = metadata.get("License")
    return {
        "path": metadata_path,
        "sha256": _sha256(metadata_data),
        "metadata_version": metadata.get("Metadata-Version"),
        "name": metadata.get("Name"),
        "version": metadata.get("Version"),
        "requires_python": metadata.get("Requires-Python"),
        "license_expression": metadata.get("License-Expression"),
        "license_field_sha256": (
            _sha256(license_field.encode("utf-8")) if license_field is not None else None
        ),
        "license_field_length": len(license_field) if license_field is not None else 0,
        "license_classifiers": [
            value for value in metadata.get_all("Classifier", []) if value.startswith("License ::")
        ],
        "license_files": license_files,
    }


def collect_document(seed_document: dict[str, Any]) -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    for seed in seed_document["packages"]:
        artifact = _release_artifact(seed)
        wheel_data = _download(artifact["url"])
        if _sha256(wheel_data) != artifact["sha256"]:
            raise ValueError(f"{seed['id']}: downloaded artifact SHA-256 mismatch")
        packages.append(
            {
                "id": seed["id"],
                "role": seed["role"],
                "requirement": seed["requirement"],
                "name": seed["name"],
                "version": seed["version"],
                "pypi_json_url": seed["pypi_json_url"],
                "artifact": artifact,
                "metadata": _metadata_record(seed, wheel_data),
            }
        )
    return {
        "schema_version": 1,
        "profile": "python-wheel-core",
        "target": seed_document["target"],
        "packages": packages,
    }


def _canonical_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Rewrite the evidence file after exact artifact verification",
    )
    args = parser.parse_args()
    try:
        original = args.evidence.read_bytes()
        seed = json.loads(original)
        regenerated = _canonical_bytes(collect_document(seed))
        if args.refresh:
            args.evidence.write_bytes(regenerated)
        elif regenerated != original:
            raise ValueError("evidence bytes differ from the regenerated canonical document")
    except (KeyError, OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"python wheel evidence error: {exc}", file=sys.stderr)
        return 1
    print(f"python-wheel-license-evidence: packages={len(seed['packages'])} verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
