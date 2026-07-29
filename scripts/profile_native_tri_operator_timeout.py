"""Profile the guarded native-tri round on one fixture without changing production code.

This diagnostic mirrors ``OperatorTransaction.run_one_round`` phase order and
adds only wall-clock checkpoints, call counters, and a bounded alarm.  It is
intentionally separate from the operator implementation so a timeout cannot
leave a partially modified production module behind.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.analyzer.readers import read_stl  # noqa: E402
from core.preprocessor.native_tri.operator_loop import OperatorTransaction  # noqa: E402


FIXTURE = ROOT / "tests/benchmarks/high_genus_dual_torus.stl"
LIMIT_SECONDS = float(os.environ.get("TRI_PROFILE_TIMEOUT_S", "180"))


class PhaseTimeout(RuntimeError):
    pass


phase = "initializing"
started = 0.0


def _alarm(_signum: int, _frame: object) -> None:
    elapsed = time.perf_counter() - started
    print(json.dumps({"status": "timeout", "phase": phase, "elapsed_s": elapsed}), flush=True)
    raise PhaseTimeout(f"phase timeout: {phase}")


def _phase_start(name: str) -> float:
    global phase
    phase = name
    stamp = time.perf_counter()
    print(json.dumps({"event": "phase_start", "phase": name, "elapsed_s": stamp - started}), flush=True)
    return stamp


def _phase_end(name: str, stamp: float, **values: object) -> None:
    now = time.perf_counter()
    payload = {"event": "phase_end", "phase": name, "elapsed_s": now - started, "phase_s": now - stamp}
    payload.update(values)
    print(json.dumps(payload, sort_keys=True), flush=True)


def main() -> int:
    global started
    started = time.perf_counter()
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, LIMIT_SECONDS)
    mesh = read_stl(str(FIXTURE))
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    lengths = np.concatenate(
        [
            np.linalg.norm(vertices[faces[:, i]] - vertices[faces[:, (i + 1) % 3]], axis=1)
            for i in range(3)
        ]
    )
    target = float(np.median(lengths[lengths > 0.0]))
    transaction = OperatorTransaction(vertices, faces, target_edge_length=target)
    reports = []

    stamp = _phase_start("split")
    edges = transaction._unique_edges()
    split_candidates = 0
    for edge in edges:
        if transaction.should_split_edge(edge, target):
            split_candidates += 1
            reports.append(transaction.split_edge(edge, target))
    _phase_end(
        "split",
        stamp,
        input_edges=len(edges),
        candidate_count=split_candidates,
        report_count=split_candidates,
        vertices=len(transaction.state.vertices),
        faces=len(transaction.state.faces),
    )

    stamp = _phase_start("collapse")
    processed: set[tuple[int, int]] = set()
    collapse_scans = 0
    collapse_candidates = 0
    collapse_reports = 0
    while True:
        collapse_scans += 1
        current_edges = transaction._unique_edges()
        candidates = [
            edge
            for edge in current_edges
            if edge not in processed and transaction.should_collapse_edge(edge, target)
        ]
        collapse_candidates += len(candidates)
        if not candidates:
            break
        edge = min(candidates, key=transaction._edge_length)
        reports.append(transaction.collapse_edge(edge, target))
        collapse_reports += 1
        processed.add(edge)
        if collapse_reports % 25 == 0:
            print(
                json.dumps(
                    {
                        "event": "progress",
                        "phase": "collapse",
                        "elapsed_s": time.perf_counter() - started,
                        "scan_count": collapse_scans,
                        "candidate_count": collapse_candidates,
                        "report_count": collapse_reports,
                        "vertices": len(transaction.state.vertices),
                        "faces": len(transaction.state.faces),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    _phase_end(
        "collapse",
        stamp,
        scan_count=collapse_scans,
        candidate_count=collapse_candidates,
        report_count=collapse_reports,
        vertices=len(transaction.state.vertices),
        faces=len(transaction.state.faces),
    )

    stamp = _phase_start("flip")
    processed.clear()
    flip_scans = 0
    flip_candidates = 0
    flip_reports = 0
    while True:
        flip_scans += 1
        current_edges = transaction._unique_edges()
        candidates = [
            edge
            for edge in current_edges
            if edge not in processed and transaction.should_flip_edge(edge)
        ]
        flip_candidates += len(candidates)
        if not candidates:
            break
        edge = min(candidates, key=transaction._edge_length)
        reports.append(transaction.flip_edge(edge))
        flip_reports += 1
        processed.add(edge)
        if flip_reports % 25 == 0:
            print(
                json.dumps(
                    {
                        "event": "progress",
                        "phase": "flip",
                        "elapsed_s": time.perf_counter() - started,
                        "scan_count": flip_scans,
                        "candidate_count": flip_candidates,
                        "report_count": flip_reports,
                        "vertices": len(transaction.state.vertices),
                        "faces": len(transaction.state.faces),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    _phase_end(
        "flip",
        stamp,
        scan_count=flip_scans,
        candidate_count=flip_candidates,
        report_count=flip_reports,
        vertices=len(transaction.state.vertices),
        faces=len(transaction.state.faces),
    )
    signal.setitimer(signal.ITIMER_REAL, 0.0)
    print(json.dumps({"status": "complete", "report_count": len(reports)}), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PhaseTimeout:
        raise SystemExit(124)
