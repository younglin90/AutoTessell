"""Audit an explicit native corpus config without meshing or copying."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.evaluator.native_campaign_readiness import audit_native_campaign_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = audit_native_campaign_config(args.config)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": result["accepted"], "reasons": len(result["reasons"]), "cases": len(result["cases"])}, sort_keys=True))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
