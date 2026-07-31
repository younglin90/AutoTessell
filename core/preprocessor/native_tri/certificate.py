"""Runtime-disconnected L0 certificate for native-tri surface candidates.

This module deliberately certifies only an exact source clone.  It is an
oracle for the future topology-changing route, not an operator and not a
geometric-envelope implementation.  In particular, a candidate that changes
vertices or connectivity is rejected even if it supplies face provenance.
"""

from __future__ import annotations

import json
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
class _SurfaceTopologyAudit:
    """Read-only topology facts used only by the source-certificate diagnostic."""

    valid: bool
    closed_oriented_manifold: bool
    edge_count: int
    component_count: int
    euler_characteristic: int | None


def _surface_topology_audit(
    vertices: np.ndarray | None,
    faces: np.ndarray | None,
) -> _SurfaceTopologyAudit:
    """Return exact index-topology facts; never repair or reorient a surface."""
    if vertices is None or faces is None or len(faces) == 0:
        return _SurfaceTopologyAudit(False, False, 0, 0, None)
    triangles = vertices[faces]
    twice_area = np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
        axis=1,
    )
    if not np.isfinite(twice_area).all() or np.any(twice_area <= np.finfo(float).tiny):
        return _SurfaceTopologyAudit(False, False, 0, 0, None)

    edge_faces: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for face_index, face in enumerate(faces.tolist()):
        for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            start, end = int(first), int(second)
            edge = (min(start, end), max(start, end))
            direction = 1 if (start, end) == edge else -1
            edge_faces.setdefault(edge, []).append((face_index, direction))
    closed_oriented = all(
        len(owners) == 2 and owners[0][1] != owners[1][1] for owners in edge_faces.values()
    )

    adjacency: list[set[int]] = [set() for _ in range(len(faces))]
    for owners in edge_faces.values():
        if len(owners) == 2:
            first, second = owners[0][0], owners[1][0]
            adjacency[first].add(second)
            adjacency[second].add(first)
    component_count = 0
    unseen = set(range(len(faces)))
    while unseen:
        component_count += 1
        pending = [unseen.pop()]
        while pending:
            face_index = pending.pop()
            neighbours = adjacency[face_index].intersection(unseen)
            unseen.difference_update(neighbours)
            pending.extend(neighbours)
    return _SurfaceTopologyAudit(
        True,
        closed_oriented,
        len(edge_faces),
        component_count,
        len(vertices) - len(edge_faces) + len(faces),
    )


def _sharp_feature_edges(vertices: np.ndarray, faces: np.ndarray) -> set[tuple[int, int]]:
    """Return observed 30-degree source creases without assigning their semantics."""
    normals = np.cross(
        vertices[faces[:, 1]] - vertices[faces[:, 0]],
        vertices[faces[:, 2]] - vertices[faces[:, 0]],
    )
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    edge_faces: dict[tuple[int, int], list[int]] = {}
    for face_index, face in enumerate(faces.tolist()):
        for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = (min(int(first), int(second)), max(int(first), int(second)))
            edge_faces.setdefault(edge, []).append(face_index)
    observed: set[tuple[int, int]] = set()
    for edge, owners in edge_faces.items():
        if len(owners) != 2:
            continue
        cosine = float(np.clip(np.dot(normals[owners[0]], normals[owners[1]]), -1.0, 1.0))
        if float(np.degrees(np.arccos(cosine))) >= 30.0:
            observed.add(edge)
    return observed


def _normalise_patch_ids(
    patch_ids: Sequence[int | str | None] | None,
    face_count: int,
) -> tuple[tuple[int | str | None, ...], bool]:
    """Keep source patch payloads immutable; invalid payloads are never coerced."""
    if patch_ids is None:
        return (None,) * face_count, True
    if len(patch_ids) != face_count:
        return (), False
    values: list[int | str | None] = []
    for value in patch_ids:
        scalar = value.item() if isinstance(value, np.generic) else value
        if isinstance(scalar, bool) or not isinstance(scalar, (int, str, type(None))):
            return (), False
        values.append(scalar)
    return tuple(values), True


def _normalise_feature_edges(
    feature_edges: Sequence[Sequence[int]] | None,
    *,
    source_faces: np.ndarray | None,
) -> tuple[set[tuple[int, int]], bool]:
    """Validate explicitly supplied feature ownership without inferring it."""
    if feature_edges is None:
        return set(), True
    if source_faces is None:
        return set(), False
    source_edges = {
        (min(int(first), int(second)), max(int(first), int(second)))
        for face in source_faces.tolist()
        for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))
    }
    normalized: set[tuple[int, int]] = set()
    for raw_edge in feature_edges:
        try:
            first, second = tuple(raw_edge)
        except (TypeError, ValueError):
            return set(), False
        if any(
            isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral)
            for value in (first, second)
        ):
            return set(), False
        edge = (min(int(first), int(second)), max(int(first), int(second)))
        if edge[0] == edge[1] or edge not in source_edges:
            return set(), False
        normalized.add(edge)
    return normalized, True


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


@dataclass(frozen=True, slots=True)
class NativeTriSourceCertificateDiagnostic:
    """Read-only L1 evidence; only an exact L0 clone can be accepted.

    The shell fields deliberately retain their sampled status in their names.
    They are observations for planning an exact whole-triangle envelope gate,
    never a containment certificate for a topology-changing candidate.
    """

    accepted: bool
    rejection_reasons: tuple[str, ...]
    source_vertices_hash: str | None
    source_faces_hash: str | None
    source_payload_hash: str | None
    declared_feature_edges: tuple[tuple[int, int], ...] | None
    declared_feature_edges_sha256: str | None
    candidate_vertices_hash: str | None
    candidate_faces_hash: str | None
    source_closed_oriented_manifold: bool
    candidate_closed_oriented_manifold: bool
    topology_invariants_preserved: bool
    source_feature_edge_count: int
    feature_ownership_explicit: bool
    source_patch_payload_valid: bool
    candidate_face_provenance_complete: bool
    candidate_face_provenance_unambiguous: bool
    candidate_source_face_coverage_complete: bool
    shell_constructed: bool
    shell_reason: str
    sampled_shell_containment_ok: bool | None
    sampled_shell_failed_face_index: int | None
    centroid_mapped_faces: int
    centroid_unmapped_faces: int
    centroid_ambiguous_faces: int
    centroid_pinched_faces: int
    centroid_non_finite_faces: int
    certifiable_candidate_faces: int
    candidate_face_count: int
    clone_reference: bool
    contract: str = "native_tri_source_certificate_preflight_l1_diagnostic"


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


def diagnose_native_tri_source_certificate(
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    candidate_vertices: np.ndarray,
    candidate_faces: np.ndarray,
    *,
    face_provenance: Sequence[Sequence[int]] | None,
    source_patch_ids: Sequence[int | str | None] | None = None,
    source_feature_edges: Sequence[Sequence[int]] | None = None,
    shell_local_scale_fraction: float = 0.2,
) -> NativeTriSourceCertificateDiagnostic:
    """Diagnose a future source certificate without enabling topology edits.

    An exact source clone delegates to the L0 certificate.  Every non-clone
    is rejected regardless of sampled-shell or centroid-projection values:
    neither establishes whole-triangle containment, source coverage, nor
    feature/boundary transfer.  This makes the diagnostic safe to retain while
    the exact Wang-style envelope and explicit feature-path contract are
    separate work.
    """
    source_v = _as_vertices(source_vertices)
    candidate_v = _as_vertices(candidate_vertices)
    source_f = _as_faces(source_faces, len(source_v)) if source_v is not None else None
    candidate_f = _as_faces(candidate_faces, len(candidate_v)) if candidate_v is not None else None
    source_vertices_hash = _array_hash(source_v) if source_v is not None else None
    source_faces_hash = _array_hash(source_f) if source_f is not None else None
    candidate_vertices_hash = _array_hash(candidate_v) if candidate_v is not None else None
    candidate_faces_hash = _array_hash(candidate_f) if candidate_f is not None else None
    source_audit = _surface_topology_audit(source_v, source_f)
    candidate_audit = _surface_topology_audit(candidate_v, candidate_f)
    candidate_face_count = len(candidate_f) if candidate_f is not None else 0
    source_face_count = len(source_f) if source_f is not None else 0
    provenance, complete, unambiguous, provenance_error = _normalise_face_provenance(
        face_provenance,
        candidate_face_count=candidate_face_count,
        source_face_count=source_face_count,
    )
    patch_ids, patch_payload_valid = _normalise_patch_ids(source_patch_ids, source_face_count)
    observed_features = (
        _sharp_feature_edges(source_v, source_f)
        if source_v is not None and source_f is not None and source_audit.valid
        else set()
    )
    declared_features, feature_declaration_valid = _normalise_feature_edges(
        source_feature_edges,
        source_faces=source_f,
    )
    canonical_declared_features = (
        None
        if source_feature_edges is None
        else tuple(sorted(declared_features)) if feature_declaration_valid else None
    )
    declared_feature_edges_sha256 = (
        sha256(
            json.dumps(
                canonical_declared_features,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if feature_declaration_valid
        else None
    )
    payload_hash = (
        sha256(
            json.dumps(
                {
                    "faces": source_f.tolist(),
                    "patch_ids": patch_ids,
                    "declared_feature_edges": canonical_declared_features,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if source_f is not None and patch_payload_valid and feature_declaration_valid
        else None
    )
    feature_ownership_explicit = (
        feature_declaration_valid
        and source_feature_edges is not None
        and observed_features.issubset(declared_features)
    )
    topology_invariants_preserved = (
        source_audit.closed_oriented_manifold
        and candidate_audit.closed_oriented_manifold
        and source_audit.component_count == candidate_audit.component_count
        and source_audit.euler_characteristic == candidate_audit.euler_characteristic
    )
    clone_reference = (
        source_vertices_hash is not None
        and source_vertices_hash == candidate_vertices_hash
        and source_faces_hash is not None
        and source_faces_hash == candidate_faces_hash
    )

    reasons: list[str] = []
    if not source_audit.valid:
        reasons.append("source_preflight_invalid")
    elif not source_audit.closed_oriented_manifold:
        reasons.append("source_preflight_not_closed_oriented_manifold")
    if not candidate_audit.valid:
        reasons.append("candidate_preflight_invalid")
    elif not candidate_audit.closed_oriented_manifold:
        reasons.append("candidate_preflight_not_closed_oriented_manifold")
    if not topology_invariants_preserved:
        reasons.append("topology_invariants_changed")
    if not patch_payload_valid:
        reasons.append("source_patch_payload_invalid")
    if not feature_declaration_valid:
        reasons.append("source_feature_ownership_invalid")
    elif observed_features and not feature_ownership_explicit and not clone_reference:
        reasons.append("source_feature_ownership_missing")
    if provenance_error is not None:
        reasons.append(f"candidate_face_{provenance_error}")
    source_coverage_complete = (
        complete
        and unambiguous
        and {entry[0] for entry in provenance} == set(range(source_face_count))
    )
    if complete and unambiguous and not source_coverage_complete:
        reasons.append("candidate_source_face_coverage_incomplete")

    shell_constructed = False
    shell_reason = "not_attempted"
    sampled_containment_ok: bool | None = None
    sampled_failed_face_index: int | None = None
    centroid_mapped = centroid_unmapped = centroid_ambiguous = 0
    centroid_pinched = centroid_non_finite = 0
    if (
        source_audit.valid
        and source_audit.closed_oriented_manifold
        and candidate_audit.valid
        and candidate_f is not None
        and source_v is not None
        and source_f is not None
        and patch_payload_valid
        and np.isfinite(shell_local_scale_fraction)
        and 0.0 < shell_local_scale_fraction <= 1.0
    ):
        from .bijective_shell import build_linear_bijective_shell

        shell_result = build_linear_bijective_shell(
            source_v,
            source_f,
            local_scale_fraction=float(shell_local_scale_fraction),
            source_patch_ids=patch_ids,
        )
        shell_constructed = shell_result.success
        shell_reason = shell_result.reason
        if shell_result.shell is not None:
            assert candidate_v is not None
            containment = shell_result.shell.check_round_containment(candidate_v, candidate_f)
            sampled_containment_ok = containment.accepted
            sampled_failed_face_index = containment.failed_face_index
            census = shell_result.shell.census_face_centroids(candidate_v, candidate_f)
            centroid_mapped = census.mapped
            centroid_unmapped = census.unmapped
            centroid_ambiguous = census.ambiguous
            centroid_pinched = census.pinched
            centroid_non_finite = census.non_finite
            if not containment.accepted and not clone_reference:
                reasons.append("sampled_shell_containment_failed_diagnostic")
            if census.mapped != candidate_face_count and not clone_reference:
                reasons.append("candidate_centroid_provenance_incomplete_diagnostic")
        elif not clone_reference:
            reasons.append("source_shell_construction_failed_diagnostic")
    elif not clone_reference:
        shell_reason = "preflight_or_shell_parameter_invalid"
        reasons.append("source_shell_not_attempted_diagnostic")

    l0 = certify_native_tri_candidate(
        source_vertices,
        source_faces,
        candidate_vertices,
        candidate_faces,
        face_provenance=face_provenance,
    )
    if clone_reference:
        reasons.extend(l0.rejection_reasons)
    else:
        reasons.append("nonclone_runtime_certificate_unavailable")
    return NativeTriSourceCertificateDiagnostic(
        accepted=clone_reference and l0.accepted and not reasons,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
        source_vertices_hash=source_vertices_hash,
        source_faces_hash=source_faces_hash,
        source_payload_hash=payload_hash,
        declared_feature_edges=canonical_declared_features,
        declared_feature_edges_sha256=declared_feature_edges_sha256,
        candidate_vertices_hash=candidate_vertices_hash,
        candidate_faces_hash=candidate_faces_hash,
        source_closed_oriented_manifold=source_audit.closed_oriented_manifold,
        candidate_closed_oriented_manifold=candidate_audit.closed_oriented_manifold,
        topology_invariants_preserved=topology_invariants_preserved,
        source_feature_edge_count=len(observed_features),
        feature_ownership_explicit=feature_ownership_explicit,
        source_patch_payload_valid=patch_payload_valid,
        candidate_face_provenance_complete=complete,
        candidate_face_provenance_unambiguous=unambiguous,
        candidate_source_face_coverage_complete=source_coverage_complete,
        shell_constructed=shell_constructed,
        shell_reason=shell_reason,
        sampled_shell_containment_ok=sampled_containment_ok,
        sampled_shell_failed_face_index=sampled_failed_face_index,
        centroid_mapped_faces=centroid_mapped,
        centroid_unmapped_faces=centroid_unmapped,
        centroid_ambiguous_faces=centroid_ambiguous,
        centroid_pinched_faces=centroid_pinched,
        centroid_non_finite_faces=centroid_non_finite,
        certifiable_candidate_faces=source_face_count if clone_reference and l0.accepted else 0,
        candidate_face_count=candidate_face_count,
        clone_reference=clone_reference,
    )
