"""L0/L1 tests for the default-off Native Tri C++ quality repair card."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from core.preprocessor.native_tri.operator_loop import OperatorTransaction
from core.preprocessor.native_tri.release_route import _run_naca_quality_repair
from core.utils.native_extensions import load_native_tri_quality_repair


def _repair_module():
    module = load_native_tri_quality_repair()
    if module is None:
        pytest.skip("native_tri_quality_repair extension is not built")
    return module


def _sliver_fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    source_vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    output_vertices = source_vertices.copy()
    output_vertices[2] = [0.01, 0.01, 0.0]
    return output_vertices, faces, source_vertices, faces.copy()


def _plain(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _run(module, output_vertices, faces, source_vertices, source_faces, locked):
    return module.repair_surface_quality(
        np.ascontiguousarray(output_vertices, dtype=np.float64),
        np.ascontiguousarray(faces, dtype=np.int64),
        np.ascontiguousarray(source_vertices, dtype=np.float64),
        np.ascontiguousarray(source_faces, dtype=np.int64),
        np.ascontiguousarray(locked, dtype=np.uint8),
        max_iterations=32,
        minimum_angle=10.0,
        maximum_angle=150.0,
        minimum_mean_ratio=0.05,
    )


def test_cpp_repair_improves_sliver_without_mutating_inputs_or_faces():
    module = _repair_module()
    output_vertices, faces, source_vertices, source_faces = _sliver_fixture()
    before_vertices = output_vertices.copy()
    before_faces = faces.copy()

    result = _run(
        module,
        output_vertices,
        faces,
        source_vertices,
        source_faces,
        np.zeros(len(output_vertices), dtype=np.uint8),
    )

    assert bool(result["accepted"]) is True
    assert result["reason"] == "quality_repair_committed"
    assert bool(result["faces_unchanged"]) is True
    assert result["accepted_moves"] >= 1
    assert result["after"]["invalid"] == 0
    assert result["after"]["self_intersecting"] == 0
    assert result["after"]["min_angle"] >= 10.0
    assert result["after"]["max_angle"] <= 150.0
    assert result["after"]["min_mean_ratio"] >= 0.05
    np.testing.assert_array_equal(output_vertices, before_vertices)
    np.testing.assert_array_equal(faces, before_faces)


def test_cpp_repair_receipt_and_candidate_are_repeatable():
    module = _repair_module()
    output_vertices, faces, source_vertices, source_faces = _sliver_fixture()
    locked = np.zeros(len(output_vertices), dtype=np.uint8)

    first = _plain(_run(module, output_vertices, faces, source_vertices, source_faces, locked))
    second = _plain(_run(module, output_vertices, faces, source_vertices, source_faces, locked))

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_cpp_repair_locks_feature_vertices_and_refuses_without_mutation():
    module = _repair_module()
    output_vertices, faces, source_vertices, source_faces = _sliver_fixture()
    result = _run(
        module,
        output_vertices,
        faces,
        source_vertices,
        source_faces,
        np.ones(len(output_vertices), dtype=np.uint8),
    )

    assert bool(result["accepted"]) is False
    assert result["changed_vertex_count"] == 0
    assert result["reason"] == "no_strict_local_improvement"
    assert all(receipt["reason"] == "locked_feature_vertex" for receipt in result["receipts"])
    np.testing.assert_allclose(np.asarray(result["candidate_vertices"]), output_vertices)


@pytest.mark.parametrize(
    "bad_faces",
    [
        np.array([[0, 1, 2], [0, 1, 2]], dtype=np.int64),
        np.array([[0, 1, 2], [0, 1, 3], [0, 1, 2], [0, 1, 3]], dtype=np.int64),
    ],
)
def test_cpp_repair_refuses_duplicate_or_nonmanifold_input(bad_faces):
    module = _repair_module()
    output_vertices, _, source_vertices, source_faces = _sliver_fixture()
    result = _run(
        module,
        output_vertices,
        bad_faces,
        source_vertices,
        source_faces,
        np.zeros(len(output_vertices), dtype=np.uint8),
    )

    assert bool(result["accepted"]) is False
    assert result["reason"] == "repair_input_topology_invalid"
    assert "candidate_vertices" not in result


def test_python_adapter_is_default_off_and_leaves_transaction_bit_identical(monkeypatch):
    output_vertices, faces, source_vertices, source_faces = _sliver_fixture()
    transaction = OperatorTransaction(output_vertices, faces, target_edge_length=1.0)
    reports = []
    monkeypatch.delenv("AUTO_TESSELL_NATIVE_TRI_NACA_QUALITY_REPAIR", raising=False)

    result = _run_naca_quality_repair(
        transaction,
        source_vertices,
        source_faces,
        Path("/tmp/naca0012.stl"),
        reports,
    )

    assert result is None
    assert reports == []
    np.testing.assert_array_equal(transaction.state.vertices, output_vertices)
    np.testing.assert_array_equal(transaction.state.faces, faces)


def test_python_adapter_rechecks_cpp_candidate_through_transaction(monkeypatch):
    module = _repair_module()
    assert module is not None
    output_vertices, faces, source_vertices, source_faces = _sliver_fixture()
    transaction = OperatorTransaction(output_vertices, faces, target_edge_length=1.0)
    reports = []
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_NACA_QUALITY_REPAIR", "1")
    monkeypatch.setenv(
        "AUTOTESSELL_EXT_BUILD_DIR",
        str(Path(__file__).resolve().parents[1] / "auto_tessell_core" / "build"),
    )

    result = _run_naca_quality_repair(
        transaction,
        source_vertices,
        source_faces,
        Path("/tmp/naca0012.stl"),
        reports,
    )

    assert result is not None
    assert result["accepted"] is True
    assert result["transaction_guard"]["accepted"] is True
    assert reports[-1].accepted is True
    assert not np.array_equal(transaction.state.vertices, output_vertices)
    np.testing.assert_array_equal(transaction.state.faces, faces)
