"""Verify the complete native release matrix including measured authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.evaluator.native_release_authority_gate import (
    validate_native_release_authority_matrix,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        value = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        value = None
    report = validate_native_release_authority_matrix(value)
    arguments.evidence.write_text(
        json.dumps(report.as_dict(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
