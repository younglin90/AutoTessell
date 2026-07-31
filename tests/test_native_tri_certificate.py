"""L0 contracts for the runtime-disconnected native-tri candidate certificate."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri import OperatorTransaction
from core.preprocessor.native_tri.certificate import (
    certify_native_tri_candidate,
    diagnose_native_tri_source_certificate,
)


def _cube() -> tuple[np.ndarray, np.ndarray]:
    mesh = trimesh.creation.box()
    return np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces, dtype=np.int64)


def _clone_provenance(face_count: int) -> tuple[tuple[int, ...], ...]:
    return tuple((index,) for index in range(face_count))


def _cylinder_operator_candidate() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mesh = read_stl(Path(__file__).parent / "benchmarks" / "cylinder.stl")
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    lengths = np.concatenate(
        [
            np.linalg.norm(vertices[faces[:, index]] - vertices[faces[:, (index + 1) % 3]], axis=1)
            for index in range(3)
        ]
    )
    transaction = OperatorTransaction(
        vertices,
        faces,
        target_edge_length=float(np.median(lengths[lengths > 0.0])),
    )
    transaction.run_one_round(smooth=False)
    return vertices, faces, transaction.state.vertices, transaction.state.faces


def test_exact_source_clone_passes_and_preserves_source_hashes() -> None:
    vertices, faces = _cube()
    certificate = certify_native_tri_candidate(
        vertices,
        faces,
        vertices.copy(),
        faces.copy(),
        face_provenance=_clone_provenance(len(faces)),
    )

    assert certificate.accepted is True
    assert certificate.rejection_reasons == ()
    assert certificate.source_vertices_hash == certificate.candidate_vertices_hash
    assert certificate.source_faces_hash == certificate.candidate_faces_hash
    assert certificate.source_envelope_preserved is True
    assert certificate.topology_preserved is True
    assert certificate.provenance_preserved is True
    assert certificate.contract == "native_tri_source_clone_l0"


def test_moved_candidate_rejects_source_envelope_violation() -> None:
    vertices, faces = _cube()
    moved = vertices.copy()
    moved[0, 0] += 1e-6
    certificate = certify_native_tri_candidate(
        vertices, faces, moved, faces, face_provenance=_clone_provenance(len(faces))
    )

    assert certificate.accepted is False
    assert "source_envelope_violation_l0" in certificate.rejection_reasons
    assert certificate.source_envelope_preserved is False


def test_topology_edit_without_per_face_provenance_rejects() -> None:
    vertices, faces = _cube()
    edited_faces = faces[:-1].copy()
    certificate = certify_native_tri_candidate(
        vertices, faces, vertices, edited_faces, face_provenance=None
    )

    assert certificate.accepted is False
    assert "topology_changed_l0" in certificate.rejection_reasons
    assert "provenance_missing" in certificate.rejection_reasons
    assert certificate.provenance_preserved is False


def test_invalid_and_ambiguous_provenance_reject() -> None:
    vertices, faces = _cube()
    invalid = list(_clone_provenance(len(faces)))
    invalid[0] = (len(faces),)
    invalid_certificate = certify_native_tri_candidate(
        vertices, faces, vertices, faces, face_provenance=invalid
    )
    assert invalid_certificate.accepted is False
    assert "provenance_invalid" in invalid_certificate.rejection_reasons

    ambiguous = list(_clone_provenance(len(faces)))
    ambiguous[0] = (0, 1)
    ambiguous_certificate = certify_native_tri_candidate(
        vertices, faces, vertices, faces, face_provenance=ambiguous
    )
    assert ambiguous_certificate.accepted is False
    assert "provenance_ambiguous" in ambiguous_certificate.rejection_reasons


def test_fractional_boolean_and_string_provenance_reject_without_coercion() -> None:
    vertices, faces = _cube()
    for invalid_index in (1.5, True, "1"):
        provenance = list(_clone_provenance(len(faces)))
        provenance[0] = (invalid_index,)  # type: ignore[assignment]
        certificate = certify_native_tri_candidate(
            vertices, faces, vertices, faces, face_provenance=provenance
        )
        assert certificate.accepted is False
        assert "provenance_invalid" in certificate.rejection_reasons


def test_non_integral_or_boolean_candidate_face_indices_reject_without_coercion() -> None:
    vertices, faces = _cube()
    for invalid_index in (1.5, True, "1"):
        malformed_faces = faces.astype(object)
        malformed_faces[0, 0] = invalid_index
        certificate = certify_native_tri_candidate(
            vertices,
            faces,
            vertices,
            malformed_faces,
            face_provenance=_clone_provenance(len(faces)),
        )
        assert certificate.accepted is False
        assert "candidate_invalid" in certificate.rejection_reasons
        assert certificate.topology_preserved is False


def test_certificate_is_deterministic_across_three_runs() -> None:
    vertices, faces = _cube()
    certificates = [
        certify_native_tri_candidate(
            vertices,
            faces,
            vertices.copy(),
            faces.copy(),
            face_provenance=_clone_provenance(len(faces)),
        )
        for _ in range(3)
    ]

    assert certificates[0] == certificates[1] == certificates[2]


def test_source_certificate_clone_is_l0_reference_only_with_full_face_count() -> None:
    vertices, faces, _, _ = _cylinder_operator_candidate()
    before_vertices = vertices.tobytes()
    before_faces = faces.tobytes()
    diagnostics = [
        diagnose_native_tri_source_certificate(
            vertices,
            faces,
            vertices.copy(),
            faces.copy(),
            face_provenance=_clone_provenance(len(faces)),
            source_patch_ids=tuple("wall" for _ in faces),
            shell_local_scale_fraction=0.2,
        )
        for _ in range(3)
    ]

    assert diagnostics == [diagnostics[0]] * 3
    report = diagnostics[0]
    assert report.accepted is True
    assert report.clone_reference is True
    assert report.candidate_face_count == 128
    assert report.certifiable_candidate_faces == 128
    assert report.source_closed_oriented_manifold is True
    assert report.candidate_closed_oriented_manifold is True
    assert report.topology_invariants_preserved is True
    assert report.shell_constructed is True
    assert report.sampled_shell_containment_ok is True
    assert report.centroid_mapped_faces == 128
    assert report.source_payload_hash is not None
    assert vertices.tobytes() == before_vertices
    assert faces.tobytes() == before_faces


def test_source_certificate_refuses_cylinder_topology_edit_before_runtime_use() -> None:
    vertices, faces, candidate_vertices, candidate_faces = _cylinder_operator_candidate()
    before = (
        vertices.tobytes(),
        faces.tobytes(),
        candidate_vertices.tobytes(),
        candidate_faces.tobytes(),
    )
    report = diagnose_native_tri_source_certificate(
        vertices,
        faces,
        candidate_vertices,
        candidate_faces,
        face_provenance=None,
        source_patch_ids=tuple("wall" for _ in faces),
        shell_local_scale_fraction=0.2,
    )

    assert report.accepted is False
    assert report.clone_reference is False
    assert report.candidate_face_count == 32
    assert report.certifiable_candidate_faces == 0
    assert report.source_feature_edge_count == 64
    assert report.feature_ownership_explicit is False
    assert report.shell_constructed is True
    assert report.sampled_shell_containment_ok is False
    assert report.sampled_shell_failed_face_index == 0
    assert report.centroid_mapped_faces == 4
    assert report.centroid_unmapped_faces == 28
    assert report.candidate_face_provenance_complete is False
    assert "source_feature_ownership_missing" in report.rejection_reasons
    assert "candidate_face_provenance_missing" in report.rejection_reasons
    assert "sampled_shell_containment_failed_diagnostic" in report.rejection_reasons
    assert "candidate_centroid_provenance_incomplete_diagnostic" in report.rejection_reasons
    assert "nonclone_runtime_certificate_unavailable" in report.rejection_reasons
    assert before == (
        vertices.tobytes(),
        faces.tobytes(),
        candidate_vertices.tobytes(),
        candidate_faces.tobytes(),
    )


def test_source_certificate_rejects_ambiguous_or_missing_nonclone_provenance() -> None:
    vertices, faces = _cube()
    reordered = faces[::-1].copy()
    ambiguous = tuple((0, 1) for _ in reordered)
    ambiguous_report = diagnose_native_tri_source_certificate(
        vertices,
        faces,
        vertices.copy(),
        reordered,
        face_provenance=ambiguous,
        source_feature_edges=(),
    )
    missing_report = diagnose_native_tri_source_certificate(
        vertices,
        faces,
        vertices.copy(),
        reordered,
        face_provenance=None,
        source_feature_edges=(),
    )

    for report, reason in (
        (ambiguous_report, "candidate_face_provenance_ambiguous"),
        (missing_report, "candidate_face_provenance_missing"),
    ):
        assert report.accepted is False
        assert report.clone_reference is False
        assert report.certifiable_candidate_faces == 0
        assert reason in report.rejection_reasons
        assert "nonclone_runtime_certificate_unavailable" in report.rejection_reasons
