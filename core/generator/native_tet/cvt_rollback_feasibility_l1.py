"""Read-only CVT rollback feasibility evidence for native-Tet tests only.

The generator never imports this module.  A test subprocess supplies exact
pre-CVT and post-CVT candidate arrays already produced by the unchanged CVT
call.  The diagnostic reports strict sidedness, source provenance, and the
existing strict-boundary eligibility facts without selecting a fallback.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .initial_overlap_source_l1 import array_sha256
from .rescue_gate import audit_source_component_bijection, audit_tet_boundary

_SCHEMA_VERSION = "native_tet_cvt_rollback_feasibility_l1/v1"


@dataclass(frozen=True, slots=True)
class CvtRollbackFeasibilityRecord:
    """Immutable comparison of one unchanged CVT call's pre/post arrays."""

    schema_version: str
    fixture: str
    repeat: int
    cvt_call_index: int
    pre_points_sha256: str
    pre_tets_sha256: str
    candidate_points_sha256: str
    candidate_tets_sha256: str
    pre_same_side_internal_faces: int
    candidate_same_side_internal_faces: int
    pre_ambiguous_internal_faces: int
    candidate_ambiguous_internal_faces: int
    pre_source_faces_preserved: bool
    candidate_source_faces_preserved: bool
    pre_component_bijective: bool
    candidate_component_bijective: bool
    pre_boundary_valid: bool
    candidate_boundary_valid: bool
    pre_strict_writer_eligible: bool
    candidate_strict_writer_eligible: bool
    source_preserving_pre_cvt_candidate_exists: bool

    def as_json(self) -> dict[str, object]:
        """Return scalar-only evidence for deterministic subprocess checks."""
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


def capture_cvt_rollback_feasibility_l1(
    *,
    fixture: str,
    repeat: int,
    cvt_call_index: int,
    source_points: np.ndarray,
    source_faces: np.ndarray,
    pre_points: np.ndarray,
    pre_tets: np.ndarray,
    candidate_points: np.ndarray,
    candidate_tets: np.ndarray,
) -> CvtRollbackFeasibilityRecord:
    """Compare immutable snapshots; no result is accepted or written here."""
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
    before_points = _matrix(
        pre_points,
        dtype=np.dtype(np.float64),
        columns=3,
        name="pre_points",
    )
    before_tets = _matrix(
        pre_tets,
        dtype=np.dtype(np.int64),
        columns=4,
        name="pre_tets",
    )
    after_points = _matrix(
        candidate_points,
        dtype=np.dtype(np.float64),
        columns=3,
        name="candidate_points",
    )
    after_tets = _matrix(
        candidate_tets,
        dtype=np.dtype(np.int64),
        columns=4,
        name="candidate_tets",
    )
    arrays = (source, faces, before_points, before_tets, after_points, after_tets)
    hashes_before = tuple(array_sha256(values) for values in arrays)
    before_sidedness = audit_tet_boundary(before_points, before_tets)
    candidate_sidedness = audit_tet_boundary(after_points, after_tets)
    before_source = audit_source_component_bijection(
        source, faces, before_points, before_tets
    )
    candidate_source = audit_source_component_bijection(
        source, faces, after_points, after_tets
    )
    hashes_after = tuple(array_sha256(values) for values in arrays)
    if hashes_before != hashes_after:
        raise RuntimeError("CVT rollback feasibility diagnostic mutated audited arrays")

    pre_eligible = bool(
        before_sidedness.valid
        and before_source.bijective
        and before_source.source_faces_preserved
    )
    candidate_eligible = bool(
        candidate_sidedness.valid
        and candidate_source.bijective
        and candidate_source.source_faces_preserved
    )
    return CvtRollbackFeasibilityRecord(
        schema_version=_SCHEMA_VERSION,
        fixture=str(fixture),
        repeat=int(repeat),
        cvt_call_index=int(cvt_call_index),
        pre_points_sha256=hashes_before[2],
        pre_tets_sha256=hashes_before[3],
        candidate_points_sha256=hashes_before[4],
        candidate_tets_sha256=hashes_before[5],
        pre_same_side_internal_faces=int(before_sidedness.n_same_side_internal_faces),
        candidate_same_side_internal_faces=int(
            candidate_sidedness.n_same_side_internal_faces
        ),
        pre_ambiguous_internal_faces=int(before_sidedness.n_ambiguous_internal_faces),
        candidate_ambiguous_internal_faces=int(
            candidate_sidedness.n_ambiguous_internal_faces
        ),
        pre_source_faces_preserved=bool(before_source.source_faces_preserved),
        candidate_source_faces_preserved=bool(candidate_source.source_faces_preserved),
        pre_component_bijective=bool(before_source.bijective),
        candidate_component_bijective=bool(candidate_source.bijective),
        pre_boundary_valid=bool(before_sidedness.valid),
        candidate_boundary_valid=bool(candidate_sidedness.valid),
        pre_strict_writer_eligible=pre_eligible,
        candidate_strict_writer_eligible=candidate_eligible,
        source_preserving_pre_cvt_candidate_exists=pre_eligible,
    )


__all__ = ["CvtRollbackFeasibilityRecord", "capture_cvt_rollback_feasibility_l1"]
