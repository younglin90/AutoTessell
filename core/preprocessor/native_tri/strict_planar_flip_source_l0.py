"""Source-locked test-authority ingress for the isolated native-tri flip.

This is deliberately an offline contract.  An authored test-side declaration
must bind to exact STL bytes and to the exact arrays produced by ``read_stl``;
it does not infer CAD/STL physical-group authority or select a product route.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from numbers import Integral
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)


def _array_hash(values: np.ndarray) -> str:
    digest = sha256()
    digest.update(str(values.dtype).encode("ascii"))
    digest.update(np.asarray(values.shape, dtype=np.int64).tobytes())
    digest.update(values.tobytes())
    return digest.hexdigest()


def _canonical_digest(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        return None
    return value


@dataclass(frozen=True, slots=True)
class AuthoritativeNativeTriPatchIds:
    """Test-authored source-face payloads; bare payloads are forbidden."""

    payloads: tuple[int | str | None, ...]
    authoritative: bool


@dataclass(frozen=True, slots=True)
class AuthoritativeNativeTriFeatureEdges:
    """Test-authored source feature edges; inference is forbidden."""

    edges: tuple[tuple[int, int], ...]
    authoritative: bool


@dataclass(frozen=True, slots=True)
class StrictPlanarFlipSourceRequest:
    """One exact STL input plus its explicit test-authority declaration."""

    source_path: Path | str
    source_sha256: str
    vertices_sha256: str
    faces_sha256: str
    patch_ids: AuthoritativeNativeTriPatchIds
    feature_edges: AuthoritativeNativeTriFeatureEdges
    physical_groups: AuthoritativePhysicalGroupMapping


@dataclass(frozen=True, slots=True)
class StrictPlanarFlipSource:
    """Immutable, admitted source arrays and explicitly declared payloads."""

    vertices: np.ndarray
    faces: np.ndarray
    patch_ids: tuple[int | str | None, ...]
    feature_edges: tuple[tuple[int, int], ...]
    physical_groups: tuple[str, ...]
    source_sha256: str
    vertices_sha256: str
    faces_sha256: str
    physical_groups_sha256: str
    contract: str = "strict_planar_flip_source_l0_test_authority"


@dataclass(frozen=True, slots=True)
class StrictPlanarFlipSourceResult:
    accepted: bool
    status: str
    rejection_reason: str | None
    source: StrictPlanarFlipSource | None


def _rejected(reason: str) -> StrictPlanarFlipSourceResult:
    return StrictPlanarFlipSourceResult(False, "reject_strict_planar_flip_source", reason, None)


def _readonly_copy(values: np.ndarray) -> np.ndarray:
    copied = np.ascontiguousarray(values).copy()
    copied.setflags(write=False)
    return copied


def _patches(value: object, count: int) -> tuple[int | str | None, ...] | None:
    if (
        not isinstance(value, AuthoritativeNativeTriPatchIds)
        or not value.authoritative
        or len(value.payloads) != count
    ):
        return None
    payloads: list[int | str | None] = []
    for raw in value.payloads:
        scalar = raw.item() if isinstance(raw, np.generic) else raw
        if isinstance(scalar, bool) or not isinstance(scalar, (Integral, str, type(None))):
            return None
        payloads.append(int(scalar) if isinstance(scalar, Integral) else scalar)
    return tuple(payloads)


def _physical_groups(value: object, count: int) -> tuple[str, ...] | None:
    if (
        not isinstance(value, AuthoritativePhysicalGroupMapping)
        or not value.authoritative
        or len(value.source_face_groups) != count
        or not all(isinstance(group, str) and group.strip() for group in value.source_face_groups)
    ):
        return None
    return tuple(value.source_face_groups)


def _source_edges(faces: np.ndarray) -> frozenset[tuple[int, int]]:
    return frozenset(
        (min(int(first), int(second)), max(int(first), int(second)))
        for face in faces.tolist()
        for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))
    )


def _feature_edges(
    value: object,
    source_edges: frozenset[tuple[int, int]],
) -> tuple[tuple[int, int], ...] | None:
    if not isinstance(value, AuthoritativeNativeTriFeatureEdges) or not value.authoritative:
        return None
    edges: list[tuple[int, int]] = []
    for raw in value.edges:
        if (
            not isinstance(raw, tuple)
            or len(raw) != 2
            or isinstance(raw[0], bool)
            or isinstance(raw[1], bool)
            or not isinstance(raw[0], Integral)
            or not isinstance(raw[1], Integral)
        ):
            return None
        edge = (int(raw[0]), int(raw[1]))
        if edge[0] >= edge[1] or edge not in source_edges:
            return None
        edges.append(edge)
    if edges != sorted(set(edges)):
        return None
    return tuple(edges)


def ingest_strict_planar_flip_source_l0(request: object) -> StrictPlanarFlipSourceResult:
    """Load an exact STL only when all declared test-authority bindings match."""
    if not isinstance(request, StrictPlanarFlipSourceRequest):
        return _rejected("strict_planar_flip_source_request_required")
    expected = (
        _canonical_digest(request.source_sha256),
        _canonical_digest(request.vertices_sha256),
        _canonical_digest(request.faces_sha256),
    )
    if any(value is None for value in expected):
        return _rejected("strict_planar_flip_source_digest_invalid")
    if not isinstance(request.source_path, (str, Path)):
        return _rejected("strict_planar_flip_source_path_invalid")
    path = Path(request.source_path)
    if path.is_symlink() or not path.is_file():
        return _rejected("strict_planar_flip_source_path_invalid")
    try:
        source_bytes = path.read_bytes()
        mesh = read_stl(path)
        vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
        faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    except (OSError, ValueError, TypeError):
        return _rejected("strict_planar_flip_source_read_failed")
    if (
        vertices.ndim != 2
        or vertices.shape[1] != 3
        or faces.ndim != 2
        or faces.shape[1] != 3
        or len(faces) < 2
        or not np.isfinite(vertices).all()
        or (faces < 0).any()
        or (faces >= len(vertices)).any()
        or any(len(set(face.tolist())) != 3 for face in faces)
    ):
        return _rejected("strict_planar_flip_source_arrays_invalid")
    source_hash = sha256(source_bytes).hexdigest()
    vertices_hash = _array_hash(vertices)
    faces_hash = _array_hash(faces)
    if (source_hash, vertices_hash, faces_hash) != expected:
        return _rejected("strict_planar_flip_source_binding_mismatch")
    patches = _patches(request.patch_ids, len(faces))
    groups = _physical_groups(request.physical_groups, len(faces))
    features = _feature_edges(request.feature_edges, _source_edges(faces))
    if patches is None:
        return _rejected("strict_planar_flip_source_patch_authority_required")
    if groups is None:
        return _rejected("strict_planar_flip_source_physical_authority_required")
    if features is None:
        return _rejected("strict_planar_flip_source_feature_authority_required")
    group_hash = sha256(repr(groups).encode("utf-8")).hexdigest()
    source = StrictPlanarFlipSource(
        vertices=_readonly_copy(vertices),
        faces=_readonly_copy(faces),
        patch_ids=patches,
        feature_edges=features,
        physical_groups=groups,
        source_sha256=source_hash,
        vertices_sha256=vertices_hash,
        faces_sha256=faces_hash,
        physical_groups_sha256=group_hash,
    )
    return StrictPlanarFlipSourceResult(
        True,
        "pass_strict_planar_flip_source_test_authority",
        None,
        source,
    )


__all__ = [
    "AuthoritativeNativeTriFeatureEdges",
    "AuthoritativeNativeTriPatchIds",
    "StrictPlanarFlipSource",
    "StrictPlanarFlipSourceRequest",
    "StrictPlanarFlipSourceResult",
    "ingest_strict_planar_flip_source_l0",
]
