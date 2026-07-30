"""L0 contracts for the runtime-disconnected native-tri candidate certificate."""

from __future__ import annotations

import numpy as np
import trimesh

from core.preprocessor.native_tri.certificate import certify_native_tri_candidate


def _cube() -> tuple[np.ndarray, np.ndarray]:
    mesh = trimesh.creation.box()
    return np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces, dtype=np.int64)


def _clone_provenance(face_count: int) -> tuple[tuple[int, ...], ...]:
    return tuple((index,) for index in range(face_count))


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
