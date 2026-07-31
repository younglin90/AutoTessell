"""Fail-closed audit for the fixed-vertex two-triangle strict-quad subset.

This is not a quadrangulation algorithm.  It accepts only an already supplied
quad array whose rows are canonical, coplanar-free connectivity unions of an
exact partition of immutable source triangles.  General strict-quad output
with inserted vertices needs a separate envelope and provenance contract.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha256
from numbers import Integral
from typing import Any

import numpy as np

_CPP23_ENV = "AUTO_TESSELL_STRICT_QUAD_PREFLIGHT_CPP23"
_STRUCTURAL_KEYS = (
    "valid",
    "coordinates_finite",
    "vertices_exact",
    "source_triangles_non_degenerate",
    "candidate_triangles_empty",
    "quads_degree_four",
    "provenance_complete",
    "pair_quads_exact",
    "pairs_coplanar",
    "source_manifold",
    "quad_manifold",
    "boundary_equal",
    "features_preserved",
    "source_component_count",
    "quad_component_count",
    "source_euler_characteristic",
    "quad_euler_characteristic",
)


def strict_quad_pair_preflight_cpp23_enabled() -> bool:
    """Return whether the optional native structural audit is explicitly on."""
    return os.environ.get(_CPP23_ENV) == "1"


def _hash(values: np.ndarray) -> str:
    digest = sha256()
    digest.update(str(values.dtype).encode("ascii"))
    digest.update(np.asarray(values.shape, dtype=np.int64).tobytes())
    digest.update(values.tobytes())
    return digest.hexdigest()


def _points(values: object, name: str) -> np.ndarray:
    if (
        not isinstance(values, np.ndarray)
        or values.dtype != np.dtype(np.float64)
        or values.ndim != 2
        or values.shape[1] != 3
        or not values.flags.c_contiguous
    ):
        raise ValueError(f"{name} must be a C-contiguous float64 array with shape (N, 3)")
    return values


def _indices(values: object, columns: int, name: str) -> np.ndarray:
    if (
        not isinstance(values, np.ndarray)
        or values.dtype != np.dtype(np.int64)
        or values.ndim != 2
        or values.shape[1] != columns
        or not values.flags.c_contiguous
    ):
        raise ValueError(f"{name} must be a C-contiguous int64 array with shape (N, {columns})")
    return values


def _canonical_edge(first: int, second: int) -> tuple[int, int]:
    return (first, second) if first < second else (second, first)


def _topology(
    faces: np.ndarray,
) -> tuple[bool, int, int, tuple[tuple[int, int, int], ...], frozenset[tuple[int, int]]]:
    """Return oriented-manifold facts for degree-three or degree-four faces."""
    edge_owners: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for face_index, face in enumerate(faces.tolist()):
        for first, second in zip(face, (*face[1:], face[0]), strict=True):
            edge = _canonical_edge(int(first), int(second))
            direction = 1 if (int(first), int(second)) == edge else -1
            edge_owners.setdefault(edge, []).append((face_index, direction))
    manifold = all(
        len(owners) <= 2 and (len(owners) != 2 or owners[0][1] != owners[1][1])
        for owners in edge_owners.values()
    )
    adjacency: list[set[int]] = [set() for _ in range(len(faces))]
    for owners in edge_owners.values():
        if len(owners) == 2:
            first, second = owners[0][0], owners[1][0]
            adjacency[first].add(second)
            adjacency[second].add(first)
    components = 0
    unseen = set(range(len(faces)))
    while unseen:
        components += 1
        pending = [unseen.pop()]
        while pending:
            face = pending.pop()
            neighbours = adjacency[face].intersection(unseen)
            unseen.difference_update(neighbours)
            pending.extend(neighbours)
    boundary = tuple(
        sorted(
            (edge[0], edge[1], owners[0][1])
            for edge, owners in edge_owners.items()
            if len(owners) == 1
        )
    )
    return manifold, len(edge_owners), components, boundary, frozenset(edge_owners)


def _oriented_quad(first: np.ndarray, second: np.ndarray) -> tuple[int, int, int, int] | None:
    shared = [int(vertex) for vertex in first if int(vertex) in set(second.tolist())]
    if len(shared) != 2:
        return None
    for local, start in enumerate(first.tolist()):
        end = int(first[(local + 1) % 3])
        if {int(start), end} != set(shared):
            continue
        opposite = next((int(vertex) for vertex in second if int(vertex) not in shared), None)
        if opposite is None:
            return None
        return int(first[(local + 2) % 3]), int(start), opposite, end
    return None


def _signed_pair_volume(vertices: np.ndarray, quad: tuple[int, int, int, int]) -> float:
    first, second, third, fourth = (vertices[index] for index in quad)
    ab = second - first
    ac = third - first
    ad = fourth - first
    cross_x = float(ab[1]) * float(ac[2]) - float(ab[2]) * float(ac[1])
    cross_y = float(ab[2]) * float(ac[0]) - float(ab[0]) * float(ac[2])
    cross_z = float(ab[0]) * float(ac[1]) - float(ab[1]) * float(ac[0])
    return cross_x * float(ad[0]) + cross_y * float(ad[1]) + cross_z * float(ad[2])


def _normalise_payloads(values: object, expected_count: int) -> tuple[tuple[Any, ...], bool]:
    if not isinstance(values, (tuple, list)) or len(values) != expected_count:
        return (), False
    normalized: list[Any] = []
    for value in values:
        scalar = value.item() if isinstance(value, np.generic) else value
        if isinstance(scalar, bool) or not isinstance(scalar, (Integral, str, type(None))):
            return (), False
        normalized.append(int(scalar) if isinstance(scalar, Integral) else scalar)
    return tuple(normalized), True


@dataclass(frozen=True, slots=True)
class StrictQuadPairPreflight:
    """Read-only evidence for a fixed-vertex two-triangle quad subset."""

    accepted: bool
    rejection_reasons: tuple[str, ...]
    source_vertices_hash: str | None
    candidate_vertices_hash: str | None
    source_triangles_hash: str | None
    quads_hash: str | None
    structural_facts: tuple[tuple[str, bool | int], ...]
    patch_payload_preserved: bool
    contract: str = "strict_quad_fixed_vertex_pair_preflight_l0"


def _python_structural_facts(
    source_vertices: np.ndarray,
    candidate_vertices: np.ndarray,
    source_triangles: np.ndarray,
    candidate_triangles: np.ndarray,
    quads: np.ndarray,
    pair_provenance: np.ndarray,
    feature_edges: np.ndarray,
) -> dict[str, bool | int]:
    coordinates_finite = bool(
        np.isfinite(source_vertices).all() and np.isfinite(candidate_vertices).all()
    )
    vertices_exact = (
        source_vertices.shape == candidate_vertices.shape
        and source_vertices.tobytes() == candidate_vertices.tobytes()
    )
    source_indices_valid = bool(
        len(source_triangles)
        and (source_triangles >= 0).all()
        and (source_triangles < len(source_vertices)).all()
        and all(len(set(row.tolist())) == 3 for row in source_triangles)
    )
    source_triangles_non_degenerate = bool(source_indices_valid)
    if source_triangles_non_degenerate:
        for triangle in source_triangles:
            first, second, third = (source_vertices[int(index)] for index in triangle)
            area_vector = np.cross(second - first, third - first)
            if (
                not np.isfinite(area_vector).all()
                or float(np.linalg.norm(area_vector)) <= np.finfo(float).tiny
            ):
                source_triangles_non_degenerate = False
                break
    quad_indices_valid = bool(
        len(quads) and (quads >= 0).all() and (quads < len(source_vertices)).all()
    )
    quads_degree_four = bool(
        quad_indices_valid and all(len(set(row.tolist())) == 4 for row in quads)
    )
    provenance_complete = bool(
        len(pair_provenance) == len(quads) and len(source_triangles) == 2 * len(quads)
    )
    pair_ordered = True
    consumed: set[int] = set()
    previous: tuple[int, int] | None = None
    if provenance_complete:
        for row in pair_provenance.tolist():
            pair = (int(row[0]), int(row[1]))
            if pair[0] < 0 or pair[1] >= len(source_triangles) or pair[0] >= pair[1]:
                provenance_complete = False
                continue
            if previous is not None and pair <= previous:
                pair_ordered = False
            if pair[0] in consumed or pair[1] in consumed:
                provenance_complete = False
            consumed.update(pair)
            previous = pair
        provenance_complete = provenance_complete and consumed == set(range(len(source_triangles)))
    pair_quads_exact = bool(source_indices_valid and quad_indices_valid and provenance_complete)
    pairs_coplanar = bool(pair_quads_exact)
    if pair_quads_exact:
        for index, pair in enumerate(pair_provenance.tolist()):
            expected = _oriented_quad(
                source_triangles[int(pair[0])], source_triangles[int(pair[1])]
            )
            if expected is None or tuple(int(value) for value in quads[index]) != expected:
                pair_quads_exact = False
                break
            if _signed_pair_volume(source_vertices, expected) != 0.0:
                pairs_coplanar = False
    source_manifold = quad_manifold = False
    source_edge_count = quad_edge_count = source_components = quad_components = 0
    source_boundary: tuple[tuple[int, int, int], ...] = ()
    quad_boundary: tuple[tuple[int, int, int], ...] = ()
    source_edges: frozenset[tuple[int, int]] = frozenset()
    quad_edges: frozenset[tuple[int, int]] = frozenset()
    if source_indices_valid and quad_indices_valid:
        source_manifold, source_edge_count, source_components, source_boundary, source_edges = (
            _topology(source_triangles)
        )
        quad_manifold, quad_edge_count, quad_components, quad_boundary, quad_edges = _topology(
            quads
        )
    boundary_equal = source_boundary == quad_boundary
    features_preserved = True
    for first, second in feature_edges.tolist():
        edge = _canonical_edge(int(first), int(second))
        if first == second or edge not in source_edges or edge not in quad_edges:
            features_preserved = False
    source_euler = len(source_vertices) - source_edge_count + len(source_triangles)
    quad_euler = len(source_vertices) - quad_edge_count + len(quads)
    candidate_triangles_empty = len(candidate_triangles) == 0
    topology_preserved = bool(
        source_manifold
        and quad_manifold
        and boundary_equal
        and source_components == quad_components
        and source_euler == quad_euler
    )
    valid = bool(
        coordinates_finite
        and vertices_exact
        and source_indices_valid
        and source_triangles_non_degenerate
        and quad_indices_valid
        and quads_degree_four
        and len(quads) > 0
        and candidate_triangles_empty
        and provenance_complete
        and pair_ordered
        and pair_quads_exact
        and pairs_coplanar
        and features_preserved
        and topology_preserved
    )
    return {
        "valid": valid,
        "coordinates_finite": coordinates_finite,
        "vertices_exact": vertices_exact,
        "source_triangles_non_degenerate": source_triangles_non_degenerate,
        "candidate_triangles_empty": candidate_triangles_empty,
        "quads_degree_four": quads_degree_four,
        "provenance_complete": provenance_complete and pair_ordered,
        "pair_quads_exact": pair_quads_exact,
        "pairs_coplanar": pairs_coplanar,
        "source_manifold": source_manifold,
        "quad_manifold": quad_manifold,
        "boundary_equal": boundary_equal,
        "features_preserved": features_preserved,
        "source_component_count": source_components,
        "quad_component_count": quad_components,
        "source_euler_characteristic": source_euler,
        "quad_euler_characteristic": quad_euler,
    }


def _native_facts_or_fail_closed(
    expected: dict[str, bool | int],
    arrays: tuple[np.ndarray, ...],
) -> None:
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "strict_quad_pair_preflight"):
        return
    result = native.strict_quad_pair_preflight(*arrays)
    if not isinstance(result, dict) or set(result) != set(_STRUCTURAL_KEYS):
        raise RuntimeError("native strict_quad_pair_preflight returned malformed audit")
    for key in _STRUCTURAL_KEYS:
        value = result[key]
        if key.endswith("count") or key.endswith("characteristic"):
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise RuntimeError("native strict_quad_pair_preflight returned malformed audit")
        elif not isinstance(value, bool):
            raise RuntimeError("native strict_quad_pair_preflight returned malformed audit")
    if {
        key: int(value) if isinstance(value, Integral) and not isinstance(value, bool) else value
        for key, value in result.items()
    } != expected:
        raise RuntimeError("native strict_quad_pair_preflight disagrees with Python oracle")


def diagnose_strict_quad_pair_preflight(
    source_vertices: object,
    candidate_vertices: object,
    source_triangles: object,
    candidate_triangles: object,
    quads: object,
    pair_provenance: object,
    feature_edges: object,
    *,
    source_patch_ids: object,
    candidate_quad_patch_ids: object,
) -> StrictQuadPairPreflight:
    """Diagnose one strict fixed-vertex pair product without producing it."""
    try:
        arrays = (
            _points(source_vertices, "source_vertices"),
            _points(candidate_vertices, "candidate_vertices"),
            _indices(source_triangles, 3, "source_triangles"),
            _indices(candidate_triangles, 3, "candidate_triangles"),
            _indices(quads, 4, "quads"),
            _indices(pair_provenance, 2, "pair_provenance"),
            _indices(feature_edges, 2, "feature_edges"),
        )
    except ValueError as exc:
        return StrictQuadPairPreflight(False, (str(exc),), None, None, None, None, (), False)
    facts = _python_structural_facts(*arrays)
    if strict_quad_pair_preflight_cpp23_enabled():
        _native_facts_or_fail_closed(facts, arrays)
    source_patches, source_patches_valid = _normalise_payloads(source_patch_ids, len(arrays[2]))
    quad_patches, quad_patches_valid = _normalise_payloads(candidate_quad_patch_ids, len(arrays[4]))
    patch_payload_preserved = bool(source_patches_valid and quad_patches_valid)
    if patch_payload_preserved and facts["provenance_complete"]:
        for quad_index, pair in enumerate(arrays[5]):
            first, second = int(pair[0]), int(pair[1])
            if (
                source_patches[first] != source_patches[second]
                or quad_patches[quad_index] != source_patches[first]
            ):
                patch_payload_preserved = False
                break
    reasons = [key for key, value in facts.items() if isinstance(value, bool) and not value]
    if not patch_payload_preserved:
        reasons.append("patch_payload_preserved")
    return StrictQuadPairPreflight(
        accepted=bool(facts["valid"] and patch_payload_preserved),
        rejection_reasons=tuple(reasons),
        source_vertices_hash=_hash(arrays[0]),
        candidate_vertices_hash=_hash(arrays[1]),
        source_triangles_hash=_hash(arrays[2]),
        quads_hash=_hash(arrays[4]),
        structural_facts=tuple((key, facts[key]) for key in _STRUCTURAL_KEYS),
        patch_payload_preserved=patch_payload_preserved,
    )
