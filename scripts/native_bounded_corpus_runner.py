#!/usr/bin/env python3
"""Run bounded native release-corpus nodes with an honest status taxonomy.

This is an evidence runner, not a release promoter.  It executes each supplied
pytest node in its own process group, records output/resource evidence, and
classifies a timeout as ``no_conclusion`` rather than PASS or FAIL.  It never
mutates source fixtures or changes engine routing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
from typing import Any

SCHEMA = "autotessell/native-bounded-corpus/v1"


def _group_metrics(pgid: int) -> tuple[int, float]:
    rss_total = 0
    cpu_seconds = 0.0
    hz = float(os.sysconf("SC_CLK_TCK"))
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().split()
            if len(fields) < 15 or int(fields[4]) != pgid:
                continue
            cpu_seconds += (int(fields[13]) + int(fields[14])) / hz
            for line in (entry / "status").read_text(errors="replace").splitlines():
                if line.startswith("VmRSS:"):
                    rss_total += int(line.split()[1])
                    break
        except (FileNotFoundError, PermissionError, ValueError, IndexError):
            continue
    return rss_total, cpu_seconds


def _phase(line: str) -> str:
    lowered = line.lower()
    if "collected " in lowered:
        return "collection_complete"
    if "passed" in lowered or "failed" in lowered or "error" in lowered:
        return "pytest_summary"
    return "test_execution"


def run_node(node: str, timeout_s: float) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q", node, "--disable-warnings"]
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    pgid = process.pid
    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    selector.register(process.stdout, selectors.EVENT_READ)
    output_digest = hashlib.sha256()
    tail: list[str] = []
    phase = "spawned"
    phase_events: list[dict[str, Any]] = [{"phase": phase, "elapsed_s": 0.0}]
    peak_rss = 0
    peak_cpu = 0.0
    timed_out = False
    while True:
        for key, _ in selector.select(timeout=0.25):
            line = key.fileobj.readline()
            if line:
                output_digest.update(line.encode("utf-8", errors="replace"))
                tail.append(line.rstrip("\n"))
                del tail[:-80]
                next_phase = _phase(line)
                if next_phase != phase:
                    phase = next_phase
                    phase_events.append({"phase": phase, "elapsed_s": round(time.monotonic() - started, 3)})
            else:
                selector.unregister(key.fileobj)
        rss, cpu = _group_metrics(pgid)
        peak_rss = max(peak_rss, rss)
        peak_cpu = max(peak_cpu, cpu)
        if process.poll() is not None and not selector.get_map():
            break
        if time.monotonic() - started > timeout_s:
            timed_out = True
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5.0)
            break
    selector.close()
    rss, cpu = _group_metrics(pgid)
    peak_rss = max(peak_rss, rss)
    peak_cpu = max(peak_cpu, cpu)
    elapsed = time.monotonic() - started
    status = "no_conclusion" if timed_out else ("pass" if process.returncode == 0 else "fail")
    return {
        "node": node,
        "command": command,
        "status": status,
        "exit_code": process.returncode,
        "timeout_s": timeout_s,
        "elapsed_s": round(elapsed, 3),
        "peak_group_rss_kb": peak_rss,
        "peak_group_cpu_s": round(peak_cpu, 3),
        "phase_events": phase_events,
        "output_sha256": output_digest.hexdigest(),
        "output_tail": tail,
        "timeout_is_no_conclusion": timed_out,
        "release_claim": False,
    }


def aggregate_status(cases: list[dict[str, Any]]) -> str:
    statuses = {case.get("status") for case in cases}
    if "no_conclusion" in statuses:
        return "has_no_conclusion"
    if "fail" in statuses:
        return "has_failures"
    return "all_bounded_nodes_passed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("nodes", nargs="+")
    args = parser.parse_args()
    started = time.time()
    cases = [run_node(node, args.timeout_s) for node in args.nodes]
    payload = {
        "schema": SCHEMA,
        "started_unix_s": started,
        "finished_unix_s": time.time(),
        "timeout_s": args.timeout_s,
        "cases": cases,
        "aggregate_status": aggregate_status(cases),
        "release_claim": False,
        "protected_poly_mutation": False,
        "route_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"aggregate_status": payload["aggregate_status"], "cases": cases}, indent=2))
    return 0 if payload["aggregate_status"] == "all_bounded_nodes_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
