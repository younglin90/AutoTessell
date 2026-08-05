"""Quality-first BL=0/1/3 matrix with per-layer and digest evidence."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger
from tests.test_native_surface_bl_front_actual_stl import _candidate, _surface
from tests.test_native_surface_bl_front_stack_transaction import _plan


def _digest(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=list).encode()
    return hashlib.sha256(payload).hexdigest()


def _layer_rows(points, edge_rows, result):
    vertices = {int(item["id"]): np.asarray([item["x"], item["y"], item["z"]], dtype=float) for item in result["generated_vertices"]}
    edge_by_id = {int(row[0]): (int(row[1]), int(row[2])) for row in edge_rows}
    rows = []
    for item in result["provenance"]:
        source_a, source_b = edge_by_id[int(item["source_wall_edge"])]
        source = np.asarray(points[source_b], dtype=float) - np.asarray(points[source_a], dtype=float)
        generated_a, generated_b = (vertices[int(value)] for value in item["generated_vertices"])
        generated = generated_b - generated_a
        source_length = float(np.linalg.norm(source))
        generated_length = float(np.linalg.norm(generated))
        step = float(item["used_step"])
        rows.append(
            {
                "layer": int(item["layer"]),
                "edge": int(item["source_wall_edge"]),
                "step": step,
                "skew": abs(generated_length - source_length) / max(generated_length, source_length),
                "non_ortho": math.degrees(math.acos(np.clip(np.dot(source, generated) / (source_length * generated_length), -1.0, 1.0))),
                "aspect": max(source_length, step) / min(source_length, step),
            }
        )
    return rows


def _fixture_cases():
    feature = dict(
        points=[(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        edges=[[201, 0, 1, 0], [202, 0, 2, 1]],
        normals=[(0, 0, 1), (1, 0, 0)],
        patches=["wall_a", "wall_b"],
        features=["feature_a", "feature_b"],
        groups=["group_a", "group_b"],
    )
    narrow = dict(
        points=[(0, 0, 0), (1, 0, 0), (0, 0.2, 0), (1, 0.2, 0)],
        edges=[[101, 0, 1, 0], [102, 2, 3, 0]],
        normals=[(0, 0, 1)],
        patches=["wall"],
        features=["smooth"],
        groups=["fluid_wall"],
    )
    return [("feature", feature), ("narrow", narrow)]


def test_quality_matrix_actual_and_synthetic_cases() -> None:
    matrix = []
    actual_path = Path("tests/benchmarks/hemisphere_open.stl")
    ledger = build_stl_edge_ledger(actual_path)
    points, _, _, vertex_ids = _surface(actual_path)
    actual_edges = np.asarray(
        [[int(edge["edge_id"][:15], 16), vertex_ids[tuple(edge["endpoint_a"])], vertex_ids[tuple(edge["endpoint_b"])], edge["incident_facets"][0]] for edge in ledger["edges"] if edge["incidence"] == 1],
        dtype=np.int64,
    ).reshape((-1, 4))
    actual_cases = [("hemisphere", points, actual_edges)]

    for name, case in _fixture_cases():
        actual_cases.append((name, np.asarray(case["points"], dtype=float), np.asarray(case["edges"], dtype=np.int64)))

    for name, points_value, edge_values in actual_cases:
        for layers in (0, 1, 3):
            if name == "hemisphere":
                _, first = _candidate(actual_path, layers)
                _, second = _candidate(actual_path, layers)
            else:
                case = dict(next(case for case_name, case in _fixture_cases() if case_name == name))
                first = _plan(**case, layers=layers, first_height=0.01, growth_ratio=1.2)
                second = _plan(**case, layers=layers, first_height=0.01, growth_ratio=1.2)
            assert first == second
            source_digest = _digest(edge_values.tolist())
            output_digest = _digest({"vertices": first["generated_vertices"], "faces": first["generated_faces"], "provenance": first["provenance"]})
            row = {"case": name, "layers": layers, "source_digest": source_digest, "output_digest": output_digest, "accepted": first["accepted"]}
            if layers == 0:
                assert first["accepted"] is True and first["status"] == "disabled_identity"
                assert first["generated_vertices"] == [] and first["provenance"] == []
                matrix.append(row)
                continue
            assert first["accepted"] is True
            rows = _layer_rows(points_value, edge_values, first)
            assert len({item["layer"] for item in rows}) == layers
            assert max(item["skew"] for item in rows) <= 0.50
            assert max(item["non_ortho"] for item in rows) <= 50.0
            assert max(item["aspect"] for item in rows) <= first["quality"]["metric_aspect_ratio"] * (1.0 + 1.0e-12)
            for layer in range(1, layers):
                lower = {item["edge"]: item["step"] for item in rows if item["layer"] == layer}
                upper = {item["edge"]: item["step"] for item in rows if item["layer"] == layer + 1}
                for edge in lower:
                    assert math.isclose(upper[edge] / lower[edge], 1.2, rel_tol=1.0e-12)
            row.update(
                {
                    "selected_scale": first["quality"]["selected_scale"],
                    "max_skew": max(item["skew"] for item in rows),
                    "max_non_ortho": max(item["non_ortho"] for item in rows),
                    "max_aspect": max(item["aspect"] for item in rows),
                    "min_step": min(item["step"] for item in rows),
                    "lineage_count": len(first["provenance"]),
                }
            )
            matrix.append(row)
    print(json.dumps(matrix, sort_keys=True))
    assert len(matrix) == 9
    assert len({row["output_digest"] for row in matrix if row["layers"] > 0}) == 6
