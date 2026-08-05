from __future__ import annotations

import numpy as np

import sys
from pathlib import Path

_BUILD = Path(__file__).resolve().parents[1] / "auto_tessell_core" / "build"
if str(_BUILD) not in sys.path:
    sys.path.insert(0, str(_BUILD))

import native_tet_surface_boundary_receipt_consumer as consumer
from core.generator import tier_native_tet
from core.generator.native_tet import TetHarnessResult


def _source() -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    faces = np.asarray(
        [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], dtype=np.int64
    )
    return points, faces


def _receipt(points: np.ndarray, faces: np.ndarray, *, positive: bool = False) -> dict[str, object]:
    return {
        "accepted": True,
        "receipt_sealed": True,
        "quality_policy": {
            "max_non_orthogonality": 50.0,
            "max_skewness": 0.5,
            "max_aspect_ratio": 20.0,
            "policy_sha256": "c" * 64,
        },
        "runtime_route": "default_off",
        "receipt_digest": "tet-receipt-v1",
        "source_sha256": "a" * 64,
        "semantic_ledger_sha256": "b" * 64,
        "canonical_source_vertices": points.tolist(),
        "canonical_source_faces": faces.tolist(),
        "positive_bl_volume_partition_available": positive,
        "interface_triangles": [
            {
                "source_face": str(index),
                "output_face": f"out-{index}",
                "triangle": triangle.tolist(),
                "feature": "smooth",
                "patch": "wall",
                "physical_group": "fluid-wall",
                "component": "tetra",
                "provenance": f"surface#{index}",
            }
            for index, triangle in enumerate(faces)
        ],
    }


def test_cpp_ingress_locks_exact_canonical_source_and_refuses_tamper() -> None:
    points, faces = _source()
    accepted = consumer.validate_surface_boundary_receipt_ingress(
        _receipt(points, faces), points, faces, 0
    )
    assert accepted["accepted"] is True
    assert accepted["reason"] == "authoritative_surface_receipt_ingress_verified"
    assert accepted["runtime_route"] == "native_tet_production_receipt"
    tampered = points.copy()
    tampered[0, 0] = 1.0e-9
    refused = consumer.validate_surface_boundary_receipt_ingress(
        _receipt(points, faces), tampered, faces, 0
    )
    assert refused["accepted"] is False
    assert refused["reason"] == "surface_receipt_canonical_geometry_mismatch"


def test_positive_bl_without_closed_volume_partition_refuses() -> None:
    points, faces = _source()
    refused = consumer.validate_surface_boundary_receipt_ingress(
        _receipt(points, faces), points, faces, 1
    )
    assert refused["accepted"] is False
    assert refused["reason"] == "positive_bl_volume_partition_unavailable"


def test_tet_runner_consumes_receipt_on_actual_route(monkeypatch, tmp_path) -> None:
    points, faces = _source()

    def fake_harness(*args, **kwargs):
        return TetHarnessResult(
            success=True,
            elapsed=0.01,
            iterations=1,
            n_cells=1,
            n_points=4,
            message="receipt route witness",
            tet_points=points,
            tets=np.asarray([[0, 1, 2, 3]], dtype=np.int64),
        )

    monkeypatch.setattr(tier_native_tet, "run_native_tet_harness", fake_harness)
    result = tier_native_tet._runner(
        points,
        faces,
        tmp_path,
        input_config={"surface_receipt": _receipt(points, faces)},
    )
    assert result.success is False
    assert result.route == "native_tet_production_receipt"
    assert result.contract == "receipt_locked_ingress"
    assert result.contract_details["receipt_ingress"]["accepted"] is True
    assert result.contract_details["publication_eligible"] is False


def test_receipt_route_does_not_fallback_after_harness_failure(monkeypatch, tmp_path) -> None:
    points, faces = _source()

    def fake_harness(*args, **kwargs):
        return TetHarnessResult(
            success=False,
            elapsed=0.01,
            iterations=1,
            n_cells=0,
            n_points=0,
            message="harness failed",
        )

    def forbidden_fallback(*args, **kwargs):
        raise AssertionError("receipt route must not use legacy fallback")

    monkeypatch.setattr(tier_native_tet, "run_native_tet_harness", fake_harness)
    monkeypatch.setattr(tier_native_tet, "generate_native_tet", forbidden_fallback)
    result = tier_native_tet._runner(
        points,
        faces,
        tmp_path,
        input_config={"surface_receipt": _receipt(points, faces)},
    )
    assert result.success is False
    assert result.contract_details["receipt_ingress"]["accepted"] is True
