"""Measure the persisted Native Tet corpus without regenerating it."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evaluator.native_canonical_quality_witness import (  # noqa: E402
    build_canonical_volume_quality_witness,
)
from core.evaluator.native_quality_witness_admission import (  # noqa: E402
    validate_native_quality_witness,
)


def _lineage(certificate: dict[str, object]) -> dict[str, object]:
    return {
        "feature": {"sha256": certificate.get("feature_sha256"), "preserved": certificate.get("feature_preserved")},
        "patch": {"sha256": certificate.get("patch_sha256"), "preserved": certificate.get("patch_preserved")},
        "physical_group": {"sha256": certificate.get("physical_group_sha256"), "preserved": certificate.get("physical_groups_preserved")},
        "component": {"bijective": certificate.get("component_bijection")},
        "provenance": {"sha256": certificate.get("provenance_sha256"), "complete": certificate.get("provenance_complete")},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for row in manifest.get("cases", ()):
        if not isinstance(row, dict) or not str(row.get("id", "")).startswith("native-tet"):
            continue
        case_dir = args.campaign_root / "cases" / str(row["id"]) / "run-0"
        certificate = row.get("source_output_authority", {})
        if not isinstance(certificate, dict):
            certificate = {}
        lineage = _lineage(certificate)
        witnesses = [
            build_canonical_volume_quality_witness(case_dir, entity_lineage=lineage)
            for _ in range(3)
        ]
        first = witnesses[0]
        digest_list = [item.get("witness_sha256") for item in witnesses]
        admission = validate_native_quality_witness(first, requested_layers=0)
        quality = first.get("quality", {}) if isinstance(first, dict) else {}
        rows.append({
            "id": row.get("id"),
            "case_dir": str(case_dir),
            "accepted": first.get("accepted") is True,
            "witness_replay_identical": len(digest_list) == 3 and len(set(digest_list)) == 1,
            "witness_sha256": first.get("witness_sha256"),
            "admission": admission,
            "quality": quality,
            "volume_quality": first.get("volume_quality"),
            "strict_topology": row.get("strict_topology"),
        })
    payload = {
        "schema": "autotessell/native-tet-corpus-quality/v1",
        "manifest": str(args.manifest),
        "rows": rows,
        "accepted_rows": sum(row["admission"].get("accepted") is True for row in rows),
        "replayed_rows": sum(row["witness_replay_identical"] is True for row in rows),
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if payload["accepted_rows"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
