"""Contracts for first-party pytest collection from repository root."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_COLLECTION_SUMMARY = re.compile(r"^([0-9]+) tests collected(?: in .*)?$", re.MULTILINE)


def _collect_nodeids(*arguments: str) -> tuple[int, tuple[str, ...]]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output[-4000:]

    summary = _COLLECTION_SUMMARY.search(output)
    assert summary is not None, output[-4000:]
    nodeids = tuple(line for line in result.stdout.splitlines() if "::" in line)
    assert nodeids
    count = int(summary.group(1))
    assert len(nodeids) == count
    return count, nodeids


def test_pytest_config_declares_tests_as_the_first_party_root() -> None:
    config = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert config["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]


def test_bare_root_collection_matches_explicit_first_party_tests() -> None:
    root_count, root_nodeids = _collect_nodeids()
    explicit_count, explicit_nodeids = _collect_nodeids("tests")

    assert root_count == explicit_count
    assert root_nodeids == explicit_nodeids
    assert all(nodeid.startswith("tests/") for nodeid in root_nodeids)
