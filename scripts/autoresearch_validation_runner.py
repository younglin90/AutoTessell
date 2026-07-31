"""Bounded manifest validation with durable, fail-closed JSON evidence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import signal
import time
from pathlib import Path

_MAX_CONCURRENCY = 2
_TERMINATION_GRACE_SECONDS = 1.0


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _elapsed_seconds(started_at: float) -> float:
    return time.monotonic() - started_at


def _valid_concurrency(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= _MAX_CONCURRENCY else None


def _valid_command(value: object) -> list[str] | None:
    if not isinstance(value, list) or not value or not all(isinstance(part, str) for part in value):
        return None
    return list(value)


def _valid_timeout(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    timeout = float(value)
    return timeout if math.isfinite(timeout) and timeout > 0.0 else None


def _base_result(item: object, *, command: list[str] | None = None) -> dict[str, object]:
    name = item.get("name") if isinstance(item, dict) else None
    return {"name": name, "command": command}


async def _terminate_process_group(process: asyncio.subprocess.Process) -> str:
    """Terminate a timed-out process group; return durable TERM/KILL evidence."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return "TERM"
    try:
        await asyncio.wait_for(process.wait(), timeout=_TERMINATION_GRACE_SECONDS)
        return "TERM"
    except TimeoutError:
        os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
        return "KILL"


async def run_job(item: object) -> dict[str, object]:
    """Run one declared job; every non-PASS outcome has explicit evidence."""
    raw_item = item if isinstance(item, dict) else {}
    command = _valid_command(raw_item.get("command"))
    timeout = _valid_timeout(raw_item.get("timeout_seconds"))
    if command is None or timeout is None:
        result = _base_result(raw_item, command=command)
        result.update(
            {
                "status": "UNVERIFIED",
                "result_status": "UNVERIFIED",
                "error": "invalid manifest item",
            }
        )
        return result

    started_at = time.monotonic()
    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        status = "PASS" if process.returncode == 0 else "ERROR"
        result = _base_result(raw_item, command=command)
        result.update(
            {
                "started_monotonic": started_at,
                "elapsed_seconds": _elapsed_seconds(started_at),
                "exit_code": process.returncode,
                "status": status,
                "result_status": status,
                "stdout_sha256": _digest(stdout),
                "stderr_sha256": _digest(stderr),
            }
        )
        return result
    except TimeoutError:
        termination = "TERM"
        if process is not None:
            termination = await _terminate_process_group(process)
        result = _base_result(raw_item, command=command)
        result.update(
            {
                "started_monotonic": started_at,
                "elapsed_seconds": _elapsed_seconds(started_at),
                "termination": termination,
                "status": "TIMEOUT",
                "result_status": "TIMEOUT",
            }
        )
        return result
    except Exception as exc:
        result = _base_result(raw_item, command=command)
        result.update(
            {
                "started_monotonic": started_at,
                "elapsed_seconds": _elapsed_seconds(started_at),
                "status": "ERROR",
                "result_status": "ERROR",
                "error": str(exc),
            }
        )
        return result


def _manifest_failure(error: str) -> dict[str, object]:
    return {"status": "UNVERIFIED", "result_status": "UNVERIFIED", "error": error, "results": []}


async def main(manifest: object) -> dict[str, object]:
    """Validate a bounded manifest without creating a zero-permit semaphore."""
    if not isinstance(manifest, dict):
        return _manifest_failure("manifest must be object")
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list):
        return _manifest_failure("jobs must be list")
    concurrency = _valid_concurrency(manifest.get("concurrency", _MAX_CONCURRENCY))
    if concurrency is None:
        return _manifest_failure(f"concurrency must be integer in range 1..{_MAX_CONCURRENCY}")

    semaphore = asyncio.Semaphore(concurrency)

    async def guarded(job: object) -> dict[str, object]:
        async with semaphore:
            return await run_job(job)

    results = await asyncio.gather(*(guarded(job) for job in jobs))
    passed = bool(results) and all(result["status"] == "PASS" for result in results)
    return {
        "status": "PASS" if passed else "UNVERIFIED",
        "result_status": "PASS" if passed else "UNVERIFIED",
        "concurrency": concurrency,
        "results": results,
    }


def _read_manifest(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"jobs": None, "manifest_read_error": str(exc)}


def _write_evidence(path: Path, result: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    arguments = parser.parse_args()
    outcome = asyncio.run(main(_read_manifest(arguments.manifest)))
    _write_evidence(arguments.evidence, outcome)
    raise SystemExit(0 if outcome["status"] == "PASS" else 1)
