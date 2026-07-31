"""Default-OFF fixed-pair mixed triangle/quad surface transaction.

This is an independent product lane, not a relabel of
``native_quad_dominant``.  An explicit, partial pair plan consumes some source
triangles into quads and retains the rest as triangles.  Every array and
payload is derived from immutable source inputs; no pipeline, UI, or writer is
wired to this module.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from numbers import Integral

import numpy as np

from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_remesh.surface_mode_contract import (
    SurfaceProductCertificate,
    SurfaceProductMode,
    certify_surface_product_mode,
)

from .strict_pair_preflight import _oriented_quad, _signed_pair_volume

_ENV = "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_PRODUCT_L0"
_PRODUCER = "native_tri_quad_fixed_pair_l0"


@dataclass(frozen=True, slots=True)
class AuthoritativeTriQuadFeatureEdges:
    """Explicit source feature edges; inference is deliberately forbidden."""

    edges: tuple[tuple[int, int], ...]
    authoritative: bool


@dataclass(frozen=True, slots=True)
class AuthoritativeTriQuadPatchIds:
    """Explicit source-face patch IDs; inferred or bare payloads are forbidden."""

    payloads: tuple[int | str, ...]
    authoritative: bool


@dataclass(frozen=True, slots=True)
class TriQuadFixedPairPreflight:
    """Fail-closed source/topology/payload evidence for one pair plan."""

    accepted: bool
    rejection_reason: str | None
    source_vertices_hash: str | None
    source_triangles_hash: str | None
    source_patch_hash: str | None
    source_physical_group_hash: str | None
    feature_hash: str | None
    source_oriented_manifold: bool
    output_oriented_manifold: bool
    boundary_equal: bool
    feature_edges_preserved: bool
    component_count_equal: bool
    euler_characteristic_equal: bool
    provenance_complete: bool
    patch_payload_preserved: bool
    physical_group_payload_preserved: bool


@dataclass(frozen=True, slots=True)
class TriQuadFixedPairProduct:
    """Read-only separate mixed-face arrays plus exact source provenance."""

    vertices: np.ndarray
    triangles: np.ndarray
    quads: np.ndarray
    triangle_source_indices: np.ndarray
    quad_source_pairs: np.ndarray
    triangle_patch_ids: tuple[int | str, ...]
    quad_patch_ids: tuple[int | str, ...]
    triangle_physical_groups: tuple[str, ...]
    quad_physical_groups: tuple[str, ...]
    source_vertices_hash: str
    source_triangles_hash: str
    source_patch_hash: str
    source_physical_group_hash: str
    feature_hash: str
    contract: str = "tri_quad_fixed_pair_product_l0"


@dataclass(frozen=True, slots=True)
class TriQuadFixedPairProductResult:
    """Explicit admission result; no writer/product-route promotion occurs."""

    accepted: bool
    status: str
    rejection_reason: str | None
    transaction_applied: bool
    independent_product_ready: bool
    product_claimed: bool
    preflight: TriQuadFixedPairPreflight
    product_certificate: SurfaceProductCertificate | None
    product: TriQuadFixedPairProduct | None


@dataclass(frozen=True, slots=True)
class _TopologyAudit:
    valid: bool
    edges: frozenset[tuple[int, int]]
    boundary: tuple[tuple[int, int, int], ...]
    components: int
    euler: int


def tri_quad_fixed_pair_product_l0_enabled() -> bool:
    """Return whether this disconnected materializer was explicitly enabled."""
    return os.environ.get(_ENV) == "1"


def _hash_bytes(*parts: bytes) -> str:
    digest = sha256()
    for part in parts:
        digest.update(part)
    return digest.hexdigest()


def _array_hash(values: np.ndarray) -> str:
    return _hash_bytes(
        str(values.dtype).encode("ascii"),
        np.asarray(values.shape, dtype=np.int64).tobytes(),
        values.tobytes(),
    )


def _readonly_copy(values: np.ndarray) -> np.ndarray:
    copied = np.ascontiguousarray(values).copy()
    copied.setflags(write=False)
    return copied


def _edge(first: int, second: int) -> tuple[int, int]:
    return (first, second) if first < second else (second, first)


def _points(value: object) -> np.ndarray | None:
    if (
        not isinstance(value, np.ndarray)
        or value.dtype != np.dtype(np.float64)
        or value.ndim != 2
        or value.shape[1] != 3
        or not value.flags.c_contiguous
        or not np.isfinite(value).all()
    ):
        return None
    return value


def _triangles(value: object) -> np.ndarray | None:
    if (
        not isinstance(value, np.ndarray)
        or value.dtype != np.dtype(np.int64)
        or value.ndim != 2
        or value.shape[1] != 3
        or not value.flags.c_contiguous
        or len(value) == 0
    ):
        return None
    return value


def _pair_plan(value: object, source_count: int) -> np.ndarray | None:
    if (
        not isinstance(value, np.ndarray)
        or value.dtype != np.dtype(np.int64)
        or value.ndim != 2
        or value.shape[1] != 2
        or not value.flags.c_contiguous
        or len(value) == 0
        or 2 * len(value) >= source_count
    ):
        return None
    consumed: set[int] = set()
    previous: tuple[int, int] | None = None
    for raw in value.tolist():
        pair = (int(raw[0]), int(raw[1]))
        if pair[0] < 0 or pair[1] >= source_count or pair[0] >= pair[1]:
            return None
        if previous is not None and pair <= previous:
            return None
        if pair[0] in consumed or pair[1] in consumed:
            return None
        consumed.update(pair)
        previous = pair
    return value


def _payloads(value: object, count: int) -> tuple[int | str, ...] | None:
    if not isinstance(value, (tuple, list)) or len(value) != count:
        return None
    out: list[int | str] = []
    for raw in value:
        scalar = raw.item() if isinstance(raw, np.generic) else raw
        if isinstance(scalar, bool):
            return None
        if isinstance(scalar, Integral):
            out.append(int(scalar))
        elif isinstance(scalar, str) and scalar.strip():
            out.append(scalar)
        else:
            return None
    return tuple(out)


def _patches(value: object, count: int) -> tuple[int | str, ...] | None:
    if not isinstance(value, AuthoritativeTriQuadPatchIds) or not value.authoritative:
        return None
    return _payloads(value.payloads, count)


def _payload_hash(values: tuple[int | str, ...] | tuple[str, ...]) -> str:
    return _hash_bytes(
        json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    )


def _physical_groups(value: object, count: int) -> tuple[str, ...] | None:
    if (
        not isinstance(value, AuthoritativePhysicalGroupMapping)
        or not value.authoritative
        or len(value.source_face_groups) != count
        or not all(isinstance(group, str) and group.strip() for group in value.source_face_groups)
    ):
        return None
    return tuple(value.source_face_groups)


def _topology(vertices: np.ndarray, faces: tuple[np.ndarray, ...]) -> _TopologyAudit:
    rows = [tuple(int(index) for index in row) for values in faces for row in values]
    if not rows:
        return _TopologyAudit(False, frozenset(), (), 0, 0)
    edge_owners: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for face_index, face in enumerate(rows):
        if (
            len(set(face)) != len(face)
            or any(index < 0 or index >= len(vertices) for index in face)
        ):
            return _TopologyAudit(False, frozenset(), (), 0, 0)
        first, second, third = (vertices[index] for index in face[:3])
        if float(np.linalg.norm(np.cross(second - first, third - first))) <= np.finfo(float).tiny:
            return _TopologyAudit(False, frozenset(), (), 0, 0)
        for local, first_index in enumerate(face):
            second_index = face[(local + 1) % len(face)]
            key = _edge(first_index, second_index)
            direction = 1 if (first_index, second_index) == key else -1
            edge_owners.setdefault(key, []).append((face_index, direction))
    manifold = all(
        len(owners) <= 2 and (len(owners) != 2 or owners[0][1] != owners[1][1])
        for owners in edge_owners.values()
    )
    if not manifold:
        return _TopologyAudit(False, frozenset(edge_owners), (), 0, 0)
    adjacency = [set() for _ in rows]
    for owners in edge_owners.values():
        if len(owners) == 2:
            first_face, second_face = owners[0][0], owners[1][0]
            adjacency[first_face].add(second_face)
            adjacency[second_face].add(first_face)
    unseen = set(range(len(rows)))
    components = 0
    while unseen:
        components += 1
        pending = [unseen.pop()]
        while pending:
            current = pending.pop()
            neighbours = adjacency[current].intersection(unseen)
            unseen.difference_update(neighbours)
            pending.extend(neighbours)
    boundary = tuple(
        sorted(
            (edge[0], edge[1], owners[0][1])
            for edge, owners in edge_owners.items()
            if len(owners) == 1
        )
    )
    return _TopologyAudit(
        True,
        frozenset(edge_owners),
        boundary,
        components,
        len(vertices) - len(edge_owners) + len(rows),
    )


def _features(value: object, source_edges: frozenset[tuple[int, int]]) -> tuple[tuple[tuple[int, int], ...], str] | None:
    if not isinstance(value, AuthoritativeTriQuadFeatureEdges) or not value.authoritative:
        return None
    if not isinstance(value.edges, tuple):
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
    normalized = tuple(edges)
    return normalized, _hash_bytes(
        json.dumps(normalized, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    )


def _rejected(reason: str) -> TriQuadFixedPairProductResult:
    preflight = TriQuadFixedPairPreflight(
        False, reason, None, None, None, None, None,
        False, False, False, False, False, False, False, False, False,
    )
    return TriQuadFixedPairProductResult(
        False, "reject_tri_quad_fixed_pair_preflight", reason,
        False, False, False, preflight, None, None,
    )


def materialize_tri_quad_fixed_pair_product_l0(
    source_vertices: object,
    source_triangles: object,
    pair_plan: object,
    feature_edges: object,
    *,
    source_patch_ids: object,
    source_physical_groups: object,
) -> TriQuadFixedPairProductResult:
    """Materialize a true partial-pair mixed product, never a handoff clone.

    The plan must consume at least one but not all source triangles.  Quads,
    residual triangles, provenance, patch IDs, and physical groups are all
    derived here; callers cannot provide an output mesh to relabel.
    """
    vertices = _points(source_vertices)
    triangles = _triangles(source_triangles)
    if vertices is None or triangles is None:
        return _rejected("source_arrays_invalid")
    if (
        (triangles < 0).any()
        or (triangles >= len(vertices)).any()
        or any(len(set(row.tolist())) != 3 for row in triangles)
    ):
        return _rejected("source_triangle_indices_invalid")
    plan = _pair_plan(pair_plan, len(triangles))
    if plan is None:
        return _rejected("partial_pair_plan_required")
    source_patches = _patches(source_patch_ids, len(triangles))
    source_groups = _physical_groups(source_physical_groups, len(triangles))
    if source_patches is None:
        return _rejected("source_patch_payload_required")
    if source_groups is None:
        return _rejected("authoritative_source_physical_groups_required")

    source_audit = _topology(vertices, (triangles,))
    if not source_audit.valid:
        return _rejected("source_topology_invalid")
    normalized_features = _features(feature_edges, source_audit.edges)
    if normalized_features is None:
        return _rejected("authoritative_feature_edges_required")
    declared_features, feature_hash = normalized_features

    quads: list[tuple[int, int, int, int]] = []
    quad_patches: list[int | str] = []
    quad_groups: list[str] = []
    consumed = np.zeros(len(triangles), dtype=bool)
    for first_raw, second_raw in plan.tolist():
        first, second = int(first_raw), int(second_raw)
        if source_patches[first] != source_patches[second]:
            return _rejected("quad_pair_patch_payload_ambiguous")
        if source_groups[first] != source_groups[second]:
            return _rejected("quad_pair_physical_group_payload_ambiguous")
        quad = _oriented_quad(triangles[first], triangles[second])
        if quad is None or _signed_pair_volume(vertices, quad) != 0.0:
            return _rejected("pair_not_adjacent_coplanar")
        quads.append(quad)
        quad_patches.append(source_patches[first])
        quad_groups.append(source_groups[first])
        consumed[first] = True
        consumed[second] = True

    residual_indices = np.flatnonzero(~consumed).astype(np.int64, copy=False)
    residual_triangles = np.ascontiguousarray(triangles[residual_indices], dtype=np.int64)
    quad_array = np.ascontiguousarray(np.asarray(quads, dtype=np.int64), dtype=np.int64)
    if len(residual_triangles) == 0 or len(quad_array) == 0:
        return _rejected("genuine_mixed_output_required")
    output_audit = _topology(vertices, (residual_triangles, quad_array))
    boundary_equal = source_audit.boundary == output_audit.boundary
    features_preserved = bool(output_audit.valid and set(declared_features).issubset(output_audit.edges))
    components_equal = source_audit.components == output_audit.components
    euler_equal = source_audit.euler == output_audit.euler
    provenance_complete = bool(
        len(np.unique(plan.reshape(-1))) == plan.size
        and np.array_equal(residual_triangles, triangles[residual_indices])
        and len(residual_indices) + 2 * len(plan) == len(triangles)
    )
    triangle_patches = tuple(source_patches[int(index)] for index in residual_indices)
    triangle_groups = tuple(source_groups[int(index)] for index in residual_indices)
    patch_preserved = bool(len(triangle_patches) == len(residual_triangles) and len(quad_patches) == len(quad_array))
    groups_preserved = bool(len(triangle_groups) == len(residual_triangles) and len(quad_groups) == len(quad_array))
    source_vertices_hash = _array_hash(vertices)
    source_triangles_hash = _array_hash(triangles)
    source_patch_hash = _payload_hash(source_patches)
    source_group_hash = _payload_hash(source_groups)
    accepted = bool(
        output_audit.valid
        and boundary_equal
        and features_preserved
        and components_equal
        and euler_equal
        and provenance_complete
        and patch_preserved
        and groups_preserved
    )
    preflight = TriQuadFixedPairPreflight(
        accepted,
        None if accepted else "mixed_source_contract_rejected",
        source_vertices_hash,
        source_triangles_hash,
        source_patch_hash,
        source_group_hash,
        feature_hash,
        source_audit.valid,
        output_audit.valid,
        boundary_equal,
        features_preserved,
        components_equal,
        euler_equal,
        provenance_complete,
        patch_preserved,
        groups_preserved,
    )
    if not accepted:
        return TriQuadFixedPairProductResult(
            False, "reject_tri_quad_fixed_pair_preflight", "mixed_source_contract_rejected",
            False, False, False, preflight, None, None,
        )
    certificate = certify_surface_product_mode(
        SurfaceProductMode.TRI_QUAD,
        triangle_count=len(residual_triangles),
        quad_count=len(quad_array),
        separate_tri_quad_representation=True,
        triangular_handoff=False,
        producer=_PRODUCER,
    )
    if not certificate.accepted:
        return TriQuadFixedPairProductResult(
            False, "reject_tri_quad_fixed_pair_mode",
            certificate.rejection_reason or "tri_quad_mode_rejected",
            False, False, False, preflight, certificate, None,
        )
    if not tri_quad_fixed_pair_product_l0_enabled():
        return TriQuadFixedPairProductResult(
            False, "reject_tri_quad_fixed_pair_product_disabled",
            "tri_quad_fixed_pair_product_l0_disabled",
            False, False, False, preflight, certificate, None,
        )
    product = TriQuadFixedPairProduct(
        vertices=_readonly_copy(vertices),
        triangles=_readonly_copy(residual_triangles),
        quads=_readonly_copy(quad_array),
        triangle_source_indices=_readonly_copy(residual_indices),
        quad_source_pairs=_readonly_copy(plan),
        triangle_patch_ids=triangle_patches,
        quad_patch_ids=tuple(quad_patches),
        triangle_physical_groups=triangle_groups,
        quad_physical_groups=tuple(quad_groups),
        source_vertices_hash=source_vertices_hash,
        source_triangles_hash=source_triangles_hash,
        source_patch_hash=source_patch_hash,
        source_physical_group_hash=source_group_hash,
        feature_hash=feature_hash,
    )
    return TriQuadFixedPairProductResult(
        True, "pass_tri_quad_fixed_pair_product_unwritten", None,
        True, False, False, preflight, certificate, product,
    )


__all__ = [
    "AuthoritativeTriQuadFeatureEdges",
    "AuthoritativeTriQuadPatchIds",
    "TriQuadFixedPairPreflight",
    "TriQuadFixedPairProduct",
    "TriQuadFixedPairProductResult",
    "materialize_tri_quad_fixed_pair_product_l0",
    "tri_quad_fixed_pair_product_l0_enabled",
]
