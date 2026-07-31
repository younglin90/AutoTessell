"""Fail-closed, report-only audit for an already-read CAD/B-Rep front payload.

This adapter deliberately does not read CAD bytes or invoke the OCP reader.
It validates only a caller-supplied immutable ``CadNativeTriangulation`` after
the declaration envelope has established an explicit CAD/B-Rep authority kind.
No report from this module is product acceptance evidence.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256

import numpy as np

from core.analyzer.readers.step import CadEntityProvenance, CadNativeTriangulation

_ENABLE_ENV = "AUTO_TESSELL_HEX_BREP_SOURCE_FRONT_AUTHORITY_L0"
_MISSING_EVIDENCE = (
    "source_bytes_to_reader_payload",
    "output_boundary_face_to_source_brep",
    "physical_group",
)


@dataclass(frozen=True, slots=True)
class HexBrepSourceFrontAuthorityDeclarationL0:
    """Caller-owned declaration for one already-read, immutable CAD input."""

    authority_kind: str
    authority_key: str
    source_file_sha256: str
    triangulation: CadNativeTriangulation


@dataclass(frozen=True, slots=True)
class HexBrepSourceFrontAuthorityAuditL0:
    """Fixed-shape audit; it can never authorize a Hex product claim."""

    status: str
    enabled: bool
    authority_kind: str | None
    authority_key: str | None
    source_file_digest_declared: bool
    input_brep_payload_valid: bool
    source_bytes_to_reader_payload_bound: bool
    source_face_count: int
    triangle_count: int
    missing_evidence: tuple[str, ...]
    malformed_evidence: tuple[str, ...]
    reader_invoked: bool
    candidate_constructed: bool
    production_mesh_changed: bool
    artifact_delta: int
    accepted: bool
    mesher_success_allowed: bool
    product_claimed: bool
    rejection_reason: str
    contract: str = "native_hex_brep_source_front_authority_l0"


def hex_brep_source_front_authority_l0_enabled() -> bool:
    """Return true only for the explicit opt-in; unset and other values are off."""
    return os.environ.get(_ENABLE_ENV) == "1"


def _canonical_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _readonly_array(
    value: object,
    *,
    dtype: np.dtype[object],
    shape: tuple[int | None, ...],
    readonly: bool = True,
) -> np.ndarray | None:
    if not isinstance(value, np.ndarray) or value.dtype != dtype or value.ndim != len(shape):
        return None
    if not value.flags.c_contiguous or (readonly and value.flags.writeable):
        return None
    if any(
        expected is not None and actual != expected
        for actual, expected in zip(value.shape, shape)
    ):
        return None
    return value


def _array_sha256(value: np.ndarray, dtype: str) -> str:
    return sha256(np.ascontiguousarray(value, dtype=dtype).tobytes()).hexdigest()


def _valid_face_metadata(provenance: CadEntityProvenance) -> bool:
    count = provenance.face_count
    if not isinstance(provenance.face_names, tuple) or len(provenance.face_names) != count:
        return False
    if not all(
        name is None or (isinstance(name, str) and name.strip())
        for name in provenance.face_names
    ):
        return False
    if (
        not isinstance(provenance.xde_layer_names, tuple)
        or len(provenance.xde_layer_names) != count
    ):
        return False
    if not all(
        isinstance(names, tuple)
        and all(isinstance(name, str) and name.strip() for name in names)
        and tuple(sorted(names)) == names
        for names in provenance.xde_layer_names
    ):
        return False
    if (
        not isinstance(provenance.xde_surface_colors, tuple)
        or len(provenance.xde_surface_colors) != count
    ):
        return False
    if not all(
        color is None
        or (
            isinstance(color, tuple)
            and len(color) == 3
            and all(isinstance(component, float) and np.isfinite(component) for component in color)
        )
        for color in provenance.xde_surface_colors
    ):
        return False
    if (
        not isinstance(provenance.xde_assembly_paths, tuple)
        or len(provenance.xde_assembly_paths) != count
    ):
        return False
    if not all(
        path is None
        or (
            isinstance(path, tuple)
            and path
            and all(isinstance(part, str) and part.strip() for part in path)
        )
        for path in provenance.xde_assembly_paths
    ):
        return False
    flags = (
        provenance.xde_layer_authoritative,
        provenance.xde_color_display_metadata_authoritative,
        provenance.xde_assembly_identity_authoritative,
    )
    return (
        all(isinstance(flag, bool) for flag in flags)
        and isinstance(provenance.xde_layer_coverage_count, int)
        and not isinstance(provenance.xde_layer_coverage_count, bool)
        and provenance.xde_layer_coverage_count
        == sum(bool(names) for names in provenance.xde_layer_names)
    )


def _valid_xde_hash(provenance: CadEntityProvenance) -> bool:
    payload = {
        "face_names": provenance.face_names,
        "layer_names": provenance.xde_layer_names,
        "surface_colors": provenance.xde_surface_colors,
        "assembly_paths": provenance.xde_assembly_paths,
        "layer_authoritative": provenance.xde_layer_authoritative,
        "physical_group_authoritative": False,
    }
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return provenance.xde_metadata_sha256 == digest


def _valid_provenance(
    triangulation: CadNativeTriangulation,
) -> tuple[bool, int, int, tuple[str, ...]]:
    vertices = _readonly_array(
        triangulation.vertices,
        dtype=np.dtype(np.float64),
        shape=(None, 3),
        readonly=False,
    )
    faces = _readonly_array(
        triangulation.faces,
        dtype=np.dtype(np.int64),
        shape=(None, 3),
        readonly=False,
    )
    provenance = triangulation.provenance
    if (
        vertices is None
        or faces is None
        or len(vertices) == 0
        or len(faces) == 0
        or not np.isfinite(vertices).all()
        or (faces < 0).any()
        or (faces >= len(vertices)).any()
        or np.any(faces[:, 0] == faces[:, 1])
        or np.any(faces[:, 1] == faces[:, 2])
        or np.any(faces[:, 0] == faces[:, 2])
        or not isinstance(provenance, CadEntityProvenance)
    ):
        return False, 0, 0, ("triangulation",)
    if (
        provenance.status != "partial_authority_physical_groups_unavailable"
        or not isinstance(provenance.face_count, int)
        or isinstance(provenance.face_count, bool)
        or not isinstance(provenance.topological_edge_count, int)
        or isinstance(provenance.topological_edge_count, bool)
        or provenance.face_count <= 0
        or provenance.topological_edge_count <= 0
    ):
        return False, 0, 0, ("provenance_header",)
    if (
        provenance.face_ordinals_authoritative is not True
        or provenance.face_orientation_authoritative is not True
        or provenance.seam_connectivity_authoritative is not True
    ):
        return False, 0, 0, ("brep_authority_flags",)
    if (
        provenance.physical_groups_authoritative is not False
        or not isinstance(provenance.physical_group_names, tuple)
        or len(provenance.physical_group_names) != provenance.face_count
        or any(name is not None for name in provenance.physical_group_names)
    ):
        return False, 0, 0, ("physical_groups",)
    ordinals = _readonly_array(
        provenance.triangle_face_ordinals, dtype=np.dtype(np.int64), shape=(len(faces),)
    )
    orientation = _readonly_array(
        provenance.triangle_orientation_reversed, dtype=np.dtype(np.bool_), shape=(len(faces),)
    )
    seams = _readonly_array(
        provenance.seam_vertex_ids, dtype=np.dtype(np.int64), shape=(len(vertices),)
    )
    canonical_sources = _readonly_array(
        provenance.canonical_vertex_source_ids, dtype=np.dtype(np.int64), shape=(None,)
    )
    canonical_faces = _readonly_array(
        provenance.oriented_canonical_faces, dtype=np.dtype(np.int64), shape=(len(faces), 3)
    )
    if any(
        value is None
        for value in (ordinals, orientation, seams, canonical_sources, canonical_faces)
    ):
        return False, 0, 0, ("provenance_arrays",)
    assert ordinals is not None and orientation is not None and seams is not None
    assert canonical_sources is not None and canonical_faces is not None
    if (
        (ordinals < 0).any()
        or (ordinals >= provenance.face_count).any()
        or len(np.unique(ordinals)) != provenance.face_count
        or (seams < 0).any()
        or len(canonical_sources) == 0
        or (seams >= len(canonical_sources)).any()
        or (canonical_sources < 0).any()
        or (canonical_sources >= len(vertices)).any()
        or not np.array_equal(
            seams[canonical_sources],
            np.arange(len(canonical_sources), dtype=np.int64),
        )
        or not np.array_equal(
            canonical_sources,
            np.asarray(
                [np.flatnonzero(seams == value)[0] for value in range(len(canonical_sources))],
                dtype=np.int64,
            ),
        )
    ):
        return False, 0, 0, ("provenance_coverage",)
    oriented_faces = faces.copy()
    oriented_faces[orientation] = oriented_faces[orientation][:, (0, 2, 1)]
    if not np.array_equal(canonical_faces, seams[oriented_faces]):
        return False, 0, 0, ("oriented_canonical_faces",)
    hashes = (
        provenance.ordered_triangle_coordinate_sha256,
        provenance.ordered_face_ordinal_sha256,
        provenance.ordered_orientation_sha256,
        provenance.seam_connectivity_sha256,
        provenance.xde_metadata_sha256,
    )
    if not all(_canonical_sha256(value) for value in hashes):
        return False, 0, 0, ("provenance_hashes",)
    if (
        provenance.ordered_triangle_coordinate_sha256 != _array_sha256(vertices[faces], "<f8")
        or provenance.ordered_face_ordinal_sha256 != _array_sha256(ordinals, "<i8")
        or provenance.ordered_orientation_sha256 != _array_sha256(orientation, "u1")
        or provenance.seam_connectivity_sha256 != _array_sha256(canonical_faces, "<i8")
        or not _valid_face_metadata(provenance)
        or not _valid_xde_hash(provenance)
    ):
        return False, 0, 0, ("provenance_hashes",)
    return True, provenance.face_count, len(faces), ()


def _report(
    *,
    status: str,
    enabled: bool,
    declaration: HexBrepSourceFrontAuthorityDeclarationL0 | None,
    source_digest_declared: bool,
    payload_valid: bool,
    face_count: int = 0,
    triangle_count: int = 0,
    malformed: tuple[str, ...] = (),
) -> HexBrepSourceFrontAuthorityAuditL0:
    return HexBrepSourceFrontAuthorityAuditL0(
        status=status,
        enabled=enabled,
        authority_kind=declaration.authority_kind if declaration is not None else None,
        authority_key=declaration.authority_key if declaration is not None else None,
        source_file_digest_declared=source_digest_declared,
        input_brep_payload_valid=payload_valid,
        source_bytes_to_reader_payload_bound=False,
        source_face_count=face_count,
        triangle_count=triangle_count,
        missing_evidence=_MISSING_EVIDENCE,
        malformed_evidence=malformed,
        reader_invoked=False,
        candidate_constructed=False,
        production_mesh_changed=False,
        artifact_delta=0,
        accepted=False,
        mesher_success_allowed=False,
        product_claimed=False,
        rejection_reason="hex_brep_source_front_product_certificate_required",
    )


def diagnose_hex_brep_source_front_authority_l0(
    declaration: object,
) -> HexBrepSourceFrontAuthorityAuditL0:
    """Audit an immutable, caller-supplied B-Rep front without reading CAD.

    The envelope is checked before touching its triangulation payload.  Even a
    syntactically complete payload is only an input-side report: the source
    file bytes, reader payload, and generated Hex boundary remain unbound.
    """
    if not hex_brep_source_front_authority_l0_enabled():
        return _report(
            status="disabled_hex_brep_source_front_authority_l0",
            enabled=False,
            declaration=None,
            source_digest_declared=False,
            payload_valid=False,
        )
    if not isinstance(declaration, HexBrepSourceFrontAuthorityDeclarationL0):
        return _report(
            status="reject_invalid_brep_source_front_declaration",
            enabled=True,
            declaration=None,
            source_digest_declared=False,
            payload_valid=False,
            malformed=("declaration",),
        )
    if declaration.authority_kind != "cad_brep":
        return _report(
            status="reject_unknown_brep_source_authority_kind",
            enabled=True,
            declaration=declaration,
            source_digest_declared=False,
            payload_valid=False,
            malformed=("authority_kind",),
        )
    if (
        not isinstance(declaration.authority_key, str)
        or not declaration.authority_key.strip()
        or declaration.authority_key != declaration.authority_key.strip()
        or not _canonical_sha256(declaration.source_file_sha256)
    ):
        return _report(
            status="reject_malformed_brep_source_authority_declaration",
            enabled=True,
            declaration=declaration,
            source_digest_declared=False,
            payload_valid=False,
            malformed=("authority_key_or_source_digest",),
        )
    if not isinstance(declaration.triangulation, CadNativeTriangulation):
        return _report(
            status="reject_invalid_brep_source_front_payload",
            enabled=True,
            declaration=declaration,
            source_digest_declared=True,
            payload_valid=False,
            malformed=("triangulation",),
        )
    valid, face_count, triangle_count, malformed = _valid_provenance(declaration.triangulation)
    if not valid:
        return _report(
            status="reject_malformed_brep_source_front_payload",
            enabled=True,
            declaration=declaration,
            source_digest_declared=True,
            payload_valid=False,
            malformed=malformed,
        )
    return _report(
        status="report_brep_source_front_authority_unverified",
        enabled=True,
        declaration=declaration,
        source_digest_declared=True,
        payload_valid=True,
        face_count=face_count,
        triangle_count=triangle_count,
    )
