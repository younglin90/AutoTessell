"""Read-only provenance records for the first native-tet strict overlap.

The generator never imports this module.  Test instrumentation supplies the
immutable input surface and the arrays already passed to the existing strict
internal-face audit.  This module records the first same-side internal-face
debt together with the existing source-component/provenance evidence; it does
not choose a policy, alter a candidate, or write an artifact.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

import numpy as np

from .rescue_gate import (
    InternalFaceSidednessAudit,
    audit_internal_face_sidedness,
    audit_source_component_bijection,
)

_SCHEMA_VERSION = "native_tet_initial_overlap_source_l1/v1"


@dataclass(frozen=True, slots=True)
class InitialStrictOverlapSourceRecord:
    """Immutable stage evidence, never an acceptance or repair certificate."""

    schema_version: str
    fixture: str
    repeat: int
    audit_call_index: int
    stage: str
    source_points_sha256: str
    source_faces_sha256: str
    candidate_points_sha256: str
    candidate_tets_sha256: str
    n_internal_faces: int
    n_same_side_internal_faces: int
    n_ambiguous_internal_faces: int
    n_source_components: int
    n_candidate_boundary_components: int
    n_missing_source_vertices: int
    n_missing_source_faces: int
    n_unowned_candidate_faces: int
    n_uncovered_source_patches: int
    n_area_mismatch_patches: int
    n_feature_boundary_mismatches: int
    n_overlap_pairs: int
    component_bijective: bool
    source_faces_preserved: bool
    overlap_source_class: str

    def as_json(self) -> dict[str, object]:
        """Return scalar-only durable evidence in schema field order."""
        return asdict(self)


def _matrix(
    values: np.ndarray,
    *,
    dtype: np.dtype[np.float64] | np.dtype[np.int64],
    columns: int,
    name: str,
) -> np.ndarray:
    if not isinstance(values, np.ndarray) or values.dtype != dtype:
        raise TypeError(f"{name} must be an ndarray with dtype {dtype}")
    if values.ndim != 2 or values.shape[1] != columns:
        raise ValueError(f"{name} must have shape (N, {columns})")
    if not values.flags.c_contiguous:
        raise ValueError(f"{name} must be C-contiguous")
    return values


def array_sha256(values: np.ndarray) -> str:
    """Hash exact dtype, shape, and C-order bytes without changing ``values``."""
    if not isinstance(values, np.ndarray) or not values.flags.c_contiguous:
        raise ValueError("array_sha256 requires a C-contiguous ndarray")
    digest = hashlib.sha256()
    digest.update(values.dtype.str.encode("ascii"))
    digest.update(b"\0")
    digest.update(repr(tuple(int(size) for size in values.shape)).encode("ascii"))
    digest.update(b"\0")
    digest.update(memoryview(values).cast("B"))
    return digest.hexdigest()


def _classify(
    sidedness: InternalFaceSidednessAudit,
    *,
    source_faces_preserved: bool,
    n_overlap_pairs: int,
) -> str:
    """Classify existing evidence without assigning a new strictness policy."""
    if sidedness.n_same_side_internal_faces > 0:
        if source_faces_preserved:
            return "same_side_overlap_source_provenance_preserved"
        if n_overlap_pairs > 0:
            return "same_side_overlap_planar_patch_overlap"
        return "same_side_overlap_source_provenance_debt"
    if sidedness.n_ambiguous_internal_faces > 0:
        return "strict_ambiguity_without_same_side_overlap"
    if n_overlap_pairs > 0:
        return "planar_patch_overlap_without_same_side_overlap"
    return "no_strict_overlap"


def capture_initial_strict_overlap_source_l1(
    *,
    fixture: str,
    repeat: int,
    audit_call_index: int,
    source_points: np.ndarray,
    source_faces: np.ndarray,
    candidate_points: np.ndarray,
    candidate_tets: np.ndarray,
    sidedness: InternalFaceSidednessAudit | None = None,
) -> InitialStrictOverlapSourceRecord:
    """Record one existing strict-audit call and source provenance facts.

    ``sidedness`` is supplied by a test wrapper when it has already called the
    original audit.  Supplying ``None`` is L0 convenience only and invokes the
    same existing audit directly.  All four input hashes must remain exact.
    """
    source = _matrix(
        source_points,
        dtype=np.dtype(np.float64),
        columns=3,
        name="source_points",
    )
    faces = _matrix(
        source_faces,
        dtype=np.dtype(np.int64),
        columns=3,
        name="source_faces",
    )
    points = _matrix(
        candidate_points,
        dtype=np.dtype(np.float64),
        columns=3,
        name="candidate_points",
    )
    tets = _matrix(
        candidate_tets,
        dtype=np.dtype(np.int64),
        columns=4,
        name="candidate_tets",
    )
    before = tuple(array_sha256(values) for values in (source, faces, points, tets))
    observed = sidedness or audit_internal_face_sidedness(points, tets)
    components = audit_source_component_bijection(source, faces, points, tets)
    after = tuple(array_sha256(values) for values in (source, faces, points, tets))
    if before != after:
        raise RuntimeError("initial-overlap diagnostic mutated audited arrays")
    return InitialStrictOverlapSourceRecord(
        schema_version=_SCHEMA_VERSION,
        fixture=str(fixture),
        repeat=int(repeat),
        audit_call_index=int(audit_call_index),
        stage="audit_internal_face_sidedness",
        source_points_sha256=before[0],
        source_faces_sha256=before[1],
        candidate_points_sha256=before[2],
        candidate_tets_sha256=before[3],
        n_internal_faces=int(observed.n_internal_faces),
        n_same_side_internal_faces=int(observed.n_same_side_internal_faces),
        n_ambiguous_internal_faces=int(observed.n_ambiguous_internal_faces),
        n_source_components=int(components.n_source_components),
        n_candidate_boundary_components=int(components.n_candidate_boundary_components),
        n_missing_source_vertices=int(components.n_missing_source_vertices),
        n_missing_source_faces=int(components.n_missing_source_faces),
        n_unowned_candidate_faces=int(components.n_unowned_candidate_faces),
        n_uncovered_source_patches=int(components.n_uncovered_source_patches),
        n_area_mismatch_patches=int(components.n_area_mismatch_patches),
        n_feature_boundary_mismatches=int(components.n_feature_boundary_mismatches),
        n_overlap_pairs=int(components.n_overlap_pairs),
        component_bijective=bool(components.bijective),
        source_faces_preserved=bool(components.source_faces_preserved),
        overlap_source_class=_classify(
            observed,
            source_faces_preserved=bool(components.source_faces_preserved),
            n_overlap_pairs=int(components.n_overlap_pairs),
        ),
    )


def first_strict_overlap_source(
    records: tuple[InitialStrictOverlapSourceRecord, ...],
) -> InitialStrictOverlapSourceRecord | None:
    """Return first observed same-side debt; ambiguity remains a separate class."""
    return next(
        (
            record
            for record in records
            if record.n_same_side_internal_faces > 0
        ),
        None,
    )


__all__ = [
    "InitialStrictOverlapSourceRecord",
    "array_sha256",
    "capture_initial_strict_overlap_source_l1",
    "first_strict_overlap_source",
]
