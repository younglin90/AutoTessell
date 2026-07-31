"""Validation-runner manifest and CLI evidence contracts."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.autoresearch_validation_runner import main

_ROOT = Path(__file__).resolve().parents[1]
_RUNNER = _ROOT / "scripts" / "autoresearch_validation_runner.py"


def test_manifest_reports_pass_error_and_invalid_job_without_false_aggregate_pass() -> None:
    result = asyncio.run(
        main(
            {
                "concurrency": 2,
                "jobs": [
                    {"name": "ok", "command": ["/bin/true"], "timeout_seconds": 1},
                    {"name": "bad", "command": ["/bin/false"], "timeout_seconds": 1},
                    {"name": "invalid"},
                ],
            }
        )
    )

    assert result["status"] == "UNVERIFIED"
    assert result["result_status"] == "UNVERIFIED"
    assert [item["status"] for item in result["results"]] == ["PASS", "ERROR", "UNVERIFIED"]


@pytest.mark.parametrize("concurrency", (0, -1, 3, True, 1.5, "2"))
def test_invalid_concurrency_is_deadlock_free_and_unverified(concurrency: object) -> None:
    manifest = {
        "concurrency": concurrency,
        "jobs": [{"command": ["/bin/true"], "timeout_seconds": 1}],
    }
    result = asyncio.run(
        asyncio.wait_for(
            main(manifest),
            timeout=1,
        )
    )

    assert result == {
        "status": "UNVERIFIED",
        "result_status": "UNVERIFIED",
        "error": "concurrency must be integer in range 1..2",
        "results": [],
    }


def test_cli_writes_pass_and_timeout_evidence_with_required_timeout_fields(tmp_path: Path) -> None:
    pass_manifest = tmp_path / "pass.json"
    pass_evidence = tmp_path / "nested" / "pass-evidence.json"
    pass_manifest.write_text(
        json.dumps(
            {
                "concurrency": 1,
                "jobs": [
                    {"name": "true", "command": ["/bin/true"], "timeout_seconds": 1}
                ],
            }
        ),
        encoding="utf-8",
    )
    passed = subprocess.run(
        [sys.executable, str(_RUNNER), str(pass_manifest), "--evidence", str(pass_evidence)],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert passed.returncode == 0
    assert json.loads(pass_evidence.read_text(encoding="utf-8"))["status"] == "PASS"

    timeout_manifest = tmp_path / "timeout.json"
    timeout_evidence = tmp_path / "timeout-evidence.json"
    timeout_manifest.write_text(
        json.dumps(
            {
                "concurrency": 1,
                "jobs": [
                    {
                        "name": "timeout",
                        "command": [sys.executable, "-c", "import time; time.sleep(10)"],
                        "timeout_seconds": 0.05,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    timed_out = subprocess.run(
        [sys.executable, str(_RUNNER), str(timeout_manifest), "--evidence", str(timeout_evidence)],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    evidence = json.loads(timeout_evidence.read_text(encoding="utf-8"))
    job = evidence["results"][0]
    assert timed_out.returncode == 1
    assert evidence["status"] == "UNVERIFIED"
    assert job["status"] == job["result_status"] == "TIMEOUT"
    assert job["command"] == [sys.executable, "-c", "import time; time.sleep(10)"]
    assert job["termination"] in {"TERM", "KILL"}
    assert isinstance(job["elapsed_seconds"], float) and job["elapsed_seconds"] > 0.0


def test_cli_invalid_concurrency_writes_unverified_evidence_without_running_jobs(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "invalid-concurrency.json"
    evidence_path = tmp_path / "invalid-concurrency-evidence.json"
    manifest.write_text(
        json.dumps({"concurrency": 0, "jobs": [{"command": ["/bin/true"], "timeout_seconds": 1}]}),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, str(_RUNNER), str(manifest), "--evidence", str(evidence_path)],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert completed.returncode == 1
    assert evidence == {
        "error": "concurrency must be integer in range 1..2",
        "result_status": "UNVERIFIED",
        "results": [],
        "status": "UNVERIFIED",
    }
