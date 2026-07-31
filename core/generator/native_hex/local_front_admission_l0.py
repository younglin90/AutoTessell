"""Default-OFF admission proof for a report-only native-hex local front.

Python owns source identity, entity provenance, and exact quadization.  The
optional C++23 function verifies only the numeric row multiplicity and
clearance facts already derived by this oracle.  This module never constructs
a shell, writes a mesh, or selects a production route.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path

import numpy as np

from .source_feature_sidecar_l1 import (
    AuthoritativeSourceFeatureManifest,
    audit_authoritative_source_feature_sidecar_l1,
)
from .source_quad_feature_provenance_l1 import audit_quadized_entity_boundaries_l1
from .source_quad_inward_clearance_l0 import audit_sampled_inward_clearance_l0
from .source_triangle_quadization_l1 import audit_exact_source_quadization_l1

_ENV = "AUTO_TESSELL_HEX_LOCAL_FRONT_ADMISSION_CPP23"


@dataclass(frozen=True, slots=True)
class LocalFrontAdmissionL0:
    status: str
    admitted: bool
    source_rows_complete: bool
    clearance_sufficient: bool
    source_face_count: int
    quad_count: int
    source_geometry_unchanged: bool
    native_checked: bool


def _numeric_oracle(
    source_face_ids: np.ndarray,
    source_face_count: int,
    requested_step: float,
    minimum_clearance: float,
) -> tuple[bool, bool]:
    if (
        source_face_count <= 0
        or not np.isfinite(requested_step)
        or requested_step <= 0.0
        or not np.isfinite(minimum_clearance)
        or minimum_clearance <= 0.0
        or source_face_ids.ndim != 1
        or len(source_face_ids) != 3 * source_face_count
        or not np.issubdtype(source_face_ids.dtype, np.integer)
    ):
        return False, False
    ids = np.asarray(source_face_ids, dtype=np.int64)
    if np.any(ids < 0) or np.any(ids >= source_face_count):
        return False, False
    return bool(np.all(np.bincount(ids, minlength=source_face_count) == 3)), bool(
        minimum_clearance >= requested_step
    )


def _native_numeric_crosscheck(
    source_face_ids: np.ndarray,
    source_face_count: int,
    requested_step: float,
    minimum_clearance: float,
    expected: tuple[bool, bool],
) -> bool:
    """Return False only when opt-in native support is unavailable.

    A malformed or divergent native result is an authority failure, not a
    permission to weaken the source gate.
    """
    from . import quality

    native = quality._load_native_hex_quality()
    if native is None or not hasattr(native, "local_front_numeric_admission"):
        return False
    result = native.local_front_numeric_admission(
        np.ascontiguousarray(source_face_ids, dtype=np.int64),
        int(source_face_count),
        float(requested_step),
        float(minimum_clearance),
    )
    if not isinstance(result, dict):
        raise RuntimeError("native local-front admission returned a non-dict result")
    rows, clearance = result.get("source_rows_complete"), result.get("clearance_sufficient")
    if (
        not isinstance(rows, bool)
        or not isinstance(clearance, bool)
        or isinstance(result.get("source_face_count"), bool)
        or not isinstance(result.get("source_face_count"), Integral)
        or isinstance(result.get("quad_count"), bool)
        or not isinstance(result.get("quad_count"), Integral)
        or int(result["source_face_count"]) != source_face_count
        or int(result["quad_count"]) != len(source_face_ids)
        or (rows, clearance) != expected
    ):
        raise RuntimeError("native local-front admission disagrees with Python authority")
    return True


def audit_local_front_admission_l0(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    source_path: str | Path,
    manifest: AuthoritativeSourceFeatureManifest | None,
    requested_step: float,
) -> LocalFrontAdmissionL0:
    """Admit only an authoritative exact source-quad front; default OFF native."""
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    points_before, triangles_before = points.copy(), triangles.copy()
    unchanged = bool(
        np.array_equal(points, points_before) and np.array_equal(triangles, triangles_before)
    )
    sidecar = audit_authoritative_source_feature_sidecar_l1(
        points, triangles, source_path=source_path, manifest=manifest
    )
    if sidecar.status != "pass_authoritative_feature_sidecar" or manifest is None:
        return LocalFrontAdmissionL0(
            "reject_authoritative_source_provenance",
            False,
            False,
            False,
            len(triangles),
            0,
            unchanged,
            False,
        )
    clearance_audit = audit_sampled_inward_clearance_l0(
        points,
        triangles,
        source_path=source_path,
        manifest=manifest,
        required_clearance=float(requested_step),
    )
    if (
        clearance_audit.status != "pass_sampled_inward_clearance"
        or clearance_audit.minimum_clearance is None
    ):
        return LocalFrontAdmissionL0(
            "reject_sampled_inward_clearance",
            False,
            False,
            False,
            len(triangles),
            0,
            unchanged and clearance_audit.source_geometry_unchanged,
            False,
        )
    quad_features = audit_quadized_entity_boundaries_l1(points, triangles, manifest.face_entities)
    exact = audit_exact_source_quadization_l1(points, triangles, manifest.face_entities)
    if (
        quad_features.status != "pass_exact_quad_entity_boundary_provenance"
        or exact.status != "pass_exact_source_quadization"
    ):
        return LocalFrontAdmissionL0(
            "reject_exact_source_quad_provenance",
            False,
            False,
            False,
            len(triangles),
            0,
            unchanged,
            False,
        )
    source_ids = np.ascontiguousarray(exact.quadization.source_face_ids, dtype=np.int64)
    rows, clearance = _numeric_oracle(
        source_ids,
        len(triangles),
        float(requested_step),
        float(clearance_audit.minimum_clearance),
    )
    native_checked = False
    if os.environ.get(_ENV) == "1":
        native_checked = _native_numeric_crosscheck(
            source_ids,
            len(triangles),
            float(requested_step),
            float(clearance_audit.minimum_clearance),
            (rows, clearance),
        )
    admitted = rows and clearance
    return LocalFrontAdmissionL0(
        "pass_local_front_admission" if admitted else "reject_local_front_numeric_admission",
        admitted,
        rows,
        clearance,
        len(triangles),
        len(source_ids),
        unchanged,
        native_checked,
    )
