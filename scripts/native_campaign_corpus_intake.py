#!/usr/bin/env python3
"""Seal an immutable native campaign corpus from an explicit JSON config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.evaluator.native_campaign_intake import prepare_native_campaign_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("cases"), dict):
        raise SystemExit("config must contain a cases object")
    cases = {}
    for case_id, raw in config["cases"].items():
        if not isinstance(raw, dict):
            raise SystemExit(f"case {case_id!r} must be an object")
        normalized = dict(raw)
        for key in ("source", "baseline"):
            if key in normalized:
                normalized[key] = str((config_path.parent / normalized[key]).resolve())
        for section in ("authority", "semantic", "provenance"):
            normalized[section] = [
                str((config_path.parent / value).resolve())
                for value in normalized.get(section, [])
            ]
        cases[case_id] = normalized
    lock = prepare_native_campaign_corpus(
        args.destination.resolve(),
        cases,
        corpus_id=str(config.get("corpus_id", "native-release-corpus")),
    )
    print(json.dumps({"corpus_id": lock["corpus_id"], "lock_sha256": lock["lock_sha256"], "cases": sorted(lock["cases"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
