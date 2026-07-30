"""Runtime-disconnected L0 certificate for native-tri surface candidates.

This module deliberately certifies only an exact source clone.  It is an
oracle for the future topology-changing route, not an operator and not a
geometric-envelope implementation.  In particular, a candidate that changes
vertices or connectivity is rejected even if it supplies face provenance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from numbers import Integral

import numpy as np


def _array_hash(values: np.ndarray) -> str:
    """Return a dtype- and shape-sensitive deterministic array hash."""
    contiguous = np.ascontiguousarray(values)
    digest = sha256()
    digest.update(str(contiguous.dtype).encode("ascii"))
    digest.update(np.asarray(contiguous.shape, dtype=np.int64).tobytes())
    digest.update(contiguous.tobytes())
    return digest.hexdigest()


def _as_vertices(values: np.ndarray) -> np.ndarray | None:
    try:
        vertices = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        return None
    return vertices


def _as_faces(values: np.ndarray, vertex_count: int) -> np.ndarray | None:
    try:
        raw_faces = np.asarray(values)
    except (TypeError, ValueError):
        return None
    if raw_faces.ndim != 2 or raw_faces.shape[1] != 3:
        return None
    if any(
        isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral)
        for value in raw_faces.flat
    ):
        return None
    try:
        faces = np.asarray(raw_faces, dtype=np.int64)
    except (OverflowError, TypeError, ValueError):
        return None
    if (faces < 0).any() or (faces >= vertex_count).any():
        return None
    return faces


@dataclass(frozen=True, slots=True)
class NativeTriCandidateCertificate:
    """Evidence for a candidate evaluated under the intentionally strict L0 contract."""

    accepted: bool
    rejection_reasons: tuple[str, ...]
    source_vertices_hash: str | None
    source_faces_hash: str | None
    candidate_vertices_hash: str | None
    candidate_faces_hash: str | None
    source_envelope_preserved: bool
    topology_preserved: bool
    provenance_complete: bool
    provenance_unambiguous: bool
    provenance_preserved: bool
    face_provenance: tuple[tuple[int, ...], ...]
    contract: str = "native_tri_source_clone_l0"


def _normalise_face_provenance(
    provenance: Sequence[Sequence[int]] | None,
    *,
    candidate_face_count: int,
    source_face_count: int,
) -> tuple[tuple[tuple[int, ...], ...], bool, bool, str | None]:
    """Validate one unambiguous source-face reference for every candidate face."""
    if provenance is None:
        return (), False, False, "provenance_missing"
    if len(provenance) != candidate_face_count:
        return (), False, False, "provenance_incomplete"

    normalised: list[tuple[int, ...]] = []
    for references in provenance:
        try:
            raw_entry = tuple(references)
        except TypeError:
            return (), False, False, "provenance_invalid"
        if any(
            isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral)
            for value in raw_entry
        ):
            return (), False, False, "provenance_invalid"
        entry = tuple(int(value) for value in raw_entry)
        if len(entry) != 1:
            return (), True, False, "provenance_ambiguous"
        if entry[0] < 0 or entry[0] >= source_face_count:
            return (), False, False, "provenance_invalid"
        normalised.append(entry)
    return tuple(normalised), True, True, None


def certify_native_tri_candidate(
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    candidate_vertices: np.ndarray,
    candidate_faces: np.ndarray,
    *,
    face_provenance: Sequence[Sequence[int]] | None,
) -> NativeTriCandidateCertificate:
    """Fail closed unless the candidate is the exact source clone with proof.

    L0 intentionally does *not* claim that a non-clone is inside the source
    envelope.  Future L1 work must replace this clone-only check with a
    conservative candidate-envelope test before any topology edit can route.
    """
    source_v = _as_vertices(source_vertices)
    candidate_v = _as_vertices(candidate_vertices)
    source_f = _as_faces(source_faces, len(source_v)) if source_v is not None else None
    candidate_f = _as_faces(candidate_faces, len(candidate_v)) if candidate_v is not None else None

    source_vertices_hash = _array_hash(source_v) if source_v is not None else None
    source_faces_hash = _array_hash(source_f) if source_f is not None else None
    candidate_vertices_hash = _array_hash(candidate_v) if candidate_v is not None else None
    candidate_faces_hash = _array_hash(candidate_f) if candidate_f is not None else None
    reasons: list[str] = []
    if source_v is None or source_f is None:
        reasons.append("source_invalid")
    if candidate_v is None or candidate_f is None:
        reasons.append("candidate_invalid")

    candidate_face_count = len(candidate_f) if candidate_f is not None else 0
    source_face_count = len(source_f) if source_f is not None else 0
    provenance, complete, unambiguous, provenance_error = _normalise_face_provenance(
        face_provenance,
        candidate_face_count=candidate_face_count,
        source_face_count=source_face_count,
    )
    if provenance_error is not None:
        reasons.append(provenance_error)

    source_envelope_preserved = (
        source_vertices_hash is not None and source_vertices_hash == candidate_vertices_hash
    )
    topology_preserved = source_faces_hash is not None and source_faces_hash == candidate_faces_hash
    if not source_envelope_preserved:
        reasons.append("source_envelope_violation_l0")
    if not topology_preserved:
        reasons.append("topology_changed_l0")

    expected_clone_provenance = tuple((index,) for index in range(source_face_count))
    provenance_preserved = complete and unambiguous and provenance == expected_clone_provenance
    if complete and unambiguous and not provenance_preserved:
        reasons.append("source_clone_provenance_mismatch")

    return NativeTriCandidateCertificate(
        accepted=not reasons,
        rejection_reasons=tuple(reasons),
        source_vertices_hash=source_vertices_hash,
        source_faces_hash=source_faces_hash,
        candidate_vertices_hash=candidate_vertices_hash,
        candidate_faces_hash=candidate_faces_hash,
        source_envelope_preserved=source_envelope_preserved,
        topology_preserved=topology_preserved,
        provenance_complete=complete,
        provenance_unambiguous=unambiguous,
        provenance_preserved=provenance_preserved,
        face_provenance=provenance,
    )
