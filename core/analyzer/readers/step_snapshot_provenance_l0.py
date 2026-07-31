"""Explicit, default-off CAD snapshot provenance transaction.

The legacy CAD reader and production route remain unchanged.  This adapter
streams a private snapshot and gives only that pathname to the provenance
reader, so the parser cannot re-open a mutable caller pathname.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

import numpy as np

from .step import CadEntityProvenance, CadNativeTriangulation, load_cad_native_with_provenance

_ENABLE_ENV = "AUTO_TESSELL_CAD_PROVENANCE_SNAPSHOT_L0"
_CHUNK_BYTES = 1024 * 1024
_FORMATS = frozenset({"step", "stp", "iges", "igs", "brep"})


@dataclass(frozen=True, slots=True)
class CadSnapshotProvenanceL0:
    """Non-accepting result.  The optional payload is never routed or emitted."""

    status: str
    enabled: bool
    source_snapshot_sha256: str | None
    source_snapshot_bytes: int
    reader_payload_sha256: str | None
    source_digest_matches: bool
    reader_payload_matches: bool
    reader_invoked: bool
    snapshot_reader_received: bool
    snapshot_removed: bool
    provenance_payload_valid: bool
    physical_groups_authoritative: bool
    malformed_evidence: tuple[str, ...]
    candidate_constructed: bool
    production_mesh_changed: bool
    artifact_delta: int
    accepted: bool
    mesher_success_allowed: bool
    product_claimed: bool
    rejection_reason: str
    triangulation: CadNativeTriangulation | None = None
    contract: str = "cad_provenance_snapshot_l0"


def cad_provenance_snapshot_l0_enabled() -> bool:
    """Only exact explicit opt-in enables snapshot creation or reader calls."""
    return os.environ.get(_ENABLE_ENV) == "1"


def _canonical_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _report(
    status: str,
    enabled: bool,
    *,
    source_hash: str | None = None,
    source_bytes: int = 0,
    payload_hash: str | None = None,
    source_matches: bool = False,
    payload_matches: bool = False,
    reader_invoked: bool = False,
    snapshot_received: bool = False,
    payload_valid: bool = False,
    physical: bool = False,
    malformed: tuple[str, ...] = (),
    triangulation: CadNativeTriangulation | None = None,
) -> CadSnapshotProvenanceL0:
    return CadSnapshotProvenanceL0(
        status,
        enabled,
        source_hash,
        source_bytes,
        payload_hash,
        source_matches,
        payload_matches,
        reader_invoked,
        snapshot_received,
        False,
        payload_valid,
        physical,
        malformed,
        False,
        False,
        0,
        False,
        False,
        False,
        "cad_snapshot_provenance_product_certificate_required",
        triangulation,
    )


def _array(
    value: object, dtype: np.dtype[object], shape: tuple[int | None, ...], *, readonly: bool = True
) -> np.ndarray | None:
    if not isinstance(value, np.ndarray) or value.dtype != dtype or value.ndim != len(shape):
        return None
    if not value.flags.c_contiguous or (readonly and value.flags.writeable):
        return None
    if any(
        expected is not None and actual != expected for actual, expected in zip(value.shape, shape)
    ):
        return None
    return value


def _array_hash(value: np.ndarray, dtype: str) -> str:
    return sha256(np.ascontiguousarray(value, dtype=dtype).tobytes()).hexdigest()


def _metadata_hash(provenance: CadEntityProvenance) -> str:
    value = {
        "face_names": provenance.face_names,
        "layer_names": provenance.xde_layer_names,
        "surface_colors": provenance.xde_surface_colors,
        "assembly_paths": provenance.xde_assembly_paths,
        "layer_authoritative": provenance.xde_layer_authoritative,
        "physical_group_authoritative": False,
    }
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate(value: object) -> tuple[CadNativeTriangulation | None, tuple[str, ...]]:
    if not isinstance(value, CadNativeTriangulation) or not isinstance(
        value.provenance, CadEntityProvenance
    ):
        return None, ("triangulation",)
    vertices = _array(value.vertices, np.dtype(np.float64), (None, 3), readonly=False)
    faces = _array(value.faces, np.dtype(np.int64), (None, 3), readonly=False)
    provenance = value.provenance
    if (
        vertices is None
        or faces is None
        or not len(vertices)
        or not len(faces)
        or not np.isfinite(vertices).all()
        or (faces < 0).any()
        or (faces >= len(vertices)).any()
        or np.any(faces[:, 0] == faces[:, 1])
        or np.any(faces[:, 1] == faces[:, 2])
        or np.any(faces[:, 0] == faces[:, 2])
    ):
        return None, ("triangulation",)
    if (
        provenance.status != "partial_authority_physical_groups_unavailable"
        or not isinstance(provenance.face_count, int)
        or isinstance(provenance.face_count, bool)
        or not isinstance(provenance.topological_edge_count, int)
        or isinstance(provenance.topological_edge_count, bool)
        or provenance.face_count <= 0
        or provenance.topological_edge_count <= 0
        or provenance.face_ordinals_authoritative is not True
        or provenance.face_orientation_authoritative is not True
        or provenance.seam_connectivity_authoritative is not True
    ):
        return None, ("brep_authority",)
    if (
        provenance.physical_groups_authoritative is not False
        or not isinstance(provenance.physical_group_names, tuple)
        or len(provenance.physical_group_names) != provenance.face_count
        or any(name is not None for name in provenance.physical_group_names)
    ):
        return None, ("physical_groups",)
    ordinals = _array(provenance.triangle_face_ordinals, np.dtype(np.int64), (len(faces),))
    orientation = _array(
        provenance.triangle_orientation_reversed, np.dtype(np.bool_), (len(faces),)
    )
    seams = _array(provenance.seam_vertex_ids, np.dtype(np.int64), (len(vertices),))
    sources = _array(provenance.canonical_vertex_source_ids, np.dtype(np.int64), (None,))
    canonical_faces = _array(
        provenance.oriented_canonical_faces, np.dtype(np.int64), (len(faces), 3)
    )
    if any(item is None for item in (ordinals, orientation, seams, sources, canonical_faces)):
        return None, ("provenance_arrays",)
    assert ordinals is not None and orientation is not None and seams is not None
    assert sources is not None and canonical_faces is not None
    if (
        (ordinals < 0).any()
        or (ordinals >= provenance.face_count).any()
        or len(np.unique(ordinals)) != provenance.face_count
        or not len(sources)
        or (seams < 0).any()
        or (seams >= len(sources)).any()
        or (sources < 0).any()
        or (sources >= len(vertices)).any()
        or not np.array_equal(seams[sources], np.arange(len(sources), dtype=np.int64))
    ):
        return None, ("provenance_coverage",)
    first_sources = np.asarray([np.flatnonzero(seams == index)[0] for index in range(len(sources))])
    if not np.array_equal(sources, first_sources):
        return None, ("provenance_coverage",)
    oriented = faces.copy()
    oriented[orientation] = oriented[orientation][:, (0, 2, 1)]
    if not np.array_equal(canonical_faces, seams[oriented]):
        return None, ("oriented_canonical_faces",)
    hashes = (
        provenance.ordered_triangle_coordinate_sha256,
        provenance.ordered_face_ordinal_sha256,
        provenance.ordered_orientation_sha256,
        provenance.seam_connectivity_sha256,
        provenance.xde_metadata_sha256,
    )
    if not all(_canonical_sha256(item) for item in hashes):
        return None, ("provenance_hashes",)
    if (
        provenance.ordered_triangle_coordinate_sha256 != _array_hash(vertices[faces], "<f8")
        or provenance.ordered_face_ordinal_sha256 != _array_hash(ordinals, "<i8")
        or provenance.ordered_orientation_sha256 != _array_hash(orientation, "u1")
        or provenance.seam_connectivity_sha256 != _array_hash(canonical_faces, "<i8")
        or provenance.xde_metadata_sha256 != _metadata_hash(provenance)
    ):
        return None, ("provenance_hashes",)
    return value, ()


def _update(digest: object, value: bytes | memoryview) -> None:
    digest.update(len(value).to_bytes(8, "big"))  # type: ignore[attr-defined]
    digest.update(value)  # type: ignore[attr-defined]


def _update_array(digest: object, label: str, value: np.ndarray) -> None:
    _update(digest, label.encode())
    _update(digest, value.dtype.str.encode())
    _update(digest, np.asarray(value.shape, dtype=">i8").tobytes())
    raw = memoryview(value).cast("B")
    for offset in range(0, len(raw), _CHUNK_BYTES):
        _update(digest, raw[offset : offset + _CHUNK_BYTES])


def canonical_cad_reader_payload_sha256(triangulation: CadNativeTriangulation) -> str:
    """Versioned payload digest; array bytes are streamed by memoryview."""
    valid, malformed = _validate(triangulation)
    if valid is None:
        raise ValueError(f"invalid CAD provenance payload: {','.join(malformed)}")
    provenance = valid.provenance
    array_fields = {
        "triangle_face_ordinals",
        "triangle_orientation_reversed",
        "seam_vertex_ids",
        "canonical_vertex_source_ids",
        "oriented_canonical_faces",
    }
    metadata = {
        field: getattr(provenance, field)
        for field in CadEntityProvenance.__dataclass_fields__
        if field not in array_fields
    }
    digest = sha256()
    _update(digest, b"autotessell/cad-reader-payload/v1")
    _update(
        digest, json.dumps(metadata, default=str, sort_keys=True, separators=(",", ":")).encode()
    )
    for label, array in (
        ("vertices", valid.vertices),
        ("faces", valid.faces),
        ("triangle_face_ordinals", provenance.triangle_face_ordinals),
        ("triangle_orientation_reversed", provenance.triangle_orientation_reversed),
        ("seam_vertex_ids", provenance.seam_vertex_ids),
        ("canonical_vertex_source_ids", provenance.canonical_vertex_source_ids),
        ("oriented_canonical_faces", provenance.oriented_canonical_faces),
    ):
        _update_array(digest, label, array)
    return digest.hexdigest()


def _copy_snapshot(source: Path, snapshot: Path) -> tuple[str, int]:
    digest, count = sha256(), 0
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        if not stat.S_ISREG(os.fstat(source_fd).st_mode):
            raise OSError("source is not a regular file")
        target_fd = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(source_fd, "rb", closefd=True) as input_file:
                source_fd = -1
                with os.fdopen(target_fd, "wb", closefd=True) as output_file:
                    target_fd = -1
                    while chunk := input_file.read(_CHUNK_BYTES):
                        digest.update(chunk)
                        count += len(chunk)
                        output_file.write(chunk)
                    output_file.flush()
                    os.fsync(output_file.fileno())
        finally:
            if target_fd >= 0:
                os.close(target_fd)
    finally:
        if source_fd >= 0:
            os.close(source_fd)
    os.chmod(snapshot, 0o600)
    return digest.hexdigest(), count


def load_cad_native_with_provenance_snapshot_l0(
    source_path: str | Path,
    fmt: str,
    *,
    expected_source_sha256: str,
    expected_reader_payload_sha256: str,
    reader: Callable[[Path, str], CadNativeTriangulation] | None = None,
) -> CadSnapshotProvenanceL0:
    """Invoke the provenance reader only on an exact private byte snapshot."""
    if not cad_provenance_snapshot_l0_enabled():
        return _report("disabled_cad_provenance_snapshot_l0", False)
    if (
        not isinstance(source_path, (str, Path))
        or not isinstance(fmt, str)
        or fmt.lstrip(".").lower() not in _FORMATS
        or not _canonical_sha256(expected_source_sha256)
        or not _canonical_sha256(expected_reader_payload_sha256)
    ):
        return _report("reject_invalid_snapshot_declaration", True, malformed=("declaration",))
    source = Path(source_path)
    if not source.is_file():
        return _report("reject_snapshot_source_not_found", True)
    source_hash: str | None = None
    source_bytes = 0
    result: CadSnapshotProvenanceL0
    try:
        with tempfile.TemporaryDirectory(prefix="autotessell_cad_snapshot_") as directory:
            private = Path(directory)
            os.chmod(private, 0o700)
            snapshot = private / "source.snapshot"
            try:
                source_hash, source_bytes = _copy_snapshot(source, snapshot)
            except OSError:
                result = _report(
                    "reject_snapshot_source_unreadable",
                    True,
                    source_hash=source_hash,
                    source_bytes=source_bytes,
                )
            else:
                if source_hash != expected_source_sha256:
                    result = _report(
                        "reject_snapshot_source_digest_mismatch",
                        True,
                        source_hash=source_hash,
                        source_bytes=source_bytes,
                    )
                else:
                    try:
                        loaded = (reader or load_cad_native_with_provenance)(snapshot, fmt)
                    except Exception:
                        result = _report(
                            "reject_snapshot_provenance_reader_failed",
                            True,
                            source_hash=source_hash,
                            source_bytes=source_bytes,
                            source_matches=True,
                            reader_invoked=True,
                        )
                    else:
                        valid, malformed = _validate(loaded)
                        if valid is None:
                            physical = bool(
                                isinstance(loaded, CadNativeTriangulation)
                                and isinstance(loaded.provenance, CadEntityProvenance)
                                and loaded.provenance.physical_groups_authoritative
                            )
                            result = _report(
                                "reject_snapshot_provenance_payload",
                                True,
                                source_hash=source_hash,
                                source_bytes=source_bytes,
                                source_matches=True,
                                reader_invoked=True,
                                snapshot_received=True,
                                physical=physical,
                                malformed=malformed,
                            )
                        else:
                            valid.vertices.setflags(write=False)
                            valid.faces.setflags(write=False)
                            payload_hash = canonical_cad_reader_payload_sha256(valid)
                            if payload_hash != expected_reader_payload_sha256:
                                result = _report(
                                    "reject_snapshot_reader_payload_digest_mismatch",
                                    True,
                                    source_hash=source_hash,
                                    source_bytes=source_bytes,
                                    payload_hash=payload_hash,
                                    source_matches=True,
                                    reader_invoked=True,
                                    snapshot_received=True,
                                    payload_valid=True,
                                )
                            else:
                                result = _report(
                                    "report_snapshot_reader_provenance_unverified",
                                    True,
                                    source_hash=source_hash,
                                    source_bytes=source_bytes,
                                    payload_hash=payload_hash,
                                    source_matches=True,
                                    payload_matches=True,
                                    reader_invoked=True,
                                    snapshot_received=True,
                                    payload_valid=True,
                                    triangulation=valid,
                                )
        return replace(result, snapshot_removed=True)
    except OSError:
        return _report(
            "reject_snapshot_private_storage_failed",
            True,
            source_hash=source_hash,
            source_bytes=source_bytes,
            source_matches=source_hash == expected_source_sha256,
        )
