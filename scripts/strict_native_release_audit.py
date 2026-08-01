"""Run an independent strict topology audit over explicit release artifacts.

This command never invokes a generator.  It reads only the supplied case
directories and writes a deterministic JSON evidence bundle.  A non-zero exit
status means at least one case was malformed or failed a strict invariant.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.evaluator.strict_volume_topology import audit_strict_volume_topology


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dirs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    cases = []
    for case_dir in arguments.case_dirs:
        audit = audit_strict_volume_topology(case_dir)
        row = audit.as_dict()
        row["case_dir"] = str(case_dir.resolve())
        cases.append(row)
    report = {
        "schema": "autotessell/strict-native-release-audit/v1",
        "cases": cases,
        "all_valid": bool(cases) and all(bool(row["valid"]) for row in cases),
    }
    arguments.output.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if report["all_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
