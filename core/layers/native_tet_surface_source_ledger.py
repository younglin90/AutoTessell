"""Validator for the user-declared provisional Native Tet source ledger."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_native_tet_surface_ledger(ledger_path: str | Path, root: str | Path) -> dict[str, Any]:
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    root_path = Path(root)
    errors: list[str] = []
    if ledger.get("schema") != "NativeTetSurfaceSourceLedger/v1":
        errors.append("schema_mismatch")
    if ledger.get("status") != "USER_DECLARED_PROVISIONAL":
        errors.append("authority_status_mismatch")
    for source in ledger.get("sources", []):
        path = root_path / source["path"]
        if not path.is_file():
            errors.append(f"missing_source:{source['case']}")
            continue
        if _sha256(path) != source["sha256"]:
            errors.append(f"source_hash_mismatch:{source['case']}")
        count = int(source["entity_count"])
        ranges = source.get("mapping_ranges", [])
        covered: list[int] = []
        for item in ranges:
            if item["start"] < 0 or item["end"] < item["start"] or item["end"] >= count:
                errors.append(f"range_out_of_bounds:{source['case']}")
                continue
            covered.extend(range(item["start"], item["end"] + 1))
            for field in ("patch", "feature", "physical_group", "component"):
                if not isinstance(item.get(field), str) or not item[field]:
                    errors.append(f"missing_mapping_field:{source['case']}:{field}")
        if sorted(covered) != list(range(count)):
            errors.append(f"range_coverage_not_bijective:{source['case']}")
    return {
        "valid_source_binding": not errors,
        "errors": errors,
        "status": ledger.get("status"),
        "release_eligible": False,
        "runtime_route": "default_off",
        "feature_authority": False,
        "wall_edge_authority": False,
    }
