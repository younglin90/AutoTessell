"""L0 tests for the C++23 frozen-front/collision/geodesic witness."""

from __future__ import annotations

from copy import deepcopy

import numpy as np

from core.evaluator.native_surface_frozen_front_diagnostic import (
    evaluate_frozen_front_diagnostic,
)


def _case() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    edges = np.array([[7, 0, 1, 0]], dtype=np.int64)
    layer_points = np.array([[[[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]]])
    normals = np.array([[0.0, 0.0, 1.0]])
    provenance = [{
        "source_wall_edge": 7,
        "source_face": 0,
        "layer": 1,
        "patch": "wall",
        "feature": "flat",
        "physical_group": "fluid",
        "component": "main",
        "provenance": "source-direct",
        "generated_vertices": [10, 11],
    }]
    collision = [{"visible": True, "collision": False, "method": "readback"}]
    geodesic = [{"status": "measured", "distance": 1.0, "path_digest": "path-1", "method": "provided_surface_path"}]
    return points, edges, layer_points, normals, provenance, collision, geodesic


def test_bl0_is_exact_identity_and_never_published() -> None:
    result = evaluate_frozen_front_diagnostic([], [], [], [], [], 0)
    assert result["status"] == "disabled_identity"
    assert result["actual_layers"] == 0
    assert result["publication_eligible"] is False
    assert result["runtime_route"] == "default_off"


def test_positive_layer_witness_passes_only_as_report_evidence() -> None:
    args = _case()
    before = deepcopy(args[4])
    result = evaluate_frozen_front_diagnostic(*args[:5], 1, collision_witness=args[5], geodesic_witness=args[6])
    assert result["accepted"] is True
    assert result["status"] == "quality_evidence_ready"
    assert result["actual_layers"] == 1
    assert result["frozen_front"]["status"] == "frozen"
    assert result["collision_visibility"]["status"] == "measured_clear"
    assert result["geodesic"]["status"] == "measured"
    assert result["topology"]["invalid"] == 0
    assert result["topology"]["inverted"] == 0
    assert args[4] == before
    assert result["publication_eligible"] is False
    assert result["runtime_route"] == "default_off"


def test_missing_geodesic_and_changed_front_fail_closed() -> None:
    args = list(_case())
    changed = deepcopy(args[4])
    changed[0]["patch"] = "changed"
    args[4] = changed
    result = evaluate_frozen_front_diagnostic(*args[:5], 1, collision_witness=args[5], geodesic_witness=None)
    assert result["accepted"] is False
    assert result["reason"] == "geodesic_witness_unmeasured"
    assert result["geodesic"]["status"] == "unmeasured_or_incomplete"


def test_collision_witness_is_not_inferred() -> None:
    args = _case()
    result = evaluate_frozen_front_diagnostic(*args[:5], 1, collision_witness=None, geodesic_witness=args[6])
    assert result["accepted"] is False
    assert result["reason"] == "collision_or_visibility_witness_incomplete"
    assert result["collision_visibility"]["status"] == "incomplete_or_collision"

def test_changed_frozen_front_is_refused_before_quality_claim() -> None:
    points, edges, layer_points, normals, provenance, collision, geodesic = _case()
    two_layers = np.concatenate([layer_points, layer_points + np.array([0.0, 1.0, 0.0])], axis=0)
    second = deepcopy(provenance[0])
    second["layer"] = 2
    second["feature"] = "changed"
    result = evaluate_frozen_front_diagnostic(
        points,
        edges,
        two_layers,
        normals,
        [provenance[0], second],
        2,
        collision_witness=collision * 2,
        geodesic_witness=geodesic * 2,
    )
    assert result["accepted"] is False
    assert result["reason"] == "frozen_front_changed_or_incomplete"
    assert result["frozen_front"]["changed"] == 1

