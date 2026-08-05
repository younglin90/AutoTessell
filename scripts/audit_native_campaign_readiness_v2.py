#!/usr/bin/env python3
"""Run the strict v2 corpus readiness audit and emit a refusal/pass receipt."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.evaluator.native_campaign_readiness_v2 import audit_native_campaign_config_v2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_native_campaign_config_v2(args.config)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result.get("accepted") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
