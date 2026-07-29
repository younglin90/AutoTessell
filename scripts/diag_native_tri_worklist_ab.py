"""Report-only A/B for a local worklist candidate manager.

The production operator loop is not modified here.  The alternative keeps
stable vertex labels across compaction, maintains a heap ordered by current
edge length, and refreshes only edges in the one-ring changed by an accepted
collapse/flip.  It is compared with the current full-rescan implementation on
small fixtures for topology, quality, report counts, and byte-level output.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.analyzer import topology  # noqa: E402
from core.analyzer.readers import read_stl  # noqa: E402
from core.preprocessor.native_tri.operator_loop import OperatorTransaction  # noqa: E402


FIXTURES = (
    "tests/benchmarks/cube.stl",
    "tests/benchmarks/cylinder.stl",
    "tests/benchmarks/very_thin_disk_0_01mm.stl",
    "tests/benchmarks/extreme_aspect_ratio_needle.stl",
    "tests/benchmarks/multi_scale_sphere_with_micro_spikes.stl",
)


def _edges(faces: np.ndarray, vertices: set[int] | None = None) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    for face in faces.tolist():
        if vertices is not None and not any(int(vertex) in vertices for vertex in face):
            continue
        for first, second in zip(face, face[1:] + face[:1]):
            result.add((min(int(first), int(second)), max(int(first), int(second))))
    return result


def _stable_edges(faces: np.ndarray, labels: list[int], vertices: set[int] | None = None) -> set[tuple[int, int]]:
    return {
        (min(labels[first], labels[second]), max(labels[first], labels[second]))
        for first, second in _edges(faces, vertices)
    }


def _target(vertices: np.ndarray, faces: np.ndarray) -> float:
    lengths = np.concatenate(
        [
            np.linalg.norm(vertices[faces[:, index]] - vertices[faces[:, (index + 1) % 3]], axis=1)
            for index in range(3)
        ]
    )
    return float(np.median(lengths[lengths > 0.0]))


def _digest(tx: OperatorTransaction) -> str:
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(tx.state.vertices).tobytes())
    digest.update(np.ascontiguousarray(tx.state.faces).tobytes())
    return digest.hexdigest()


def _summary(tx: OperatorTransaction, reports: tuple[object, ...] | list[object], elapsed: float) -> dict[str, object]:
    return {
        "elapsed_s": elapsed,
        "reports": len(reports),
        "accepted": sum(int(report.accepted) for report in reports),
        "vertices": len(tx.state.vertices),
        "faces": len(tx.state.faces),
        "manifold": bool(topology.is_manifold(tx.state.faces)),
        "watertight": bool(topology.is_watertight(tx.state.faces)),
        "digest": _digest(tx),
    }


def _heap_push(
    heap: list[tuple[float, tuple[int, int], int]],
    generation: dict[tuple[int, int], int],
    queued: set[tuple[int, int]],
    active: set[tuple[int, int]],
    edge: tuple[int, int],
    length: float,
) -> None:
    edge = (min(edge), max(edge))
    if edge in queued or edge not in active:
        return
    queued.add(edge)
    generation[edge] = generation.get(edge, 0) + 1
    heapq.heappush(heap, (float(length), edge, generation[edge]))


def _invalidate_local(
    heap: list[tuple[float, tuple[int, int], int]],
    generation: dict[tuple[int, int], int],
    queued: set[tuple[int, int]],
    active: set[tuple[int, int]],
    edges: set[tuple[int, int]],
) -> None:
    for edge in edges:
        active.discard(edge)
        queued.discard(edge)
        generation[edge] = generation.get(edge, 0) + 1


def _collapse_worklist(
    tx: OperatorTransaction,
    target: float,
    reports: list[object],
) -> int:
    labels = list(range(len(tx.state.vertices)))
    current_of = {label: index for index, label in enumerate(labels)}
    active = _stable_edges(tx.state.faces, labels)
    queued: set[tuple[int, int]] = set()
    generation: dict[tuple[int, int], int] = {}
    heap: list[tuple[float, tuple[int, int], int]] = []
    for edge in sorted(active):
        _heap_push(heap, generation, queued, active, edge, tx._edge_length(edge))

    scans = 0
    while heap:
        _, stable_edge, token = heapq.heappop(heap)
        queued.discard(stable_edge)
        if generation.get(stable_edge) != token or stable_edge not in active:
            continue
        first = current_of.get(stable_edge[0])
        second = current_of.get(stable_edge[1])
        if first is None or second is None:
            active.discard(stable_edge)
            continue
        edge = (min(first, second), max(first, second))
        scans += 1
        if not tx.should_collapse_edge(edge, target):
            active.discard(stable_edge)
            continue

        before = tx.state.copy()
        old_a, old_b = edge
        old_local = _stable_edges(
            before.faces,
            labels,
            {old_a, old_b},
        )
        report = tx.collapse_edge(edge, target)
        reports.append(report)
        active.discard(stable_edge)
        generation[stable_edge] = generation.get(stable_edge, 0) + 1
        if not report.accepted:
            continue

        labels.pop(old_b)
        current_of = {label: index for index, label in enumerate(labels)}
        new_local = _stable_edges(tx.state.faces, labels, {old_a})
        _invalidate_local(heap, generation, queued, active, old_local)
        for local_edge in sorted(new_local):
            first_new = current_of[local_edge[0]]
            second_new = current_of[local_edge[1]]
            _heap_push(
                heap,
                generation,
                queued,
                active,
                local_edge,
                float(np.linalg.norm(tx.state.vertices[first_new] - tx.state.vertices[second_new])),
            )
    return scans


def _flip_worklist(tx: OperatorTransaction, reports: list[object]) -> int:
    labels = list(range(len(tx.state.vertices)))
    active = _stable_edges(tx.state.faces, labels)
    queued: set[tuple[int, int]] = set()
    generation: dict[tuple[int, int], int] = {}
    heap: list[tuple[float, tuple[int, int], int]] = []
    for edge in sorted(active):
        _heap_push(heap, generation, queued, active, edge, tx._edge_length(edge))

    scans = 0
    while heap:
        _, stable_edge, token = heapq.heappop(heap)
        queued.discard(stable_edge)
        if generation.get(stable_edge) != token or stable_edge not in active:
            continue
        edge = stable_edge
        scans += 1
        first, second = edge
        if first >= len(tx.state.vertices) or second >= len(tx.state.vertices):
            active.discard(stable_edge)
            continue
        if not tx.should_flip_edge(edge):
            active.discard(stable_edge)
            continue

        before = tx.state.copy()
        incident_vertices = {first, second}
        for face in before.faces.tolist():
            if first in face and second in face:
                incident_vertices.update(int(vertex) for vertex in face)
        old_local = _edges(before.faces, incident_vertices)
        report = tx.flip_edge(edge)
        reports.append(report)
        active.discard(stable_edge)
        generation[stable_edge] = generation.get(stable_edge, 0) + 1
        if not report.accepted:
            continue
        new_local = _edges(tx.state.faces, incident_vertices)
        _invalidate_local(heap, generation, queued, active, old_local)
        for local_edge in sorted(new_local):
            _heap_push(
                heap,
                generation,
                queued,
                active,
                local_edge,
                tx._edge_length(local_edge),
            )
    return scans


def run_worklist(vertices: np.ndarray, faces: np.ndarray, target: float) -> tuple[OperatorTransaction, list[object], dict[str, int]]:
    tx = OperatorTransaction(vertices, faces, target_edge_length=target)
    reports: list[object] = []
    for edge in tx._unique_edges():
        if tx.should_split_edge(edge, target):
            reports.append(tx.split_edge(edge, target))
    collapse_scans = _collapse_worklist(tx, target, reports)
    flip_scans = _flip_worklist(tx, reports)
    return tx, reports, {"collapse_scans": collapse_scans, "flip_scans": flip_scans}


def run_fixture(relative: str) -> dict[str, object]:
    mesh = read_stl(str(ROOT / relative))
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    target = _target(vertices, faces)

    baseline_tx = OperatorTransaction(vertices, faces, target_edge_length=target)
    baseline_start = time.perf_counter()
    baseline_reports = baseline_tx.run_one_round(target_edge_length=target, smooth=False)
    baseline = _summary(baseline_tx, baseline_reports, time.perf_counter() - baseline_start)

    work_start = time.perf_counter()
    work_tx, work_reports, scans = run_worklist(vertices, faces, target)
    work = _summary(work_tx, work_reports, time.perf_counter() - work_start)
    return {
        "fixture": relative,
        "baseline": baseline,
        "worklist": {**work, **scans},
        "digest_equal": baseline["digest"] == work["digest"],
        "topology_equal": (baseline["manifold"], baseline["watertight"])
        == (work["manifold"], work["watertight"]),
    }


def main() -> int:
    selected = tuple(sys.argv[1:]) or FIXTURES
    for fixture in selected:
        try:
            row = run_fixture(fixture)
        except Exception as exc:  # noqa: BLE001 — bounded diagnostic boundary
            row = {"fixture": fixture, "status": "exception", "exception": f"{type(exc).__name__}: {exc}"}
        else:
            row["status"] = "measured"
        print(json.dumps(row, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
