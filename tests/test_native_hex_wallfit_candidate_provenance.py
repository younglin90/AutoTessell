"""Fail-closed source provenance for report-only native_hex wall-fit candidates."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from numpy.typing import NDArray

from core.analyzer.readers import read_stl
from core.generator.native_hex.mesher import _wall_fit_snap
from core.generator.native_hex.source_feature_sidecar_l1 import (
    AuthoritativeSourceFeatureManifest,
    audit_authoritative_source_feature_sidecar_l1,
    ordered_triangle_coordinate_sha256,
)
from core.generator.native_hex.wallfit_quality import source_candidate_provenance_context

_ROOT = Path(__file__).resolve().parents[1]
_CUBE = _ROOT / "tests" / "benchmarks" / "cube.stl"
_CELL_FACES = [
    [
        [0, 1, 2, 3],
        [4, 5, 6, 7],
        [0, 4, 5, 1],
        [1, 5, 6, 2],
        [2, 6, 7, 3],
        [3, 7, 4, 0],
    ]
]


def _entities(vertices: np.ndarray, faces: np.ndarray) -> tuple[tuple[str, str], ...]:
    labels: list[tuple[str, str]] = []
    for face in faces:
        center = np.mean(vertices[face], axis=0)
        axis = int(np.argmax(np.abs(center)))
        labels.append(("cube", f"axis_{axis}_{'high' if center[axis] > 0.0 else 'low'}"))
    return tuple(labels)


def _manifest(
    path: Path, vertices: np.ndarray, faces: np.ndarray
) -> AuthoritativeSourceFeatureManifest:
    return AuthoritativeSourceFeatureManifest(
        sha256(path.read_bytes()).hexdigest(),
        ordered_triangle_coordinate_sha256(vertices, faces),
        _entities(vertices, faces),
    )


def _top_inner_hex() -> NDArray[np.float64]:
    """One valid small hex whose nearest source is top cube-face interior."""

    return np.asarray(
        [
            [-0.11, -0.08, 0.10],
            [0.06, -0.08, 0.10],
            [0.06, 0.13, 0.10],
            [-0.11, 0.13, 0.10],
            [-0.11, -0.08, 0.20],
            [0.06, -0.08, 0.20],
            [0.06, 0.13, 0.20],
            [-0.11, 0.13, 0.20],
        ],
        dtype=np.float64,
    )


def test_wallfit_records_unique_authoritative_source_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mesh = read_stl(_CUBE)
    manifest = _manifest(_CUBE, mesh.vertices, mesh.faces)
    monkeypatch.delenv("AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG", raising=False)
    baseline, baseline_stats = _wall_fit_snap(
        _top_inner_hex(),
        _CELL_FACES,
        mesh.vertices,
        mesh.faces,
        target_edge=1.0,
        tol=0.01,
        ratio=1.0,
        iters=1,
    )
    monkeypatch.setenv("AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG", "1")

    points, stats = _wall_fit_snap(
        _top_inner_hex(),
        _CELL_FACES,
        mesh.vertices,
        mesh.faces,
        target_edge=1.0,
        tol=0.01,
        ratio=1.0,
        iters=1,
        source_path=_CUBE,
        source_feature_manifest=manifest,
    )

    report = cast(dict[str, Any], stats["candidate_quality"])
    assert np.array_equal(baseline, points)
    assert baseline_stats["n_snapped"] == stats["n_snapped"]
    assert report["n_candidates"] > 0
    assert report["n_source_provenance_authoritative"] > 0
    assert report["n_source_provenance_unavailable"] == 0
    assert any(
        record["source_provenance_status"] == "AUTHORITATIVE"
        and record["source_entity"] == ("cube", "axis_2_high")
        for record in report["pareto_frontier"]
    )


def test_source_provenance_fails_closed_for_hash_mismatch_and_face_reordering() -> None:
    mesh = read_stl(_CUBE)
    manifest = _manifest(_CUBE, mesh.vertices, mesh.faces)
    point = np.mean(mesh.vertices[mesh.faces[0]], axis=0)
    mismatch = AuthoritativeSourceFeatureManifest(
        "0" * 64,
        manifest.ordered_triangle_coordinate_sha256,
        manifest.face_entities,
    )

    wrong_hash = source_candidate_provenance_context(
        mesh.vertices,
        mesh.faces,
        source_path=_CUBE,
        manifest=mismatch,
    ).classify_projection_target(point)
    reordered = source_candidate_provenance_context(
        mesh.vertices,
        mesh.faces[::-1].copy(),
        source_path=_CUBE,
        manifest=manifest,
    ).classify_projection_target(point)

    assert wrong_hash.status == "UNAVAILABLE"
    assert wrong_hash.source_entity is None
    assert wrong_hash.reason == "reject_manifest_source_identity_mismatch"
    assert reordered.status == "UNAVAILABLE"
    assert reordered.source_entity is None
    assert reordered.reason == "reject_manifest_source_identity_mismatch"


def test_source_entity_boundary_tie_is_ambiguous_without_default_label() -> None:
    mesh = read_stl(_CUBE)
    manifest = _manifest(_CUBE, mesh.vertices, mesh.faces)
    sidecar = audit_authoritative_source_feature_sidecar_l1(
        mesh.vertices,
        mesh.faces,
        source_path=_CUBE,
        manifest=manifest,
    )
    assert sidecar.provenance is not None
    boundary = sidecar.provenance.entity_boundaries[0]
    point = np.mean(mesh.vertices[np.asarray(boundary.edge, dtype=np.int64)], axis=0)
    context = source_candidate_provenance_context(
        mesh.vertices,
        mesh.faces,
        source_path=_CUBE,
        manifest=manifest,
    )

    result = context.classify_projection_target(point)

    assert result.status == "AMBIGUOUS"
    assert result.source_entity is None
    assert result.reason == "authoritative_source_entity_boundary_tie"
    assert set(boundary.incident_faces).issubset(result.source_triangle_indices)


def test_source_provenance_classification_is_deterministic() -> None:
    mesh = read_stl(_CUBE)
    manifest = _manifest(_CUBE, mesh.vertices, mesh.faces)
    point = np.mean(mesh.vertices[mesh.faces[0]], axis=0)
    context = source_candidate_provenance_context(
        mesh.vertices,
        mesh.faces,
        source_path=_CUBE,
        manifest=manifest,
    )

    assert context.classify_projection_target(point) == context.classify_projection_target(point)


def test_stock_input_report_only_diagnostic_is_byte_identical_and_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mesh = read_stl(_CUBE)
    monkeypatch.delenv("AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG", raising=False)
    baseline, baseline_stats = _wall_fit_snap(
        _top_inner_hex(),
        _CELL_FACES,
        mesh.vertices,
        mesh.faces,
        target_edge=1.0,
        tol=0.01,
        ratio=1.0,
        iters=1,
    )
    monkeypatch.setenv("AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG", "1")
    diagnostic, diagnostic_stats = _wall_fit_snap(
        _top_inner_hex(),
        _CELL_FACES,
        mesh.vertices,
        mesh.faces,
        target_edge=1.0,
        tol=0.01,
        ratio=1.0,
        iters=1,
    )

    report = cast(dict[str, Any], diagnostic_stats["candidate_quality"])
    assert np.array_equal(baseline, diagnostic)
    assert baseline_stats["n_snapped"] == diagnostic_stats["n_snapped"]
    assert report["n_candidates"] > 0
    assert report["n_source_provenance_authoritative"] == 0
    assert report["n_source_provenance_ambiguous"] == 0
    assert report["n_source_provenance_unavailable"] == report["n_candidates"]
