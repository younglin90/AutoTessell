"""Default-off exact identity contract for output-boundary to B-Rep ordinals.

This report-only adapter accepts only an exact source-triangle identity witness.
It does not represent current native-Hex quad output or authorize any product.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha256

import numpy as np

from core.analyzer.readers.step_snapshot_provenance_l0 import (
    CadSnapshotProvenanceL0,
    canonical_cad_reader_payload_sha256,
)

_ENV = "AUTO_TESSELL_HEX_OUTPUT_BREP_ORDINAL_BINDING_L0"
_MISSING = ("physical_group", "nontrivial_hex_boundary_to_brep_surface_witness")


@dataclass(frozen=True, slots=True)
class HexOutputBrepOrdinalBindingL0:
    status: str
    enabled: bool
    source_snapshot_valid: bool
    output_mapping_complete: bool
    output_boundary_face_count: int
    output_geometry_sha256: str | None
    output_orientation_sha256: str | None
    output_ordinal_sha256: str | None
    physical_groups_authoritative: bool
    missing_evidence: tuple[str, ...]
    malformed_evidence: tuple[str, ...]
    accepted: bool
    candidate_constructed: bool
    production_mesh_changed: bool
    artifact_delta: int
    product_claimed: bool
    rejection_reason: str
    contract: str = "native_hex_output_brep_ordinal_binding_l0"


def _enabled() -> bool:
    return os.environ.get(_ENV) == "1"


def _array(
    value: object, dtype: np.dtype[object], shape: tuple[int | None, ...]
) -> np.ndarray | None:
    if not isinstance(value, np.ndarray) or value.dtype != dtype or value.ndim != len(shape):
        return None
    if not value.flags.c_contiguous or value.flags.writeable:
        return None
    if any(
        expected is not None and actual != expected for actual, expected in zip(value.shape, shape)
    ):
        return None
    return value


def _hash(value: np.ndarray | None) -> str | None:
    if value is None:
        return None
    digest = sha256()
    digest.update(value.dtype.str.encode())
    digest.update(np.asarray(value.shape, dtype=">i8").tobytes())
    digest.update(memoryview(value).cast("B"))
    return digest.hexdigest()


def _report(
    status: str,
    enabled: bool,
    *,
    source: bool = False,
    complete: bool = False,
    count: int = 0,
    geometry: np.ndarray | None = None,
    faces: np.ndarray | None = None,
    ordinals: np.ndarray | None = None,
    malformed: tuple[str, ...] = (),
) -> HexOutputBrepOrdinalBindingL0:
    return HexOutputBrepOrdinalBindingL0(
        status,
        enabled,
        source,
        complete,
        count,
        _hash(geometry),
        _hash(faces),
        _hash(ordinals),
        False,
        _MISSING,
        malformed,
        False,
        False,
        False,
        0,
        False,
        "hex_output_brep_product_certificate_required",
    )


def diagnose_hex_output_brep_ordinal_binding_l0(
    source_snapshot: object,
    output_boundary_vertices: object,
    output_boundary_face_ids: object,
    output_boundary_faces: object,
    output_vertex_to_source_canonical_ids: object,
    output_face_to_source_triangle_indices: object,
    output_face_to_source_brep_ordinals: object,
) -> HexOutputBrepOrdinalBindingL0:
    """Require exact source-triangle geometry, winding, and B-Rep ordinal identity."""
    if not _enabled():
        return _report("disabled_hex_output_brep_ordinal_binding_l0", False)
    if not isinstance(source_snapshot, CadSnapshotProvenanceL0):
        return _report("reject_invalid_source_snapshot", True, malformed=("source_snapshot",))
    if (
        source_snapshot.status != "report_snapshot_reader_provenance_unverified"
        or source_snapshot.triangulation is None
        or not source_snapshot.source_digest_matches
        or not source_snapshot.reader_payload_matches
        or source_snapshot.physical_groups_authoritative
    ):
        return _report("reject_source_snapshot_unverified", True, malformed=("source_snapshot",))
    try:
        if source_snapshot.reader_payload_sha256 != canonical_cad_reader_payload_sha256(
            source_snapshot.triangulation
        ):
            return _report(
                "reject_source_snapshot_payload_mismatch", True, malformed=("source_snapshot",)
            )
    except ValueError:
        return _report(
            "reject_source_snapshot_payload_mismatch", True, malformed=("source_snapshot",)
        )
    source = source_snapshot.triangulation
    provenance = source.provenance
    vertices = _array(output_boundary_vertices, np.dtype(np.float64), (None, 3))
    ids = _array(output_boundary_face_ids, np.dtype(np.int64), (None,))
    faces = _array(output_boundary_faces, np.dtype(np.int64), (None, 3))
    vertex_map = _array(output_vertex_to_source_canonical_ids, np.dtype(np.int64), (None,))
    triangles = _array(output_face_to_source_triangle_indices, np.dtype(np.int64), (None,))
    ordinals = _array(output_face_to_source_brep_ordinals, np.dtype(np.int64), (None,))
    if any(value is None for value in (vertices, ids, faces, vertex_map, triangles, ordinals)):
        return _report(
            "reject_output_brep_binding_malformed", True, source=True, malformed=("output_arrays",)
        )
    assert vertices is not None and ids is not None and faces is not None
    assert vertex_map is not None and triangles is not None and ordinals is not None
    if (
        not len(ids)
        or len(faces) != len(ids)
        or len(triangles) != len(ids)
        or len(ordinals) != len(ids)
        or len(vertex_map) != len(vertices)
        or not np.isfinite(vertices).all()
        or (ids < 0).any()
        or np.any(ids[1:] <= ids[:-1])
        or (vertex_map < 0).any()
        or (vertex_map >= len(provenance.canonical_vertex_source_ids)).any()
        or (faces < 0).any()
        or (faces >= len(vertices)).any()
        or (triangles < 0).any()
        or (triangles >= len(source.faces)).any()
        or (ordinals < 0).any()
        or (ordinals >= provenance.face_count).any()
    ):
        return _report(
            "reject_output_brep_binding_malformed", True, source=True, malformed=("output_mapping",)
        )
    if len(np.unique(vertex_map)) != len(vertex_map) or not np.array_equal(
        vertex_map, np.arange(len(vertex_map))
    ):
        return _report(
            "reject_output_brep_binding_ambiguous", True, source=True, malformed=("vertex_mapping",)
        )
    canonical_sources = provenance.canonical_vertex_source_ids[vertex_map]
    if not np.array_equal(vertices, source.vertices[canonical_sources]):
        return _report(
            "reject_output_brep_binding_moved", True, source=True, malformed=("output_geometry",)
        )
    if len(np.unique(triangles)) != len(triangles) or not np.array_equal(
        np.sort(triangles), np.arange(len(source.faces))
    ):
        return _report(
            "reject_output_brep_binding_ambiguous",
            True,
            source=True,
            malformed=("triangle_mapping",),
        )
    expected_faces = provenance.oriented_canonical_faces[triangles]
    expected_ordinals = provenance.triangle_face_ordinals[triangles]
    if not np.array_equal(faces, expected_faces):
        return _report(
            "reject_output_brep_binding_reversed_or_moved",
            True,
            source=True,
            malformed=("output_orientation",),
        )
    if not np.array_equal(ordinals, expected_ordinals):
        return _report(
            "reject_output_brep_binding_wrong_ordinal",
            True,
            source=True,
            malformed=("brep_ordinal",),
        )
    return _report(
        "report_hex_output_brep_ordinal_identity_unverified",
        True,
        source=True,
        complete=True,
        count=len(ids),
        geometry=vertices,
        faces=faces,
        ordinals=ordinals,
    )
