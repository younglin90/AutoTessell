"""Read-only L1 evidence records for native-tet ambiguity classes.

The generator never imports this module.  Tests call it at already-existing
``check_boundary_invariant`` hooks to capture the *after* arrays without
changing a candidate, transaction, writer decision, or topology policy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any

import numpy as np

from core.generator.native_tet.rescue_gate import (
    audit_internal_face_sidedness,
    audit_tet_boundary,
)

_SCHEMA_VERSION = "native_tet_ambiguity_stage_ledger_l1/v1"


@dataclass(frozen=True)
class StageAmbiguityRecord:
    """Immutable diagnostic snapshot; it is not an acceptance certificate."""

    schema_version: str
    fixture: str
    repeat: int
    stage_index: int
    stage: str
    points_sha256: str
    tets_sha256: str
    n_points: int
    n_tets: int
    n_internal_faces: int
    n_same_side_internal_faces: int
    n_ambiguous_internal_faces: int
    n_predicate_zero_internal_faces: int
    n_floor_only_same_side_internal_faces: int
    n_floor_only_opposite_side_internal_faces: int
    partition_conserved: bool
    n_duplicate_tets: int
    n_nonmanifold_faces: int
    n_degenerate_tets: int
    n_inverted_tets: int
    audit_valid: bool
    result_success: bool | None = None
    result_message: str | None = None
    writer_artifact_exists: bool | None = None
    source_certificate_sha256: str | None = None

    def as_json(self) -> dict[str, object]:
        """Return only JSON scalar data, with field order owned by the schema."""
        return asdict(self)


def _require_matrix(array: np.ndarray, *, dtype: np.dtype[Any], name: str) -> np.ndarray:
    if not isinstance(array, np.ndarray):
        raise TypeError(f"{name} must be an ndarray")
    if array.dtype != dtype or array.ndim != 2:
        raise TypeError(f"{name} must be a two-dimensional {dtype} ndarray")
    if not array.flags.c_contiguous:
        raise ValueError(f"{name} must be C-contiguous")
    return array


def array_sha256(array: np.ndarray) -> str:
    """Hash dtype, shape, and exact C-order bytes without mutating ``array``."""
    if not isinstance(array, np.ndarray) or not array.flags.c_contiguous:
        raise ValueError("array_sha256 requires a C-contiguous ndarray")
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(b"\0")
    digest.update(repr(tuple(int(size) for size in array.shape)).encode("ascii"))
    digest.update(b"\0")
    digest.update(memoryview(array).cast("B"))
    return digest.hexdigest()


def json_sha256(value: Mapping[str, Any]) -> str:
    """Hash a canonical source-certificate mapping for repeat comparison only."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def capture_after_stage(
    *,
    fixture: str,
    repeat: int,
    stage_index: int,
    stage: str,
    points: np.ndarray,
    tets: np.ndarray,
) -> StageAmbiguityRecord:
    """Measure the existing audit categories on a hook's after-arrays only."""
    points = _require_matrix(points, dtype=np.dtype(np.float64), name="points")
    tets = _require_matrix(tets, dtype=np.dtype(np.int64), name="tets")
    if points.shape[1] != 3 or tets.shape[1] != 4:
        raise ValueError("points must be (N, 3) and tets must be (M, 4)")
    sidedness = audit_internal_face_sidedness(points, tets)
    topology = audit_tet_boundary(points, tets)
    partition_conserved = bool(
        sidedness.n_ambiguous_internal_faces
        == sidedness.n_predicate_zero_internal_faces
        + sidedness.n_floor_only_same_side_internal_faces
        + sidedness.n_floor_only_opposite_side_internal_faces
    )
    return StageAmbiguityRecord(
        schema_version=_SCHEMA_VERSION,
        fixture=str(fixture),
        repeat=int(repeat),
        stage_index=int(stage_index),
        stage=str(stage),
        points_sha256=array_sha256(points),
        tets_sha256=array_sha256(tets),
        n_points=int(points.shape[0]),
        n_tets=int(tets.shape[0]),
        n_internal_faces=int(sidedness.n_internal_faces),
        n_same_side_internal_faces=int(sidedness.n_same_side_internal_faces),
        n_ambiguous_internal_faces=int(sidedness.n_ambiguous_internal_faces),
        n_predicate_zero_internal_faces=int(sidedness.n_predicate_zero_internal_faces),
        n_floor_only_same_side_internal_faces=int(sidedness.n_floor_only_same_side_internal_faces),
        n_floor_only_opposite_side_internal_faces=int(
            sidedness.n_floor_only_opposite_side_internal_faces
        ),
        partition_conserved=partition_conserved,
        n_duplicate_tets=int(topology.n_duplicate_tets),
        n_nonmanifold_faces=int(topology.n_nonmanifold_faces),
        n_degenerate_tets=int(topology.n_degenerate_tets),
        n_inverted_tets=int(topology.n_inverted_tets),
        audit_valid=bool(topology.valid),
    )


def with_result_context(
    record: StageAmbiguityRecord,
    *,
    result_success: bool,
    result_message: str,
    writer_artifact_exists: bool,
    source_certificate: Mapping[str, Any],
) -> StageAmbiguityRecord:
    """Attach post-run context without changing the captured stage evidence."""
    return replace(
        record,
        result_success=bool(result_success),
        result_message=str(result_message),
        writer_artifact_exists=bool(writer_artifact_exists),
        source_certificate_sha256=json_sha256(source_certificate),
    )
