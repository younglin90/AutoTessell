"""Repository audit for explicit surface source-authority ledgers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = ("patch", "feature", "physical_group", "component")
DATA_SUFFIXES = {".json", ".yaml", ".yml", ".csv", ".ledger"}
IGNORE_PARTS = {".git", "__pycache__", ".venv", "build"}
LEDGER_HINTS = ("ledger", "authority", "mapping", "provenance")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_repository_authority(root: str | Path) -> dict[str, Any]:
    """Find explicitly named data ledgers; never treat generic reports as authority."""
    root_path = Path(root)
    candidates: list[dict[str, Any]] = []
    for path in sorted(root_path.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in DATA_SUFFIXES or any(part in IGNORE_PARTS for part in path.parts):
            continue
        lower_name = path.name.lower()
        if not any(hint in lower_name for hint in LEDGER_HINTS):
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fields = tuple(field for field in REQUIRED_FIELDS if field in text)
        candidates.append({
            "path": str(path.relative_to(root_path)),
            "sha256": _digest(path),
            "required_fields_found": list(fields),
            "complete_field_set": set(fields) == set(REQUIRED_FIELDS),
            "surface_authority_claim": "surface" in text.lower() or "stl" in text.lower(),
        })
    usable = [item for item in candidates if item["complete_field_set"] and item["surface_authority_claim"]]
    return {
        "schema": "NativeSurfaceAuthorityAudit/v1",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "usable_ledgers": usable,
        "authority_found": bool(usable),
        "blocker": None if usable else "no_explicit_surface_facet_or_brep_authority_ledger_found",
        "route": "default_off",
    }
