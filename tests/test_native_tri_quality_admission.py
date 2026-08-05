
from __future__ import annotations

import numpy as np

from core.preprocessor.native_tri.operator_loop import OperatorKind, OperatorTransaction
from core.utils.native_extensions import load_native_tri_quality_repair


def _quality_module():
    module = load_native_tri_quality_repair()
    if module is None or not hasattr(module, "admit_surface_edit"):
        raise AssertionError("native_tri_quality_repair admission API is unavailable")
    return module


def test_cpp_quality_admission_accepts_strict_surface_improvement() -> None:
    module = _quality_module()
    source = np.asarray(
        [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]],
        dtype=np.float64,
    )
    before = np.asarray(
        [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.01, 0.1, 0.0]],
        dtype=np.float64,
    )
    after = before.copy()
    after[2] = [0.0, 5.0, 0.0]
    faces = np.asarray([[0, 1, 2]], dtype=np.int64)

    receipt = dict(module.admit_surface_edit(before, faces, after, faces, source, faces))

    assert receipt["accepted"] is True
    assert receipt["reason"] == "strict_quality_improvement"
    assert receipt["hard_valid"] is True
    assert receipt["after"]["self_intersecting"] == 0
    assert receipt["after"]["min_angle"] > receipt["before"]["min_angle"]
    assert receipt["after"]["min_mean_ratio"] > receipt["before"]["min_mean_ratio"]
    assert receipt["after"]["max_edge_aspect"] < receipt["before"]["max_edge_aspect"]


def test_cpp_quality_admission_rejects_quality_regression() -> None:
    module = _quality_module()
    source = np.asarray(
        [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]],
        dtype=np.float64,
    )
    before = np.asarray(
        [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.01, 0.1, 0.0]],
        dtype=np.float64,
    )
    after = before.copy()
    after[2] = [0.0, 0.1, 0.0]
    faces = np.asarray([[0, 1, 2]], dtype=np.int64)

    receipt = dict(module.admit_surface_edit(before, faces, after, faces, source, faces))

    assert receipt["accepted"] is False
    assert receipt["reason"] in {"quality_regression", "no_strict_quality_improvement"}
    assert receipt["hard_valid"] is True
    assert receipt["non_regression"] is False


def test_operator_transaction_quality_rejection_rolls_back_bitwise() -> None:
    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    faces = np.asarray(
        [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]],
        dtype=np.int64,
    )
    before = vertices.copy()
    transaction = OperatorTransaction(
        vertices,
        faces,
        quality_admission=lambda *_: (False, "quality_admission_refused"),
    )

    report = transaction.attempt(OperatorKind.SMOOTH, (vertices.copy(), faces.copy()))

    assert report.accepted is False
    assert report.reason == "quality_admission_refused"
    assert np.array_equal(transaction.state.vertices, before)
    assert np.array_equal(transaction.state.faces, faces)
