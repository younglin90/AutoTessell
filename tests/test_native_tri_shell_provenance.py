"""TRI-SHELL-PROVENANCE1 report-only linear-shell projection tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri import (
    BijectiveShell,
    OperatorTransaction,
    ShellCoordinate,
    ShellProjectionStatus,
    SourceFacePayload,
    build_linear_bijective_shell,
)


def _single_prism() -> tuple[np.ndarray, np.ndarray, BijectiveShell]:
    vertices = np.asarray(
        ((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        dtype=np.float64,
    )
    faces = np.asarray(((0, 1, 2),), dtype=np.int64)
    result = build_linear_bijective_shell(vertices, faces, source_patch_ids=(17,))
    assert result.success and result.shell is not None
    return vertices, faces, result.shell


def _cube_shell() -> tuple[np.ndarray, np.ndarray, BijectiveShell]:
    mesh = read_stl(Path(__file__).parent / "benchmarks" / "cube.stl")
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    result = build_linear_bijective_shell(vertices, faces)
    assert result.success and result.shell is not None
    return vertices, faces, result.shell


def test_hand_computable_prism_projection_inverse_and_middle_round_trip() -> None:
    _, _, shell = _single_prism()
    thickness = float(shell.thickness[0])
    point = np.asarray((0.4, 0.3, 0.4 * thickness), dtype=np.float64)

    projection = shell.project_point(point)

    assert projection.status is ShellProjectionStatus.MAPPED
    assert projection.coordinate is not None
    assert projection.coordinate.prism_index == 0
    assert projection.coordinate.alpha == pytest.approx(0.2, abs=1e-14)
    assert projection.coordinate.beta == pytest.approx(0.3, abs=1e-14)
    assert projection.coordinate.h == pytest.approx(0.4, abs=1e-14)
    assert projection.reconstructed_point is not None
    assert projection.middle_point is not None
    np.testing.assert_allclose(np.asarray(projection.reconstructed_point), point, atol=1e-14)
    np.testing.assert_allclose(np.asarray(projection.middle_point), (0.4, 0.3, 0.0), atol=1e-14)
    assert projection.round_trip_error is not None
    assert projection.round_trip_error <= 1e-14

    inverse = shell.inverse_project(ShellCoordinate(0, 0.2, 0.3, -0.75))
    assert inverse is not None
    np.testing.assert_allclose(np.asarray(inverse), (0.4, 0.3, -0.75 * thickness), atol=1e-14)


def test_patch_payload_pullback_is_immutable_and_face_ordered() -> None:
    vertices = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
        ),
        dtype=np.float64,
    )
    faces = np.asarray(((0, 1, 2), (0, 2, 3)), dtype=np.int64)
    result = build_linear_bijective_shell(
        vertices,
        faces,
        source_patch_ids=("inlet", "wall"),
    )
    assert result.success and result.shell is not None

    report = result.shell.census_face_centroids(vertices, faces)

    assert report.total == report.mapped == 2
    assert report.coverage == 1.0
    assert tuple(
        projection.source_payload.patch_id
        for projection in report.projections
        if projection.source_payload is not None
    ) == ("inlet", "wall")
    first_payload = report.projections[0].source_payload
    assert first_payload == SourceFacePayload(0, (0, 1, 2), "inlet")
    assert first_payload is not None
    with pytest.raises(FrozenInstanceError):
        first_payload.patch_id = "changed"


def test_unmapped_ambiguous_pinched_and_non_finite_are_never_assigned() -> None:
    vertices, faces, shell = _single_prism()
    vertices_before = vertices.tobytes()
    faces_before = faces.tobytes()

    invalid_report = shell.census_points(
        np.asarray(((10.0, 10.0, 10.0), (np.nan, 0.0, 0.0))),
    )
    assert invalid_report.total == 2
    assert invalid_report.mapped == 0
    assert invalid_report.unmapped == 1
    assert invalid_report.non_finite == 1
    assert all(projection.source_payload is None for projection in invalid_report.projections)

    duplicated = replace(
        shell,
        faces=np.vstack((shell.faces, shell.faces)),
        prism_tets=(shell.prism_tets[0], shell.prism_tets[0]),
        prism_aabb_min=np.vstack((shell.prism_aabb_min, shell.prism_aabb_min)),
        prism_aabb_max=np.vstack((shell.prism_aabb_max, shell.prism_aabb_max)),
        source_face_payloads=(
            shell.source_face_payloads[0],
            SourceFacePayload(1, (0, 1, 2), 99),
        ),
    )
    ambiguous = duplicated.project_point(np.asarray((0.4, 0.3, 0.0)))
    assert ambiguous.status is ShellProjectionStatus.AMBIGUOUS
    assert ambiguous.candidate_prism_indices == (0, 1)
    assert ambiguous.source_payload is None
    assert duplicated.census_points(np.asarray(((0.4, 0.3, 0.0),))).ambiguous == 1

    pinched = replace(shell, thickness=np.zeros_like(shell.thickness))
    pinch_result = pinched.project_point(vertices[0])
    assert pinch_result.status is ShellProjectionStatus.PINCHED
    assert pinch_result.source_payload is None
    assert pinched.census_points(vertices[[0]]).pinched == 1

    assert vertices.tobytes() == vertices_before
    assert faces.tobytes() == faces_before


def test_default_off_is_inert_and_on_is_report_only_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vertices, faces, shell = _cube_shell()
    input_vertex_bytes = vertices.tobytes()
    input_face_bytes = faces.tobytes()

    monkeypatch.delenv("AUTO_TESSELL_TRI_SHELL_PROVENANCE1", raising=False)
    off = OperatorTransaction(vertices, faces, target_edge_length=1.0)
    off_rounds = off.run_rounds(max_rounds=1, shell=shell)
    assert off.shell_provenance_reports == []

    monkeypatch.setenv("AUTO_TESSELL_TRI_SHELL_PROVENANCE1", "1")
    on_runs = []
    for _ in range(2):
        transaction = OperatorTransaction(vertices, faces, target_edge_length=1.0)
        rounds = transaction.run_rounds(max_rounds=1, shell=shell)
        on_runs.append((transaction, rounds))

    for transaction, rounds in on_runs:
        assert rounds == off_rounds
        assert transaction.state.vertices.tobytes() == off.state.vertices.tobytes()
        assert transaction.state.faces.tobytes() == off.state.faces.tobytes()
        assert transaction.shell_checkpoint_reports == off.shell_checkpoint_reports
        assert len(transaction.shell_provenance_reports) == 1

    assert on_runs[0][0].shell_provenance_reports == on_runs[1][0].shell_provenance_reports

    def forced_report_failure(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("forced report-only failure")

    monkeypatch.setattr(type(shell), "census_face_centroids", forced_report_failure)
    failed_report = OperatorTransaction(vertices, faces, target_edge_length=1.0)
    failed_rounds = failed_report.run_rounds(max_rounds=1, shell=shell)
    assert failed_rounds == off_rounds
    assert failed_report.state.vertices.tobytes() == off.state.vertices.tobytes()
    assert failed_report.state.faces.tobytes() == off.state.faces.tobytes()
    assert failed_report.shell_provenance_reports == []
    assert failed_report.shell_provenance_report_failures == ["RuntimeError"]

    assert vertices.tobytes() == input_vertex_bytes
    assert faces.tobytes() == input_face_bytes
