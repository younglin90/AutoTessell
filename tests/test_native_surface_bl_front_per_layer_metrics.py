"""Independent checks for the actual advancing-strip quality metrics."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from core.evaluator.native_surface_bl_front_optimizer import (
    optimize_surface_wall_edge_front,
)
from core.layers.native_tet_surface_edge_ledger import build_stl_edge_ledger
from tests.test_native_surface_bl_front_actual_stl import _surface


_SOURCE = Path("tests/benchmarks/hemisphere_open.stl")


def _call(*, layers: int, strict_quality: bool, authority: bool = True):
    points, _triangles, normals, vertex_ids = _surface(_SOURCE)
    ledger = build_stl_edge_ledger(_SOURCE)
    selected = [edge for edge in ledger["edges"] if edge["incidence"] == 1]
    edges = np.asarray(
        [
            [
                int(edge["edge_id"][:15], 16),
                vertex_ids[tuple(edge["endpoint_a"])],
                vertex_ids[tuple(edge["endpoint_b"])],
                edge["incident_facets"][0],
            ]
            for edge in selected
        ],
        dtype=np.int64,
    )
    certificate = {
        "source_kind": "authoritative-stl-ledger",
        "raw_sha256": "a" * 64,
        "brep_hash": "b" * 64,
        "authority": "source-ledger-v1",
        "provenance": "direct-source-ledger",
    }
    provenance = [
        {
            "source_edge": str(int(row[0])),
            "source_face": str(int(row[3])),
            "wall_edge": f"wall-{int(row[0])}",
            "output_face": f"out-{int(row[0])}",
            "feature": "unclassified_boundary",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "hemisphere",
            "provenance": "direct",
        }
        for row in edges
    ]
    if not authority:
        certificate = {}
        provenance = []
    result = optimize_surface_wall_edge_front(
        points,
        edges,
        normals,
        ["wall"] * len(normals),
        ["unclassified_boundary"] * len(normals),
        ["fluid-wall"] * len(normals),
        layers,
        0.01,
        1.2,
        certificate,
        provenance,
        max_metric_aspect_ratio=float("inf"),
        strict_quality=strict_quality,
    )
    return points, edges, result


def test_bl0_remains_identity_in_shared_front_optimizer() -> None:
    _points, _edges, result = _call(layers=0, strict_quality=True)
    assert result["accepted"] is True
    assert result["status"] == "disabled_identity"
    assert result["actual_layers"] == 0
    assert result["generated_vertices"] == []
    assert result["generated_faces"] == []
    assert result["provenance"] == []
    assert result["source_authority_bound"] is True
    assert result["authority_checked"] is True


def test_bl0_refuses_unsealed_authority() -> None:
    _points, _edges, result = _call(
        layers=0,
        strict_quality=True,
        authority=False,
    )
    assert result["accepted"] is False
    assert result["reason"] == "authority_incomplete"
    assert result["actual_layers"] == 0
    assert result["generated_vertices"] == []
    assert result["generated_faces"] == []


def test_receipt_metrics_match_each_actual_advancing_strip() -> None:
    points, edges, result = _call(layers=3, strict_quality=False)
    assert result["accepted"] is True, result
    generated = {
        (int(row["layer"]), int(row["source_vertex"])): np.asarray(
            [row["x"], row["y"], row["z"]], dtype=float
        )
        for row in result["generated_vertices"]
    }
    edge_by_id = {
        int(row[0]): (int(row[1]), int(row[2]))
        for row in edges.tolist()
    }
    local_rows: list[tuple[float, float, float, float]] = []
    for lineage in result["provenance"]:
        layer = int(lineage["layer"])
        a, b = edge_by_id[int(lineage["source_wall_edge"])]
        previous_a = points[a] if layer == 1 else generated[(layer - 1, a)]
        previous_b = points[b] if layer == 1 else generated[(layer - 1, b)]
        current_a = generated[(layer, a)]
        current_b = generated[(layer, b)]
        previous_edge = previous_b - previous_a
        current_edge = current_b - current_a
        previous_length = float(np.linalg.norm(previous_edge))
        current_length = float(np.linalg.norm(current_edge))
        displacement_a = float(np.linalg.norm(current_a - previous_a))
        displacement_b = float(np.linalg.norm(current_b - previous_b))
        step = 0.5 * (displacement_a + displacement_b)
        edge_skew = abs(current_length - previous_length) / max(
            current_length, previous_length
        )
        height_skew = abs(displacement_a - displacement_b) / max(
            displacement_a, displacement_b
        )
        skew = max(edge_skew, height_skew)
        nonortho = math.degrees(
            math.acos(
                np.clip(
                    float(previous_edge @ current_edge)
                    / (previous_length * current_length),
                    -1.0,
                    1.0,
                )
            )
        )
        aspect = max(previous_length, step) / min(previous_length, step)
        local_rows.append((skew, nonortho, aspect, step))
    quality = result["quality"]
    assert math.isclose(
        quality["max_skewness"],
        max(row[0] for row in local_rows),
        rel_tol=1.0e-12,
    )
    assert math.isclose(
        quality["max_non_orthogonality"],
        max(row[1] for row in local_rows),
        rel_tol=1.0e-12,
    )
    assert math.isclose(
        quality["metric_aspect_ratio"],
        max(row[2] for row in local_rows),
        rel_tol=1.0e-12,
    )
    assert math.isclose(
        quality["min_step"],
        min(row[3] for row in local_rows),
        rel_tol=1.0e-12,
    )


def test_strict_profile_refuses_actual_thin_strip_aspect() -> None:
    _points, _edges, result = _call(layers=3, strict_quality=True)
    assert result["accepted"] is False
    assert result["actual_layers"] == 0
    assert result["candidate_discarded"] is True
    assert result["generated_vertices"] == []
    assert result["generated_faces"] == []
    assert result["provenance"] == []
