"""Parse OpenFOAM checkMesh stdout into a structured result."""

import re
from dataclasses import dataclass


@dataclass
class CheckMeshResult:
    passed: bool
    max_non_orthogonality: float | None
    max_skewness: float | None
    num_cells: int | None
    raw_output: str


def parse_checkmesh_output(stdout: str) -> CheckMeshResult:
    passed = "Mesh OK." in stdout

    return CheckMeshResult(
        passed=passed,
        max_non_orthogonality=_extract_float(stdout, r"Max non-orthogonality\s*=\s*([\d.]+)"),
        max_skewness=_extract_float(stdout, r"Max skewness\s*=\s*([\d.]+)"),
        num_cells=_extract_int(stdout, r"cells:\s+(\d+)"),
        raw_output=stdout,
    )


def _extract_float(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _extract_int(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None
