"""Prepare an immutable native release corpus from existing campaign artifacts.

This module is intentionally a copy/hash operation.  It never invokes a
mesher, repair pass, parser re-triangulation, or baseline generator.  The
caller supplies every source, baseline, authority, semantic, and provenance
path explicitly so a release corpus cannot silently fall back to a different
geometry or product route.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

from .native_frozen_corpus import (
    REQUIRED_MESH_FILES,
    build_frozen_corpus_lock,
    seal_frozen_corpus_lock,
)


def _require_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label}_not_regular_file")


def _require_directory(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label}_not_directory")


def _copy_file(source: Path, destination: Path, label: str) -> None:
    _require_file(source, label)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_tree(source: Path, destination: Path, label: str) -> None:
    _require_directory(source, label)
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"{label}_symlink:{path.relative_to(source).as_posix()}")
    shutil.copytree(source, destination, symlinks=False)


def prepare_native_campaign_corpus(
    destination_root: str | Path,
    cases: Mapping[str, Mapping[str, Any]],
    *,
    corpus_id: str = "native-release-corpus",
) -> dict[str, Any]:
    """Copy explicitly selected campaign artifacts and write a write-once lock.

    Case configuration schema:

    ``{"source": "/raw/source.stl", "baseline": "/case",` 
    ``"authority": ["/certificate.json"], "semantic": [...],` 
    ``"provenance": [...]}``

    `baseline` must already contain `constant/polyMesh` with the five required
    files.  Authority/semantic/provenance paths are copied as opaque evidence;
    Gate4 interprets their schemas in the next admission card.
    """
    destination = Path(destination_root)
    if destination.exists():
        raise FileExistsError(destination)
    if not cases:
        raise ValueError("campaign_cases_empty")
    destination.mkdir(parents=True)
    required: dict[str, list[str]] = {}
    try:
        for case_id in sorted(cases):
            spec = cases[case_id]
            if not isinstance(spec, Mapping) or not case_id or "/" in case_id or "\\" in case_id:
                raise ValueError(f"campaign_case_spec_invalid:{case_id}")
            case_root = destination / case_id
            case_root.mkdir()
            source = Path(spec.get("source", ""))
            baseline = Path(spec.get("baseline", ""))
            source_name = source.name
            _copy_file(source, case_root / "source" / source_name, f"{case_id}.source")
            _copy_tree(baseline, case_root / "baseline", f"{case_id}.baseline")
            mesh_root = case_root / "baseline" / "constant" / "polyMesh"
            for filename in REQUIRED_MESH_FILES:
                _require_file(mesh_root / filename, f"{case_id}.baseline.{filename}")
            required_files = [
                f"source/{source_name}",
                *(f"baseline/constant/polyMesh/{filename}" for filename in REQUIRED_MESH_FILES),
            ]
            for section in ("authority", "semantic", "provenance"):
                values = spec.get(section, ())
                if isinstance(values, (str, Path)):
                    values = (values,)
                if not isinstance(values, (list, tuple)) or not values:
                    raise ValueError(f"{case_id}.{section}_evidence_missing")
                for index, raw_path in enumerate(values):
                    evidence = Path(raw_path)
                    target = case_root / section / f"{index:03d}_{evidence.name}"
                    _copy_file(evidence, target, f"{case_id}.{section}.{index}")
                    required_files.append(target.relative_to(case_root).as_posix())
            required[case_id] = required_files
        lock = build_frozen_corpus_lock(
            destination,
            {case_id: case_id for case_id in cases},
            required_files=required,
            corpus_id=corpus_id,
        )
        seal_frozen_corpus_lock(destination / "corpus.lock.json", lock)
        return lock
    except Exception:
        # The destination is deliberately left as an auditable failed intake;
        # callers must review/remove it explicitly instead of silently retrying.
        raise


__all__ = ["prepare_native_campaign_corpus"]
