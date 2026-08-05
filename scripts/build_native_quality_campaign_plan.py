"""Write a configurable quality-first native campaign plan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.evaluator.native_quality_campaign_matrix import build_quality_campaign_matrix


def _csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--products", default="native-tet,native-hex,native-poly,native-tri,strict-quad,tri-quad")
    parser.add_argument("--fixtures", default="cube,sphere,naca,complex")
    parser.add_argument("--boundary-layers", default="0,1,5")
    parser.add_argument("--replays", type=int, default=3)
    args = parser.parse_args()
    plan = build_quality_campaign_matrix(
        products=_csv(args.products), fixtures=_csv(args.fixtures),
        boundary_layers=tuple(int(value) for value in _csv(args.boundary_layers)),
        replay_count=args.replays,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": True, "plan_sha256": plan["plan_sha256"], "rows": plan["expected_row_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
