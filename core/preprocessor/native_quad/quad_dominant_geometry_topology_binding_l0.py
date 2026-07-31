"""Default-OFF geometry/topology evidence for actual quad-dominant output."""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from numbers import Integral

import numpy as np

from core.preprocessor.native_remesh.quad_dominant import QuadDominantResult
from core.preprocessor.native_remesh.surface_mode_contract import SurfaceProductMode

from .quad_dominant_payload_binding_l0 import QuadDominantPayloadBindingL0
from .quad_dominant_product_certificate_l0 import (
    diagnose_quad_dominant_product_output_l0,
)

_ENV = "AUTO_TESSELL_TRI_QUAD_GEOMETRY_TOPOLOGY_BINDING_L0"


@dataclass(frozen=True, slots=True)
class AuthoritativeFeatureEdges:
    """Explicit source-edge declaration; geometric feature inference is forbidden."""

    edges: tuple[tuple[int, int], ...]
    authoritative: bool


@dataclass(frozen=True, slots=True)
class QuadDominantGeometryTopologyBindingL0:
    """Read-only mixed-face evidence; never a tri+quad product acceptance."""

    enabled: bool
    status: str
    rejection_reason: str
    source_vertices_exact: bool = False
    output_face_provenance_exact: bool = False
    payload_binding_complete: bool = False
    source_feature_edges_authoritative: bool = False
    source_oriented_manifold: bool = False
    output_oriented_manifold: bool = False
    boundary_equal: bool = False
    features_preserved: bool = False
    component_count_equal: bool = False
    euler_characteristic_equal: bool = False
    arrays_unchanged: bool = False
    source_component_count: int | None = None
    output_component_count: int | None = None
    source_euler_characteristic: int | None = None
    output_euler_characteristic: int | None = None
    geometry_topology_complete: bool = False
    missing_evidence: tuple[str, ...] = ()
    malformed_evidence: tuple[str, ...] = ()
    accepted: bool = False
    product_claimed: bool = False
    contract: str = "native_quad_dominant_geometry_topology_binding_l0"


@dataclass(frozen=True, slots=True)
class _SurfaceAudit:
    valid: bool
    oriented_manifold: bool
    boundary: tuple[tuple[int, int, int], ...]
    edges: frozenset[tuple[int, int]]
    component_count: int
    euler_characteristic: int


def tri_quad_geometry_topology_binding_l0_enabled() -> bool:
    """Return whether the runtime-disconnected diagnostic is explicitly on."""
    return os.environ.get(_ENV) == "1"


def _edge(first: int, second: int) -> tuple[int, int]:
    return (first, second) if first < second else (second, first)


def _strict_array(value: object, *, columns: int) -> np.ndarray | None:
    if (
        not isinstance(value, np.ndarray)
        or value.dtype != np.dtype(np.int64)
        or value.ndim != 2
        or value.shape[1] != columns
        or not value.flags.c_contiguous
    ):
        return None
    return value


def _audit_mixed_surface(
    vertices: np.ndarray,
    face_arrays: tuple[np.ndarray, ...],
) -> _SurfaceAudit:
    if not np.isfinite(vertices).all():
        return _SurfaceAudit(False, False, (), frozenset(), 0, 0)
    faces = [tuple(int(index) for index in row) for values in face_arrays for row in values]
    if not faces:
        return _SurfaceAudit(False, False, (), frozenset(), 0, 0)
    edge_owners: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    vertex_links: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
    for face_index, face in enumerate(faces):
        if (
            len(set(face)) != len(face)
            or any(index < 0 or index >= len(vertices) for index in face)
        ):
            return _SurfaceAudit(False, False, (), frozenset(), 0, 0)
        first, second, third = (vertices[index] for index in face[:3])
        if float(np.linalg.norm(np.cross(second - first, third - first))) <= np.finfo(float).tiny:
            return _SurfaceAudit(False, False, (), frozenset(), 0, 0)
        for local, first_index in enumerate(face):
            second_index = face[(local + 1) % len(face)]
            key = _edge(first_index, second_index)
            direction = 1 if (first_index, second_index) == key else -1
            edge_owners[key].append((face_index, direction))
            previous_index = face[(local - 1) % len(face)]
            vertex_links[first_index][previous_index].add(second_index)
            vertex_links[first_index][second_index].add(previous_index)
    oriented_manifold = all(
        len(owners) <= 2 and (len(owners) != 2 or owners[0][1] != owners[1][1])
        for owners in edge_owners.values()
    )
    if not oriented_manifold:
        return _SurfaceAudit(False, False, (), frozenset(edge_owners), 0, 0)
    for link in vertex_links.values():
        unseen = set(link)
        if not unseen:
            continue
        pending = [unseen.pop()]
        while pending:
            vertex = pending.pop()
            neighbors = link[vertex].intersection(unseen)
            unseen.difference_update(neighbors)
            pending.extend(neighbors)
        if unseen:
            return _SurfaceAudit(False, False, (), frozenset(edge_owners), 0, 0)
    adjacency = [set() for _ in faces]
    for owners in edge_owners.values():
        if len(owners) == 2:
            first_face, second_face = owners[0][0], owners[1][0]
            adjacency[first_face].add(second_face)
            adjacency[second_face].add(first_face)
    components = 0
    unseen_faces = set(range(len(faces)))
    while unseen_faces:
        components += 1
        pending = [unseen_faces.pop()]
        while pending:
            face = pending.pop()
            neighbors = adjacency[face].intersection(unseen_faces)
            unseen_faces.difference_update(neighbors)
            pending.extend(neighbors)
    boundary = tuple(
        sorted(
            (edge[0], edge[1], owners[0][1])
            for edge, owners in edge_owners.items()
            if len(owners) == 1
        )
    )
    return _SurfaceAudit(
        True,
        True,
        boundary,
        frozenset(edge_owners),
        components,
        len(vertices) - len(edge_owners) + len(faces),
    )


def _authoritative_feature_edges(
    value: object,
    source_edges: frozenset[tuple[int, int]],
) -> tuple[frozenset[tuple[int, int]] | None, bool]:
    if not isinstance(value, AuthoritativeFeatureEdges) or not value.authoritative:
        return None, False
    if not isinstance(value.edges, tuple):
        return None, False
    edges: list[tuple[int, int]] = []
    for raw in value.edges:
        if not isinstance(raw, tuple) or len(raw) != 2:
            return None, False
        first, second = raw
        if (
            isinstance(first, (bool, np.bool_))
            or isinstance(second, (bool, np.bool_))
            or not isinstance(first, Integral)
            or not isinstance(second, Integral)
        ):
            return None, False
        edge = (int(first), int(second))
        if edge[0] >= edge[1] or edge not in source_edges:
            return None, False
        edges.append(edge)
    if edges != sorted(set(edges)):
        return None, False
    return frozenset(edges), True


def diagnose_quad_dominant_geometry_topology_binding_l0(
    source_vertices: object,
    source_triangles: object,
    result: object,
    *,
    payload_binding: object,
    source_feature_edges: object,
) -> QuadDominantGeometryTopologyBindingL0:
    """Diagnose mixed-face geometry/topology binding without product promotion."""
    if not tri_quad_geometry_topology_binding_l0_enabled():
        return QuadDominantGeometryTopologyBindingL0(
            False,
            "reject_tri_quad_geometry_topology_binding_disabled",
            "tri_quad_geometry_topology_binding_l0_disabled",
            missing_evidence=("geometry_topology_binding_opt_in",),
        )
    if not isinstance(result, QuadDominantResult):
        return QuadDominantGeometryTopologyBindingL0(
            True,
            "reject_tri_quad_geometry_topology_result_invalid",
            "quad_dominant_result_required",
            malformed_evidence=("quad_dominant_result",),
        )
    output_certificate = diagnose_quad_dominant_product_output_l0(
        source_vertices,
        source_triangles,
        result,
        requested_mode=SurfaceProductMode.TRI_QUAD,
    )
    if (
        not output_certificate.source_vertices_exact
        or not output_certificate.output_face_provenance_exact
    ):
        return QuadDominantGeometryTopologyBindingL0(
            True,
            "reject_tri_quad_geometry_topology_output_provenance",
            "byte_exact_source_and_output_face_provenance_required",
            source_vertices_exact=output_certificate.source_vertices_exact,
            output_face_provenance_exact=output_certificate.output_face_provenance_exact,
            missing_evidence=("source_shape", "output_face_provenance"),
        )
    if (
        not isinstance(payload_binding, QuadDominantPayloadBindingL0)
        or not payload_binding.binding_complete
    ):
        return QuadDominantGeometryTopologyBindingL0(
            True,
            "reject_tri_quad_geometry_topology_payload_binding",
            "complete_payload_binding_required",
            source_vertices_exact=True,
            output_face_provenance_exact=True,
            missing_evidence=("payload_binding",),
        )
    if (
        not isinstance(source_vertices, np.ndarray)
        or source_vertices.dtype != np.dtype(np.float64)
        or source_vertices.ndim != 2
        or source_vertices.shape[1] != 3
        or not source_vertices.flags.c_contiguous
    ):
        return QuadDominantGeometryTopologyBindingL0(
            True,
            "reject_tri_quad_geometry_topology_source_vertices",
            "source_vertices_must_be_c_contiguous_float64",
            source_vertices_exact=True,
            output_face_provenance_exact=True,
            payload_binding_complete=True,
            malformed_evidence=("source_vertices",),
        )
    source_faces = _strict_array(source_triangles, columns=3)
    output_triangles = _strict_array(result.triangles, columns=3)
    output_quads = _strict_array(result.quads, columns=4)
    if source_faces is None or output_triangles is None or output_quads is None:
        return QuadDominantGeometryTopologyBindingL0(
            True,
            "reject_tri_quad_geometry_topology_faces_invalid",
            "source_and_output_faces_must_be_c_contiguous_int64",
            source_vertices_exact=True,
            output_face_provenance_exact=True,
            payload_binding_complete=True,
            malformed_evidence=("mixed_faces",),
        )
    snapshots = (
        source_vertices.tobytes(),
        source_faces.tobytes(),
        output_triangles.tobytes(),
        output_quads.tobytes(),
        result.accepted_face_pairs.tobytes(),
        result.remaining_triangle_source_indices.tobytes(),
    )
    source_audit = _audit_mixed_surface(source_vertices, (source_faces,))
    output_audit = _audit_mixed_surface(
        source_vertices,
        (output_triangles, output_quads),
    )
    if not source_audit.valid or not output_audit.valid:
        return QuadDominantGeometryTopologyBindingL0(
            True,
            "reject_tri_quad_geometry_topology_nonmanifold",
            "source_or_output_mixed_surface_invalid",
            source_vertices_exact=True,
            output_face_provenance_exact=True,
            payload_binding_complete=True,
            source_oriented_manifold=source_audit.oriented_manifold,
            output_oriented_manifold=output_audit.oriented_manifold,
            malformed_evidence=("mixed_surface_topology",),
        )
    feature_edges, features_authoritative = _authoritative_feature_edges(
        source_feature_edges,
        source_audit.edges,
    )
    if feature_edges is None:
        return QuadDominantGeometryTopologyBindingL0(
            True,
            "reject_tri_quad_geometry_topology_feature_authority",
            "explicit_authoritative_feature_edges_required",
            source_vertices_exact=True,
            output_face_provenance_exact=True,
            payload_binding_complete=True,
            source_oriented_manifold=True,
            output_oriented_manifold=True,
            malformed_evidence=("source_feature_edges",),
        )
    boundary_equal = source_audit.boundary == output_audit.boundary
    features_preserved = feature_edges.issubset(output_audit.edges)
    components_equal = source_audit.component_count == output_audit.component_count
    euler_equal = source_audit.euler_characteristic == output_audit.euler_characteristic
    arrays_unchanged = snapshots == (
        source_vertices.tobytes(),
        source_faces.tobytes(),
        output_triangles.tobytes(),
        output_quads.tobytes(),
        result.accepted_face_pairs.tobytes(),
        result.remaining_triangle_source_indices.tobytes(),
    )
    complete = bool(
        boundary_equal
        and features_preserved
        and components_equal
        and euler_equal
        and arrays_unchanged
    )
    return QuadDominantGeometryTopologyBindingL0(
        True,
        "report_tri_quad_geometry_topology_binding_complete_unverified"
        if complete
        else "reject_tri_quad_geometry_topology_binding",
        "tri_quad_product_certificate_required"
        if complete
        else "mixed_surface_geometry_topology_binding_failed",
        source_vertices_exact=True,
        output_face_provenance_exact=True,
        payload_binding_complete=True,
        source_feature_edges_authoritative=features_authoritative,
        source_oriented_manifold=True,
        output_oriented_manifold=True,
        boundary_equal=boundary_equal,
        features_preserved=features_preserved,
        component_count_equal=components_equal,
        euler_characteristic_equal=euler_equal,
        arrays_unchanged=arrays_unchanged,
        source_component_count=source_audit.component_count,
        output_component_count=output_audit.component_count,
        source_euler_characteristic=source_audit.euler_characteristic,
        output_euler_characteristic=output_audit.euler_characteristic,
        geometry_topology_complete=complete,
        malformed_evidence=() if complete else ("geometry_topology_binding",),
    )


__all__ = [
    "AuthoritativeFeatureEdges",
    "QuadDominantGeometryTopologyBindingL0",
    "diagnose_quad_dominant_geometry_topology_binding_l0",
    "tri_quad_geometry_topology_binding_l0_enabled",
]
