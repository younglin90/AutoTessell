from __future__ import annotations

from core.evaluator.native_surface_bl_front_target_field_transaction import (
    transact_surface_wall_edge_target_field,
)
from core.evaluator.native_surface_bl_front_optimizer import (
    propose_surface_wall_edge_target_field,
)
from tests.test_native_surface_bl_front_planar_cavity import (
    _dodecagon_with_interior_fixture,
    _hexagon_fixture,
    _target,
)
import numpy as np


def test_strict_bl0_remains_exact_identity():
    points, triangles, edges, normals, certificate, provenance = _hexagon_fixture()
    target = propose_surface_wall_edge_target_field(
        points, edges, normals, ["p"] * len(normals), ["feature"] * len(normals),
        ["g"] * len(normals), np.ones(len(edges), dtype=np.float64), 0, 0.6,
        1.0, certificate, provenance,
    )
    result = transact_surface_wall_edge_target_field(
        points, triangles, edges, normals, target, certificate, provenance, 0,
        planar_cavity_replacement=True, strict_quality=True,
    )
    assert result["accepted"] is True, result
    assert result["strict_quality"] is True
    assert result["actual_layers"] == 0
    assert result["generated_faces"] == []
    assert result["source_digest"] == result["output_digest"]


def test_strict_bl1_refuses_admissible_but_non_strict_strip_atomically():
    points, triangles, edges, normals, certificate, provenance = _hexagon_fixture()
    target = _target(points, triangles, edges, normals, certificate, provenance)
    result = transact_surface_wall_edge_target_field(
        points, triangles, edges, normals, target, certificate, provenance, 1,
        planar_cavity_replacement=True, strict_quality=True,
    )
    assert target["accepted"] is True, target
    assert result["accepted"] is False, result
    assert result["reason"] in {
        "planar_cavity_strict_front_no_candidate",
        "planar_cavity_strip_quality_failure",
        "planar_cavity_subdivided_strip_quality_failure",
    }
    assert result["strict_quality"] is True
    assert result["actual_layers"] == 0
    assert result["generated_faces"] == []
    assert result["provenance"] == []
    assert result["candidate_discarded"] is True


def test_admissible_bl3_has_per_face_quality_witness_and_repeats():
    points, triangles, edges, normals, certificate, provenance = (
        _dodecagon_with_interior_fixture()
    )
    target = _target(
        points, triangles, edges, normals, certificate, provenance,
        layers=3, first_height=0.1, clearance_cap=3.0,
    )
    runs = [
        transact_surface_wall_edge_target_field(
            points, triangles, edges, normals, target, certificate, provenance, 3,
            planar_cavity_replacement=True,
        )
        for _ in range(3)
    ]
    assert all(result["accepted"] is True for result in runs), runs
    assert all(result["strict_quality"] is False for result in runs)
    assert all(len(result["quality_witness"]) == 84 for result in runs)
    assert all(
        row["role"] in {"boundary_layer_strip", "child_front_core"}
        and row["accepted"] is True
        and row["skewness"] >= 0.0
        and row["aspect_ratio"] >= 1.0
        and row["non_orthogonality_degrees"] >= 0.0
        for row in runs[0]["quality_witness"]
    )
    assert len({result["output_digest"] for result in runs}) == 1
    assert runs[0]["quality"]["max_skewness"] <= 0.50 + 1.0e-12
