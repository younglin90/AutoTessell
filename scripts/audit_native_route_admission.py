"""Audit one native product route against an explicit corpus config."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.evaluator.native_campaign_readiness import audit_native_campaign_config
from core.evaluator.native_route_admission import admit_native_route_candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--product", required=True)
    parser.add_argument("--source-kind", required=True)
    parser.add_argument("--layers", type=int, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    audit = audit_native_campaign_config(args.config)
    cases = {
        row.get("id"): row
        for row in audit.get("cases", ())
        if isinstance(row, dict)
    }
    rows: list[dict[str, object]] = []
    for case_id in sorted(cases):
        case = cases[case_id]
        for layers in args.layers:
            result = admit_native_route_candidate(
                args.product,
                boundary_layers=layers,
                source_kind=args.source_kind,
                corpus_case=case,
            )
            rows.append({
                "case_id": case_id,
                "boundary_layers": layers,
                **result,
            })
    payload = {
        "schema": "autotessell/native-route-admission-audit/v1",
        "product": args.product,
        "source_kind": args.source_kind,
        "corpus_audit": audit,
        "rows": rows,
        "accepted_rows": sum(row.get("accepted") is True for row in rows),
        "refused_rows": sum(row.get("accepted") is not True for row in rows),
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if payload["refused_rows"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
