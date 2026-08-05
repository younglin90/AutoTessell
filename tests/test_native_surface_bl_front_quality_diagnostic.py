"""Per-edge quality diagnostics for the actual hemisphere front."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger
from tests.test_native_surface_bl_front_actual_stl import _candidate, _surface


def test_actual_hemisphere_worst_edge_metrics_are_explicit_and_repeatable() -> None:
    path = Path("tests/benchmarks/hemisphere_open.stl")
    ledger, first = _candidate(path, 3)
    _, second = _candidate(path, 3)
    assert first == second
    assert first["accepted"] is True
    points, _, _, vertex_ids = _surface(path)
    selected = [edge for edge in ledger["edges"] if edge["incidence"] == 1]
    edge_by_short_id = {int(edge["edge_id"][:15], 16): edge for edge in selected}
    generated = {item["id"]: np.asarray([item["x"], item["y"], item["z"]], dtype=float) for item in first["generated_vertices"]}
    rows = []
    for item in first["provenance"]:
        edge = edge_by_short_id[item["source_wall_edge"]]
        source_a = np.asarray(edge["endpoint_a"], dtype=float)
        source_b = np.asarray(edge["endpoint_b"], dtype=float)
        generated_a, generated_b = (generated[int(value)] for value in item["generated_vertices"])
        source_length = float(np.linalg.norm(source_b - source_a))
        generated_length = float(np.linalg.norm(generated_b - generated_a))
        step = float(item["used_step"])
        skewness = abs(generated_length - source_length) / max(generated_length, source_length)
        non_orthogonality = math.degrees(math.acos(np.clip(np.dot(source_b - source_a, generated_b - generated_a) / (source_length * generated_length), -1.0, 1.0)))
        rows.append({"edge_id": item["source_wall_edge"], "layer": item["layer"], "source_length": source_length, "step": step, "skewness": skewness, "non_orthogonality": non_orthogonality, "aspect": max(source_length, step) / min(source_length, step)})
    worst_aspect = max(rows, key=lambda row: row["aspect"])
    worst_skew = max(rows, key=lambda row: row["skewness"])
    worst_non_orthogonality = max(rows, key=lambda row: row["non_orthogonality"])
    print({"worst_aspect": worst_aspect, "worst_skew": worst_skew, "worst_non_orthogonality": worst_non_orthogonality})
    assert worst_aspect["aspect"] >= first["quality"]["metric_aspect_ratio"] * 0.99
    assert worst_skew["skewness"] <= 0.50
    assert worst_non_orthogonality["non_orthogonality"] <= 50.0
