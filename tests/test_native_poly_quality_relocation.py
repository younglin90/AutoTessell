"""Focused Native Poly C++23 post-BL quality-relocation transaction tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from core.evaluator.native_release_authority_gate import _poly_quality_relocation_valid
from core.layers.poly_bl_transition import (
    _apply_native_poly_quality_relocation,
    run_poly_bl_transition,
)
from core.utils.native_extensions import load_native_poly_quality_relocation
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)


ROOT = Path(__file__).resolve().parents[1]
GEAR_CASE = (
    ROOT
    / "docs"
    / "qa"
    / "native_release_campaign_20260803_round093_authority_final"
    / "cases"
    / "native-poly-gear"
    / "run-0"
)


def _kernel_inputs(case: Path):
    poly = case / "constant" / "polyMesh"
    points = np.asarray(parse_foam_points_array(poly / "points"), dtype=np.float64)
    faces = parse_foam_faces(poly / "faces")
    owner = np.asarray(parse_foam_labels_array(poly / "owner"), dtype=np.int64)
    neighbour = np.asarray(parse_foam_labels_array(poly / "neighbour"), dtype=np.int64)
    flat = np.asarray([vertex for face in faces for vertex in face], dtype=np.int64)
    offsets = np.zeros(len(faces) + 1, dtype=np.int64)
    offsets[1:] = np.cumsum([len(face) for face in faces], dtype=np.int64)
    locked = np.asarray(
        sorted({vertex for face in faces[len(neighbour) :] for vertex in face}),
        dtype=np.int64,
    )
    return points, faces, owner, neighbour, flat, offsets, locked


@pytest.mark.skipif(not GEAR_CASE.is_dir(), reason="round evidence artifact is unavailable")
def test_native_poly_quality_kernel_is_deterministic_and_locks_boundary() -> None:
    kernel = load_native_poly_quality_relocation()
    if kernel is None:
        pytest.skip("native_poly_quality_relocation build is unavailable")
    points, faces, owner, neighbour, flat, offsets, locked = _kernel_inputs(GEAR_CASE)
    first = dict(
        kernel.relocate_poly_quality(
            points, flat, offsets, owner, neighbour, locked, 3, 0.001, 0.0
        )
    )
    second = dict(
        kernel.relocate_poly_quality(
            points, flat, offsets, owner, neighbour, locked, 3, 0.001, 0.0
        )
    )
    assert first["accepted"] is True
    assert first["topology_input_valid"] is True
    assert first["boundary_vertices_locked"] is True
    assert np.array_equal(np.asarray(first["points"]), np.asarray(second["points"]))
    candidate = np.asarray(first["points"], dtype=np.float64)
    assert np.array_equal(
        np.ascontiguousarray(points[locked]).view(np.uint64),
        np.ascontiguousarray(candidate[locked]).view(np.uint64),
    )
    assert first["moved_vertex_count"] > 0
    assert first["locked_vertex_count"] == len(locked)
    assert first["metrics_after"]["max_aspect_ratio"] < first["metrics_before"]["max_aspect_ratio"]
    assert first["metrics_after"]["max_non_orthogonality_deg"] < first["metrics_before"]["max_non_orthogonality_deg"]


@pytest.mark.skipif(not GEAR_CASE.is_dir(), reason="round evidence artifact is unavailable")
def test_native_poly_quality_transaction_records_authoritative_improvement_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = tmp_path / "case"
    shutil.copytree(GEAR_CASE, case)
    monkeypatch.setenv("AUTO_TESSELL_POLY_NATIVE_QUALITY_RELOCATE", "1")
    report = _apply_native_poly_quality_relocation(case)
    assert report["accepted"] is True
    assert report["destination_unchanged"] is False
    assert report["quality_tuple_after"] < report["quality_tuple_before"]
    assert report["strict_topology"]["n_duplicate_faces"] == 0
    assert report["strict_topology"]["n_nonmanifold_faces"] == 0
    assert report["strict_topology"]["n_inverted_cells"] == 0
    saved = json.loads(
        (case / "native_poly_quality_relocation.json").read_text(encoding="utf-8")
    )
    assert saved["accepted"] is True
    assert saved["cpp"]["boundary_vertices_locked"] is True

    rollback_case = tmp_path / "rollback"
    shutil.copytree(GEAR_CASE, rollback_case)
    points_path = rollback_case / "constant" / "polyMesh" / "points"
    original = points_path.read_bytes()
    monkeypatch.setenv("AUTO_TESSELL_POLY_NATIVE_QUALITY_ITER", "0")
    refused = _apply_native_poly_quality_relocation(rollback_case)
    assert refused["accepted"] is False
    assert refused["destination_unchanged"] is True
    assert points_path.read_bytes() == original


def test_poly_quality_relocation_threshold_is_fail_closed() -> None:
    report = {
        "accepted": True,
        "strict_topology": {"valid": True},
        "quality_after": {
            "internal_non_orthogonality": {"max": 89.7},
            "release_skew": {"max": 89.4},
            "aspect_ratio": {"max": 1069.9},
        },
    }
    valid, reason = _poly_quality_relocation_valid({"quality_relocation": report})
    assert valid is False
    assert reason == "poly_quality_relocation_internal_non_orthogonality_gate_failed"

    report["quality_after"] = {
        "internal_non_orthogonality": {"max": 64.9},
        "release_skew": {"max": 3.9},
        "aspect_ratio": {"max": 99.9},
    }
    valid, reason = _poly_quality_relocation_valid({"quality_relocation": report})
    assert valid is True
    assert reason == ""


def test_poly_boundary_layer_zero_is_exact_noop_even_when_relocation_is_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_POLY_NATIVE_QUALITY_RELOCATE", "1")
    monkeypatch.setattr(
        "core.layers.poly_bl_transition._native_bl_zero_request_blocker",
        lambda _case: None,
    )

    def should_not_generate(*_args, **_kwargs):
        raise AssertionError("BL=0 must not enter the positive-layer generator")

    monkeypatch.setattr("core.layers.poly_bl_transition.generate_native_bl", should_not_generate)
    result = run_poly_bl_transition(
        tmp_path, num_layers=0, growth_ratio=1.2, first_thickness=1.0e-4
    )
    assert result.success is True
    assert result.n_prism_cells == 0
    assert result.quality_relocation is None
    assert "actual_layers=0" in result.message
