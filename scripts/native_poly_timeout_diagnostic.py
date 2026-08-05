#!/usr/bin/env python3
"""Read-only Native Poly per-node timeout and resource diagnostic."""

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


def _group_metrics(pgid: int) -> tuple[int, float]:
    rss_total = 0
    cpu_ticks = 0
    proc_root = Path("/proc")
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            stat_text = (entry / "stat").read_text()
            close = stat_text.rfind(")")
            fields = stat_text[close + 2 :].split()
            if len(fields) < 13 or int(fields[2]) != pgid:
                continue
            cpu_ticks += int(fields[11]) + int(fields[12])
            status = (entry / "status").read_text(errors="replace")
            for line in status.splitlines():
                if line.startswith("VmRSS:"):
                    rss_total += int(line.split()[1])
                    break
        except (FileNotFoundError, PermissionError, ValueError, IndexError):
            continue
    hz = float(os.sysconf("SC_CLK_TCK"))
    return rss_total, cpu_ticks / hz


def _phase(line: str) -> str:
    lower = line.lower()
    if "collected " in lower:
        return "collection_complete"
    if "passed" in lower or "failed" in lower or "error" in lower:
        return "pytest_summary"
    return "test_execution"


def _run_node(node: str, timeout_s: float) -> dict[str, Any]:
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
    digest = hashlib.sha256()
    tail: list[str] = []
    phase = "spawned"
    phase_events: list[dict[str, Any]] = [
        {"phase": phase, "elapsed_s": 0.0}
    ]
    peak_rss = 0
    peak_cpu = 0.0
    timed_out = False
    while True:
        for key, _ in selector.select(timeout=0.25):
            line = key.fileobj.readline()
            if line:
                digest.update(line.encode("utf-8", errors="replace"))
                tail.append(line.rstrip("\n"))
                del tail[:-80]
                next_phase = _phase(line)
                if next_phase != phase:
                    phase = next_phase
                    phase_events.append(
                        {
                            "phase": phase,
                            "elapsed_s": round(time.monotonic() - started, 3),
                        }
                    )
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
    outcome = "timeout_no_conclusion" if timed_out else (
        "passed" if process.returncode == 0 else "failed"
    )
    return {
        "node": node,
        "command": command,
        "pid": process.pid,
        "process_group": pgid,
        "outcome": outcome,
        "exit_code": process.returncode,
        "wall_timeout_s": timeout_s,
        "elapsed_s": round(elapsed, 3),
        "peak_group_rss_kb": peak_rss,
        "peak_group_cpu_s": round(peak_cpu, 3),
        "phase_events": phase_events,
        "output_sha256": digest.hexdigest(),
        "output_tail": tail,
        "protected_poly_mutation": False,
        "route_changed": False,
        "timeout_is_no_conclusion": timed_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("nodes", nargs="+")
    args = parser.parse_args()
    started = time.time()
    receipts = [_run_node(node, args.timeout_s) for node in args.nodes]
    payload = {
        "schema": "NativePolyTimeoutDiagnostic/v1",
        "started_unix_s": started,
        "finished_unix_s": time.time(),
        "workspace": str(Path.cwd()),
        "timeout_s": args.timeout_s,
        "protected_poly_mutation": False,
        "route_changed": False,
        "receipts": receipts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(
        [
            {
                "node": row["node"],
                "outcome": row["outcome"],
                "elapsed_s": row["elapsed_s"],
                "peak_group_rss_kb": row["peak_group_rss_kb"],
                "peak_group_cpu_s": row["peak_group_cpu_s"],
            }
            for row in receipts
        ],
        indent=2,
    ))
    return 0 if all(row["outcome"] == "passed" for row in receipts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
