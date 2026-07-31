"""Fast topology audit used to decide whether native tet needs C++ rescue."""

from __future__ import annotations

from dataclasses import dataclass, replace
from numbers import Integral

import numpy as np
import numpy.typing as npt

type _FloatArray = npt.NDArray[np.float64]
type _IntArray = npt.NDArray[np.int64]
type _BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class TetBoundaryAudit:
    n_tets: int
    n_boundary_faces: int
    n_open_edges: int
    n_nonmanifold_edges: int
    n_nonmanifold_faces: int
    n_boundary_components: int
    n_duplicate_tets: int
    n_degenerate_tets: int
    n_inverted_tets: int
    n_internal_faces: int = 0
    n_same_side_internal_faces: int = 0
    n_ambiguous_internal_faces: int = 0

    @property
    def valid(self) -> bool:
        """Whether every reported boundary component is locally manifold.

        Component cardinality is a source-domain contract, not a local mesh
        validity condition.  A valid tetrahedral mesh may contain multiple
        disconnected bodies.  Call :func:`audit_source_topology` when source
        component preservation is required.
        """
        return (
            self.n_tets > 0
            and self.n_boundary_faces > 0
            and self.n_open_edges == 0
            and self.n_nonmanifold_edges == 0
            and self.n_nonmanifold_faces == 0
            and self.n_boundary_components > 0
            and self.n_duplicate_tets == 0
            and self.n_degenerate_tets == 0
            and self.n_inverted_tets == 0
            and self.n_same_side_internal_faces == 0
            and self.n_ambiguous_internal_faces == 0
        )


@dataclass(frozen=True)
class InternalFaceSidednessAudit:
    """Embedding validity of two tetrahedra incident to one triangular face."""

    n_internal_faces: int
    n_opposite_side_internal_faces: int
    n_same_side_internal_faces: int
    n_ambiguous_internal_faces: int
    # These three fields partition the legacy ambiguous count.  They are
    # diagnostic-only: ``valid`` and every writer/refusal decision continue to
    # use ``n_ambiguous_internal_faces`` unchanged.
    n_predicate_zero_internal_faces: int = 0
    n_floor_only_same_side_internal_faces: int = 0
    n_floor_only_opposite_side_internal_faces: int = 0

    @property
    def valid(self) -> bool:
        return bool(
            self.n_same_side_internal_faces == 0
            and self.n_ambiguous_internal_faces == 0
        )


@dataclass(frozen=True)
class SourceComponentBijectionAudit:
    """Exact components plus complete planar-patch boundary provenance."""

    n_source_components: int
    n_candidate_boundary_components: int
    n_source_surface_vertices: int
    n_source_vertices_on_boundary: int
    n_missing_source_vertices: int
    n_matched_source_components: int
    n_mixed_candidate_components: int
    n_split_source_components: int
    n_unanchored_candidate_components: int
    n_unknown_source_vertex_anchors: int
    n_source_faces: int
    n_source_faces_on_boundary: int
    n_missing_source_faces: int
    n_candidate_boundary_faces: int
    n_owned_candidate_faces: int
    n_unowned_candidate_faces: int
    n_source_planar_patches: int
    n_uncovered_source_patches: int
    n_area_mismatch_patches: int
    n_feature_boundary_mismatches: int
    n_overlap_pairs: int
    source_faces_preserved: bool
    bijective: bool


@dataclass(frozen=True)
class SourceTopologyAudit:
    """Source-aware strict topology certificate for a tet candidate."""

    boundary: TetBoundaryAudit
    components: SourceComponentBijectionAudit

    @property
    def valid(self) -> bool:
        return bool(
            self.boundary.valid
            and self.components.bijective
            and self.components.source_faces_preserved
        )


@dataclass(frozen=True)
class SourcePrefixRoundoffRestore:
    """Bounded bitwise restoration of immutable native source vertices."""

    points: np.ndarray
    applied: bool
    reason: str
    restored_count: int
    max_delta: float
    cap: float


_COMPONENT_COUNT_FIELDS = (
    "n_source_components",
    "n_candidate_boundary_components",
    "n_source_surface_vertices",
    "n_source_vertices_on_boundary",
    "n_missing_source_vertices",
    "n_matched_source_components",
    "n_mixed_candidate_components",
    "n_split_source_components",
    "n_unanchored_candidate_components",
    "n_unknown_source_vertex_anchors",
    "n_source_faces",
    "n_source_faces_on_boundary",
    "n_missing_source_faces",
    "n_candidate_boundary_faces",
    "n_owned_candidate_faces",
    "n_unowned_candidate_faces",
    "n_source_planar_patches",
    "n_uncovered_source_patches",
    "n_area_mismatch_patches",
    "n_feature_boundary_mismatches",
    "n_overlap_pairs",
)


def _component_index_matrix(
    values: np.ndarray,
    *,
    columns: int,
    name: str,
) -> _IntArray:
    if not isinstance(values, np.ndarray) or values.dtype != np.dtype(np.int64):
        raise TypeError(f"{name} must be an ndarray with dtype int64")
    if values.ndim != 2 or values.shape[1:] != (columns,):
        raise ValueError(f"{name} must have shape (N, {columns})")
    return np.ascontiguousarray(values, dtype=np.int64)


def _component_point_matrix(values: np.ndarray, *, name: str) -> _FloatArray:
    if not isinstance(values, np.ndarray) or values.dtype != np.dtype(np.float64):
        raise TypeError(f"{name} must be an ndarray with dtype float64")
    if values.ndim != 2 or values.shape[1:] != (3,):
        raise ValueError(f"{name} must have shape (N, 3)")
    if values.shape[0] == 0:
        raise ValueError(f"{name} must not be empty")
    if not bool(np.all(np.isfinite(values))):
        raise ValueError(f"{name} coordinates must be finite")
    return np.ascontiguousarray(values, dtype=np.float64)


def _component_count(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise RuntimeError(f"native source-component audit returned invalid {name}")
    result = int(value)
    if result < 0:
        raise RuntimeError(f"native source-component audit returned negative {name}")
    return result


def _face_component_roots(faces: _IntArray) -> _IntArray:
    """Independent Python union-find oracle over shared face edges."""
    parent = np.arange(faces.shape[0], dtype=np.int64)

    def find(item: int) -> int:
        while int(parent[item]) != item:
            parent[item] = parent[int(parent[item])]
            item = int(parent[item])
        return item

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    first_owner: dict[tuple[int, int], int] = {}
    for face_index, face in enumerate(faces):
        for left, right in ((0, 1), (1, 2), (0, 2)):
            first = int(face[left])
            second = int(face[right])
            edge = (first, second) if first < second else (second, first)
            owner = first_owner.setdefault(edge, face_index)
            union(owner, face_index)
    return np.asarray([find(index) for index in range(len(faces))], dtype=np.int64)


def _candidate_boundary_faces(tets: _IntArray) -> _IntArray:
    faces = np.concatenate(
        [
            tets[:, (0, 1, 2)],
            tets[:, (0, 1, 3)],
            tets[:, (0, 2, 3)],
            tets[:, (1, 2, 3)],
        ],
        axis=0,
    )
    canonical = np.sort(faces, axis=1)
    unique, counts = np.unique(canonical, axis=0, return_counts=True)
    return unique[counts == 1]


def _audit_source_component_bijection_python(
    source_points: _FloatArray,
    source_faces: _IntArray,
    candidate_points: _FloatArray,
    tets: _IntArray,
) -> SourceComponentBijectionAudit:
    source_vertex_count = int(source_points.shape[0])
    candidate_vertex_count = int(candidate_points.shape[0])
    if source_faces.shape[0] == 0:
        raise ValueError("source_faces must not be empty")
    if tets.shape[0] == 0:
        raise ValueError("tets must not be empty")
    if np.any(source_faces < 0) or np.any(source_faces >= source_vertex_count):
        raise ValueError("source_faces vertex index out of range")
    if np.any(tets < 0) or np.any(tets >= candidate_vertex_count):
        raise ValueError("tets vertex index out of range")
    if np.any(
        (source_faces[:, 0] == source_faces[:, 1])
        | (source_faces[:, 0] == source_faces[:, 2])
        | (source_faces[:, 1] == source_faces[:, 2])
    ):
        raise ValueError("source_faces contains a repeated vertex")
    if np.any(
        (tets[:, 0] == tets[:, 1])
        | (tets[:, 0] == tets[:, 2])
        | (tets[:, 0] == tets[:, 3])
        | (tets[:, 1] == tets[:, 2])
        | (tets[:, 1] == tets[:, 3])
        | (tets[:, 2] == tets[:, 3])
    ):
        raise ValueError("tets contains a repeated vertex")
    canonical_source = np.sort(source_faces, axis=1)
    if np.unique(canonical_source, axis=0).shape[0] != source_faces.shape[0]:
        raise ValueError("source_faces contains a duplicate face")

    source_coordinate_to_vertex: dict[tuple[float, float, float], int] = {}
    for vertex, point in enumerate(source_points):
        key = (float(point[0]), float(point[1]), float(point[2]))
        if key in source_coordinate_to_vertex:
            raise ValueError("source_points contains ambiguous duplicate coordinates")
        source_coordinate_to_vertex[key] = vertex

    candidate_provenance: _IntArray = np.empty(candidate_vertex_count, dtype=np.int64)
    matched_source_coordinates: set[tuple[float, float, float]] = set()
    for vertex, point in enumerate(candidate_points):
        key = (float(point[0]), float(point[1]), float(point[2]))
        source_vertex = source_coordinate_to_vertex.get(key)
        if source_vertex is None:
            candidate_provenance[vertex] = source_vertex_count + vertex
            continue
        if key in matched_source_coordinates:
            raise ValueError("candidate_points duplicates a source coordinate")
        matched_source_coordinates.add(key)
        candidate_provenance[vertex] = source_vertex

    raw_boundary_faces = _candidate_boundary_faces(tets)
    boundary_faces = np.sort(candidate_provenance[raw_boundary_faces], axis=1)
    from core.generator.native_tet.source_facet_provenance import (
        audit_source_facet_provenance_python,
    )

    facet_report = audit_source_facet_provenance_python(
        source_points,
        source_faces,
        candidate_points,
        raw_boundary_faces,
    )
    if boundary_faces.shape[0] == 0:
        return SourceComponentBijectionAudit(
            n_source_components=0,
            n_candidate_boundary_components=0,
            n_source_surface_vertices=0,
            n_source_vertices_on_boundary=0,
            n_missing_source_vertices=0,
            n_matched_source_components=0,
            n_mixed_candidate_components=0,
            n_split_source_components=0,
            n_unanchored_candidate_components=0,
            n_unknown_source_vertex_anchors=0,
            **facet_report,
            bijective=False,
        )

    source_roots = _face_component_roots(canonical_source)
    candidate_roots = _face_component_roots(boundary_faces)
    unique_source_roots = np.unique(source_roots)
    unique_candidate_roots = np.unique(candidate_roots)

    source_component_for_vertex: _IntArray = np.full(source_vertex_count, -1, dtype=np.int64)
    source_surface_vertex: _BoolArray = np.zeros(source_vertex_count, dtype=np.bool_)
    for face_index, face in enumerate(canonical_source):
        root = int(source_roots[face_index])
        for raw_vertex in face:
            vertex = int(raw_vertex)
            source_surface_vertex[vertex] = True
            previous = int(source_component_for_vertex[vertex])
            if previous == -1:
                source_component_for_vertex[vertex] = root
            elif previous != root:
                raise ValueError("source vertex belongs to multiple edge-connected components")

    source_vertex_on_boundary: _BoolArray = np.zeros(source_vertex_count, dtype=np.bool_)
    component_pairs: set[tuple[int, int]] = set()
    anchored_candidate_roots: set[int] = set()
    unknown_source_vertices: set[int] = set()
    for face_index, face in enumerate(boundary_faces):
        candidate_root = int(candidate_roots[face_index])
        anchored = False
        for raw_vertex in face:
            vertex = int(raw_vertex)
            if vertex >= source_vertex_count:
                continue
            source_root = int(source_component_for_vertex[vertex])
            if source_root == -1:
                unknown_source_vertices.add(vertex)
                continue
            source_vertex_on_boundary[vertex] = True
            component_pairs.add((source_root, candidate_root))
            anchored = True
        if anchored:
            anchored_candidate_roots.add(candidate_root)

    source_to_candidate: dict[int, set[int]] = {}
    candidate_to_source: dict[int, set[int]] = {}
    for source_root, candidate_root in component_pairs:
        source_to_candidate.setdefault(source_root, set()).add(candidate_root)
        candidate_to_source.setdefault(candidate_root, set()).add(source_root)

    n_source_components = int(unique_source_roots.size)
    n_candidate_components = int(unique_candidate_roots.size)
    n_source_surface_vertices = int(source_surface_vertex.sum())
    n_source_vertices_on_boundary = int(source_vertex_on_boundary.sum())
    n_missing_source_vertices = n_source_surface_vertices - n_source_vertices_on_boundary
    n_matched_source_components = len(source_to_candidate)
    n_mixed_candidate_components = sum(
        len(source_roots_for_candidate) > 1
        for source_roots_for_candidate in candidate_to_source.values()
    )
    n_split_source_components = sum(
        len(candidate_roots_for_source) > 1
        for candidate_roots_for_source in source_to_candidate.values()
    )
    n_unanchored_candidate_components = n_candidate_components - len(anchored_candidate_roots)
    n_unknown_source_vertex_anchors = len(unknown_source_vertices)
    bijective = bool(
        n_source_components > 0
        and n_source_components == n_candidate_components
        and n_source_components == n_matched_source_components
        and n_missing_source_vertices == 0
        and n_mixed_candidate_components == 0
        and n_split_source_components == 0
        and n_unanchored_candidate_components == 0
        and n_unknown_source_vertex_anchors == 0
    )
    return SourceComponentBijectionAudit(
        n_source_components=n_source_components,
        n_candidate_boundary_components=n_candidate_components,
        n_source_surface_vertices=n_source_surface_vertices,
        n_source_vertices_on_boundary=n_source_vertices_on_boundary,
        n_missing_source_vertices=n_missing_source_vertices,
        n_matched_source_components=n_matched_source_components,
        n_mixed_candidate_components=n_mixed_candidate_components,
        n_split_source_components=n_split_source_components,
        n_unanchored_candidate_components=n_unanchored_candidate_components,
        n_unknown_source_vertex_anchors=n_unknown_source_vertex_anchors,
        **facet_report,
        bijective=bijective,
    )


def _validated_native_component_result(
    values: object,
    *,
    source_face_count: int,
    tet_count: int,
    source_vertex_count: int,
) -> SourceComponentBijectionAudit:
    if not isinstance(values, dict):
        raise RuntimeError("native source-component audit must return a dict")
    counts = {
        name: _component_count(values.get(name), name=name) for name in _COMPONENT_COUNT_FIELDS
    }
    raw_bijective = values.get("bijective")
    if type(raw_bijective) is not bool:
        raise RuntimeError("native source-component audit returned invalid bijective")
    raw_source_faces_preserved = values.get("source_faces_preserved")
    if type(raw_source_faces_preserved) is not bool:
        raise RuntimeError("native source-component audit returned invalid source_faces_preserved")
    if counts["n_source_vertices_on_boundary"] > counts["n_source_surface_vertices"]:
        raise RuntimeError("native source-component audit returned inconsistent vertices")
    if (
        counts["n_source_components"] > source_face_count
        or counts["n_candidate_boundary_components"] > 4 * tet_count
        or counts["n_source_surface_vertices"] > source_vertex_count
        or counts["n_matched_source_components"] > counts["n_source_components"]
        or counts["n_mixed_candidate_components"] > counts["n_candidate_boundary_components"]
        or counts["n_split_source_components"] > counts["n_source_components"]
        or counts["n_unanchored_candidate_components"] > counts["n_candidate_boundary_components"]
        or counts["n_unknown_source_vertex_anchors"] > source_vertex_count
        or counts["n_source_faces"] != source_face_count
        or counts["n_source_faces_on_boundary"] > counts["n_source_faces"]
        or counts["n_candidate_boundary_faces"] > 4 * tet_count
        or counts["n_owned_candidate_faces"] > counts["n_candidate_boundary_faces"]
        or counts["n_unowned_candidate_faces"] > counts["n_candidate_boundary_faces"]
        or counts["n_source_planar_patches"] > source_face_count
        or counts["n_uncovered_source_patches"] > counts["n_source_planar_patches"]
        or counts["n_area_mismatch_patches"] > counts["n_source_planar_patches"]
        or counts["n_feature_boundary_mismatches"] > counts["n_source_planar_patches"]
    ):
        raise RuntimeError("native source-component audit returned out-of-range counts")
    if counts["n_missing_source_vertices"] != (
        counts["n_source_surface_vertices"] - counts["n_source_vertices_on_boundary"]
    ):
        raise RuntimeError("native source-component audit returned inconsistent missing count")
    if counts["n_missing_source_faces"] != (
        counts["n_source_faces"] - counts["n_source_faces_on_boundary"]
    ):
        raise RuntimeError("native source-component audit returned inconsistent missing face count")
    if (
        counts["n_owned_candidate_faces"] + counts["n_unowned_candidate_faces"]
        != counts["n_candidate_boundary_faces"]
    ):
        raise RuntimeError("native source-component audit returned inconsistent owned face count")
    candidate_face_count = counts["n_candidate_boundary_faces"]
    max_overlap_pairs = candidate_face_count * max(0, candidate_face_count - 1) // 2
    if counts["n_overlap_pairs"] > max_overlap_pairs:
        raise RuntimeError("native source-component audit returned inconsistent overlap count")
    exact_fast_path = bool(
        counts["n_source_faces_on_boundary"] == counts["n_source_faces"]
        and candidate_face_count == counts["n_source_faces"]
    )
    if exact_fast_path:
        if (
            counts["n_owned_candidate_faces"] != candidate_face_count
            or counts["n_unowned_candidate_faces"] != 0
            or counts["n_source_planar_patches"] != 0
            or counts["n_uncovered_source_patches"] != 0
            or counts["n_area_mismatch_patches"] != 0
            or counts["n_feature_boundary_mismatches"] != 0
            or counts["n_overlap_pairs"] != 0
        ):
            raise RuntimeError(
                "native source-component audit returned inconsistent exact facet report"
            )
    elif candidate_face_count > 0 and counts["n_source_planar_patches"] == 0:
        raise RuntimeError(
            "native source-component audit returned missing planar patch census"
        )
    expected_bijective = bool(
        counts["n_source_components"] > 0
        and counts["n_source_components"]
        == counts["n_candidate_boundary_components"]
        == counts["n_matched_source_components"]
        and counts["n_missing_source_vertices"] == 0
        and counts["n_mixed_candidate_components"] == 0
        and counts["n_split_source_components"] == 0
        and counts["n_unanchored_candidate_components"] == 0
        and counts["n_unknown_source_vertex_anchors"] == 0
    )
    if raw_bijective != expected_bijective:
        raise RuntimeError("native source-component audit returned inconsistent verdict")
    expected_source_faces_preserved = bool(
        counts["n_source_faces"] > 0
        and counts["n_candidate_boundary_faces"] > 0
        and counts["n_unowned_candidate_faces"] == 0
        and counts["n_uncovered_source_patches"] == 0
        and counts["n_area_mismatch_patches"] == 0
        and counts["n_feature_boundary_mismatches"] == 0
        and counts["n_overlap_pairs"] == 0
    )
    if raw_source_faces_preserved != expected_source_faces_preserved:
        raise RuntimeError(
            "native source-component audit returned inconsistent source face verdict"
        )
    return SourceComponentBijectionAudit(
        **counts,
        source_faces_preserved=raw_source_faces_preserved,
        bijective=raw_bijective,
    )


def audit_source_component_bijection(
    source_points: np.ndarray,
    source_faces: np.ndarray,
    candidate_points: np.ndarray,
    tets: np.ndarray,
) -> SourceComponentBijectionAudit:
    """Require exact components and complete planar-patch facet provenance."""
    source = _component_point_matrix(source_points, name="source_points")
    faces = _component_index_matrix(source_faces, columns=3, name="source_faces")
    candidate = _component_point_matrix(candidate_points, name="candidate_points")
    cells = _component_index_matrix(tets, columns=4, name="tets")

    from core.utils.native_extensions import load_native_tet_predicates

    native = load_native_tet_predicates()
    if native is not None and hasattr(native, "audit_source_component_bijection"):
        values = native.audit_source_component_bijection(
            source,
            faces,
            candidate,
            cells,
        )
        return _validated_native_component_result(
            values,
            source_face_count=faces.shape[0],
            tet_count=cells.shape[0],
            source_vertex_count=source.shape[0],
        )
    return _audit_source_component_bijection_python(
        source,
        faces,
        candidate,
        cells,
    )


def audit_source_topology(
    source_points: np.ndarray,
    source_faces: np.ndarray,
    candidate_points: np.ndarray,
    tets: np.ndarray,
    *,
    relative_volume_tolerance: float = 1e-12,
) -> SourceTopologyAudit:
    """Combine local validity with source component and facet provenance.

    ``TetBoundaryAudit.valid`` intentionally accepts any positive number of
    closed components.  This source-aware certificate supplies the missing
    global contract: every source component must map bijectively to exactly
    one output boundary component through immutable source coordinates.  Each
    output boundary facet must either retain an exact source face or have one
    complete, non-overlapping planar-patch owner.  Non-coplanar replacement is
    rejected.
    """
    boundary = audit_tet_boundary(
        candidate_points,
        tets,
        relative_volume_tolerance=relative_volume_tolerance,
    )
    components = audit_source_component_bijection(
        source_points,
        source_faces,
        candidate_points,
        tets,
    )
    return SourceTopologyAudit(boundary=boundary, components=components)


def restore_source_prefix_roundoff(
    source_points: np.ndarray,
    source_faces: np.ndarray,
    candidate_points: np.ndarray,
    tets: np.ndarray,
    *,
    prefix_contract: bool,
    epsilon_multiplier: float = 32.0,
) -> SourcePrefixRoundoffRestore:
    """Restore source-surface prefix coordinates only within machine roundoff.

    Native generation preserves source vertex indices as an immutable prefix,
    but arithmetic can perturb coordinates by a few ulps.  Exact-coordinate
    provenance must not be weakened to a tolerance match.  Instead, this
    transaction restores the original bits only when every referenced source
    surface id is still a boundary id and every coordinate delta is below a
    scale-relative, predeclared machine-roundoff cap.  Reordered external P4C
    candidates must call this with ``prefix_contract=False``.
    """
    source = _component_point_matrix(source_points, name="source_points")
    faces = _component_index_matrix(source_faces, columns=3, name="source_faces")
    candidate = _component_point_matrix(candidate_points, name="candidate_points")
    cells = _component_index_matrix(tets, columns=4, name="tets")
    if not np.isfinite(epsilon_multiplier) or epsilon_multiplier < 0.0:
        raise ValueError("epsilon_multiplier must be finite and non-negative")

    float64_max = float(np.finfo(np.float64).max)
    maximum_coordinate = float(np.max(np.abs(source)))
    if maximum_coordinate == 0.0:
        diagonal = 0.0
    else:
        # Normalize before subtraction and norm so finite, opposite-sign
        # coordinates near float64 max cannot overflow the bbox diagonal.
        normalized_extent = np.ptp(source / maximum_coordinate, axis=0)
        normalized_diagonal = float(np.linalg.norm(normalized_extent))
        diagonal = (
            float64_max
            if normalized_diagonal > 0.0
            and maximum_coordinate > float64_max / normalized_diagonal
            else maximum_coordinate * normalized_diagonal
        )
    tiny = float(np.finfo(np.float64).tiny)
    epsilon = float(np.finfo(np.float64).eps)
    scale = max(diagonal, maximum_coordinate, tiny)
    cap_factor = epsilon_multiplier * epsilon
    if cap_factor > float64_max / scale:
        raise ValueError("roundoff cap must be finite")
    cap = cap_factor * scale
    if not prefix_contract:
        return SourcePrefixRoundoffRestore(
            candidate, False, "prefix_contract_disabled", 0, 0.0, cap
        )

    source_ids = np.unique(faces)
    if source_ids.size == 0:
        return SourcePrefixRoundoffRestore(
            candidate, False, "source_surface_empty", 0, 0.0, cap
        )
    if int(source_ids.min()) < 0 or int(source_ids.max()) >= source.shape[0]:
        raise ValueError("source_faces vertex index out of range")
    if candidate.shape[0] < source.shape[0]:
        return SourcePrefixRoundoffRestore(
            candidate, False, "candidate_prefix_too_short", 0, 0.0, cap
        )
    if cells.shape[0] == 0:
        return SourcePrefixRoundoffRestore(
            candidate, False, "candidate_tets_empty", 0, 0.0, cap
        )
    if np.any(cells < 0) or np.any(cells >= candidate.shape[0]):
        raise ValueError("tets vertex index out of range")

    boundary_ids = np.unique(_candidate_boundary_faces(cells))
    if not bool(np.all(np.isin(source_ids, boundary_ids))):
        return SourcePrefixRoundoffRestore(
            candidate, False, "source_prefix_not_on_boundary", 0, 0.0, cap
        )

    candidate_source = candidate[source_ids]
    original_source = source[source_ids]
    deltas = np.abs(candidate_source - original_source)
    max_delta = float(np.max(deltas))
    changed = np.any(
        candidate_source.view(np.uint64) != original_source.view(np.uint64),
        axis=1,
    )
    restored_count = int(np.count_nonzero(changed))
    if max_delta > cap:
        return SourcePrefixRoundoffRestore(
            candidate,
            False,
            "source_prefix_delta_exceeds_roundoff_cap",
            0,
            max_delta,
            cap,
        )
    if restored_count == 0:
        return SourcePrefixRoundoffRestore(
            candidate, False, "source_prefix_already_exact", 0, 0.0, cap
        )

    restored = candidate.copy()
    restored[source_ids] = source[source_ids]
    return SourcePrefixRoundoffRestore(
        restored,
        True,
        "source_prefix_roundoff_restored",
        restored_count,
        max_delta,
        cap,
    )


@dataclass(frozen=True)
class DuplicateTetGroupRepair:
    """Result of a fail-closed exact-duplicate tetrahedron cleanup.

    A repeated tetrahedron represents the same closed volume twice.  It can
    create three-or-more face incidences even when every retained tetrahedron
    is valid.  The cleanup removes *all* members of a repeated group only if
    doing so leaves the boundary exactly unchanged and restores the strict
    topology contract.  Otherwise the original candidate is returned.
    """

    tets: np.ndarray
    applied: bool
    n_duplicate_groups: int
    n_removed_tets: int
    reason: str
    boundary_preserved: bool
    before_audit: TetBoundaryAudit
    candidate_audit: TetBoundaryAudit


def has_strict_writer_topology(points: np.ndarray, tets: np.ndarray) -> bool:
    """Strict writer face contract; disconnected components remain supported."""
    audit = audit_tet_boundary(points, tets)
    return bool(
        audit.n_nonmanifold_faces == 0
        and audit.n_duplicate_tets == 0
        and audit.n_degenerate_tets == 0
        and audit.n_same_side_internal_faces == 0
        and audit.n_ambiguous_internal_faces == 0
    )


def drop_duplicate_tet_groups_if_strict_topology_restored(
    points: np.ndarray,
    tets: np.ndarray,
) -> DuplicateTetGroupRepair:
    """Remove exact duplicate groups only after full boundary/topology proof.

    Keeping one member of a duplicate group is insufficient when that cell is
    the extra incidence on a face.  Dropping every member is safe only when
    the candidate keeps exactly the same exterior boundary and has no open or
    non-manifold entities.  This is intentionally not a generic non-manifold
    repair: any residual three-plus face incidence remains a strict failure.
    """
    tet = np.asarray(tets, dtype=np.int64)
    before = audit_tet_boundary(points, tet)
    if tet.shape[0] == 0:
        return DuplicateTetGroupRepair(
            tets=tet,
            applied=False,
            n_duplicate_groups=0,
            n_removed_tets=0,
            reason="empty_tet_input",
            boundary_preserved=True,
            before_audit=before,
            candidate_audit=before,
        )

    canonical = np.sort(tet, axis=1)
    _, inverse, counts = np.unique(
        canonical,
        axis=0,
        return_inverse=True,
        return_counts=True,
    )
    duplicate_groups = int(np.count_nonzero(counts > 1))
    if duplicate_groups == 0:
        return DuplicateTetGroupRepair(
            tets=tet,
            applied=False,
            n_duplicate_groups=0,
            n_removed_tets=0,
            reason="no_exact_duplicate_tet_groups",
            boundary_preserved=True,
            before_audit=before,
            candidate_audit=before,
        )

    keep = counts[inverse] == 1
    candidate = tet[keep]
    candidate_audit = audit_tet_boundary(points, candidate)

    from core.generator.native_tet.near_wall import boundary_face_keys

    boundary_preserved = bool(boundary_face_keys(tet) == boundary_face_keys(candidate))
    topology_restored = bool(
        candidate_audit.n_tets > 0
        and candidate_audit.n_open_edges == 0
        and candidate_audit.n_nonmanifold_edges == 0
        and candidate_audit.n_nonmanifold_faces == 0
        and candidate_audit.n_duplicate_tets == 0
        and candidate_audit.n_degenerate_tets == 0
        and candidate_audit.n_same_side_internal_faces == 0
        and candidate_audit.n_ambiguous_internal_faces == 0
    )
    if not boundary_preserved:
        reason = "duplicate_group_drop_changes_boundary"
    elif not topology_restored:
        reason = "duplicate_group_drop_does_not_restore_strict_topology"
    else:
        reason = "exact_duplicate_groups_removed_with_boundary_preserved"

    return DuplicateTetGroupRepair(
        tets=candidate if boundary_preserved and topology_restored else tet,
        applied=bool(boundary_preserved and topology_restored),
        n_duplicate_groups=duplicate_groups,
        n_removed_tets=int((~keep).sum()),
        reason=reason,
        boundary_preserved=boundary_preserved,
        before_audit=before,
        candidate_audit=candidate_audit,
    )


def audit_internal_face_sidedness(
    points: np.ndarray,
    tets: np.ndarray,
    *,
    relative_volume_tolerance: float = 1e-12,
) -> InternalFaceSidednessAudit:
    """Prove that adjacent tetrahedra lie on opposite sides of their face.

    A positive-volume test for each tetrahedron is insufficient: two valid
    tetrahedra may share a face while placing both opposite apexes on the same
    side, geometrically overlapping each other.  Canonical face grouping finds
    exactly-two-cell faces; the existing robust ``orientation_signs`` predicate
    then classifies both apexes against the same ordered face.  Near-coplanar
    signs inside the scale-relative volume floor remain ambiguous and fail
    closed instead of being rounded into an accepted side.
    """
    pts = np.asarray(points, dtype=np.float64)
    tet = np.asarray(tets, dtype=np.int64)
    if tet.ndim != 2 or tet.shape[1:] != (4,):
        raise ValueError("tets must have shape (N, 4)")
    if pts.ndim != 2 or pts.shape[1:] != (3,):
        raise ValueError("points must have shape (N, 3)")
    if tet.size and (int(tet.min()) < 0 or int(tet.max()) >= len(pts)):
        raise ValueError("tet vertex index out of range")
    if tet.shape[0] == 0:
        return InternalFaceSidednessAudit(0, 0, 0, 0)

    faces = np.concatenate(
        [
            tet[:, (0, 1, 2)],
            tet[:, (0, 1, 3)],
            tet[:, (0, 2, 3)],
            tet[:, (1, 2, 3)],
        ],
        axis=0,
    )
    opposite = np.concatenate(
        [tet[:, 3], tet[:, 2], tet[:, 1], tet[:, 0]],
        axis=0,
    )
    canonical = np.sort(faces, axis=1)
    order = np.lexsort((canonical[:, 2], canonical[:, 1], canonical[:, 0]))
    sorted_faces = canonical[order]
    starts = np.r_[
        0,
        1 + np.flatnonzero(np.any(sorted_faces[1:] != sorted_faces[:-1], axis=1)),
    ]
    ends = np.r_[starts[1:], len(sorted_faces)]
    internal = (ends - starts) == 2
    internal_starts = starts[internal]
    n_internal = int(internal_starts.size)
    if n_internal == 0:
        return InternalFaceSidednessAudit(0, 0, 0, 0)

    first_rows = order[internal_starts]
    second_rows = order[internal_starts + 1]
    shared = canonical[first_rows]
    first_apex = opposite[first_rows]
    second_apex = opposite[second_rows]
    a = pts[shared[:, 0]]
    b = pts[shared[:, 1]]
    c = pts[shared[:, 2]]
    first_d = pts[first_apex]
    second_d = pts[second_apex]
    first_volume6 = np.einsum(
        "ij,ij->i",
        b - a,
        np.cross(c - a, first_d - a),
    )
    second_volume6 = np.einsum(
        "ij,ij->i",
        b - a,
        np.cross(c - a, second_d - a),
    )
    diagonal = max(
        float(np.linalg.norm(np.ptp(pts, axis=0))),
        float(np.finfo(np.float64).tiny),
    )
    volume_floor = max(0.0, float(relative_volume_tolerance)) * diagonal**3

    from core.generator.native_tet.validate import orientation_signs

    first_sign = orientation_signs(
        pts,
        np.column_stack((shared, first_apex)),
        tol=volume_floor,
    )
    second_sign = orientation_signs(
        pts,
        np.column_stack((shared, second_apex)),
        tol=volume_floor,
    )
    volume_floor_hit = (np.abs(first_volume6) <= volume_floor) | (
        np.abs(second_volume6) <= volume_floor
    )
    legacy_predicate_zero = (first_sign == 0) | (second_sign == 0)
    # Keep this exact legacy expression as the public strict contract.  The
    # categories below only expose why an already-ambiguous face was refused.
    ambiguous = volume_floor_hit | legacy_predicate_zero
    same_side = (~ambiguous) & (first_sign == second_sign)
    opposite_side = (~ambiguous) & (first_sign == -second_sign)
    if bool(np.any(ambiguous)):
        # ``first_sign``/``second_sign`` deliberately retain their historical
        # tolerance, because they define the public fail-closed contract.  A
        # second zero-tolerance query is observation-only: the NumPy fallback
        # can otherwise report a tolerance-induced zero that is
        # indistinguishable from a predicate-zero face in the legacy
        # aggregate.  Avoid this extra work on the common non-ambiguous path.
        classification_first_sign = orientation_signs(
            pts,
            np.column_stack((shared, first_apex)),
            tol=0.0,
        )
        classification_second_sign = orientation_signs(
            pts,
            np.column_stack((shared, second_apex)),
            tol=0.0,
        )
        predicate_zero = (classification_first_sign == 0) | (
            classification_second_sign == 0
        )
        floor_only = ambiguous & ~predicate_zero
        floor_only_same_side = floor_only & (
            classification_first_sign == classification_second_sign
        )
        floor_only_opposite_side = floor_only & (
            classification_first_sign == -classification_second_sign
        )
    else:
        predicate_zero = np.zeros(n_internal, dtype=bool)
        floor_only_same_side = np.zeros(n_internal, dtype=bool)
        floor_only_opposite_side = np.zeros(n_internal, dtype=bool)
    return InternalFaceSidednessAudit(
        n_internal_faces=n_internal,
        n_opposite_side_internal_faces=int(np.count_nonzero(opposite_side)),
        n_same_side_internal_faces=int(np.count_nonzero(same_side)),
        n_ambiguous_internal_faces=int(np.count_nonzero(ambiguous)),
        n_predicate_zero_internal_faces=int(np.count_nonzero(predicate_zero)),
        n_floor_only_same_side_internal_faces=int(
            np.count_nonzero(floor_only_same_side)
        ),
        n_floor_only_opposite_side_internal_faces=int(
            np.count_nonzero(floor_only_opposite_side)
        ),
    )


def audit_tet_boundary(
    points: np.ndarray,
    tets: np.ndarray,
    *,
    relative_volume_tolerance: float = 1e-12,
) -> TetBoundaryAudit:
    """Audit closed-manifold topology through C++23, with NumPy fallback."""
    pts = np.asarray(points, dtype=np.float64)
    tet = np.asarray(tets, dtype=np.int64)
    if tet.ndim != 2 or tet.shape[1:] != (4,):
        raise ValueError("tets must have shape (N, 4)")
    if pts.ndim != 2 or pts.shape[1:] != (3,):
        raise ValueError("points must have shape (N, 3)")
    if tet.size and (int(tet.min()) < 0 or int(tet.max()) >= len(pts)):
        raise ValueError("tet vertex index out of range")
    if tet.shape[0] == 0:
        return TetBoundaryAudit(0, 0, 0, 0, 0, 0, 0, 0, 0)

    sidedness = audit_internal_face_sidedness(
        pts,
        tet,
        relative_volume_tolerance=relative_volume_tolerance,
    )

    from core.utils.native_extensions import load_native_tet_predicates

    native = load_native_tet_predicates()
    if native is not None and hasattr(native, "audit_tet_boundary"):
        values = native.audit_tet_boundary(
            pts,
            tet,
            float(relative_volume_tolerance),
        )
        return replace(
            TetBoundaryAudit(*(int(value) for value in values)),
            n_internal_faces=sidedness.n_internal_faces,
            n_same_side_internal_faces=sidedness.n_same_side_internal_faces,
            n_ambiguous_internal_faces=sidedness.n_ambiguous_internal_faces,
        )

    canonical_tets = np.sort(tet, axis=1)
    duplicate_tets = int(canonical_tets.shape[0] - np.unique(canonical_tets, axis=0).shape[0])
    vertices = pts[tet]
    volume6 = np.einsum(
        "ij,ij->i",
        vertices[:, 1] - vertices[:, 0],
        np.cross(
            vertices[:, 2] - vertices[:, 0],
            vertices[:, 3] - vertices[:, 0],
        ),
    )
    diagonal = max(
        float(np.linalg.norm(np.ptp(pts, axis=0))),
        float(np.finfo(np.float64).tiny),
    )
    volume_floor = max(0.0, float(relative_volume_tolerance)) * diagonal**3
    degenerate_tets = int((np.abs(volume6) <= volume_floor).sum())
    inverted_tets = int((volume6 < 0.0).sum())

    faces = np.concatenate(
        [
            tet[:, (0, 1, 2)],
            tet[:, (0, 1, 3)],
            tet[:, (0, 2, 3)],
            tet[:, (1, 2, 3)],
        ],
        axis=0,
    )
    canonical_faces = np.sort(faces, axis=1)
    unique_faces, counts = np.unique(canonical_faces, axis=0, return_counts=True)
    boundary_faces = unique_faces[counts == 1]
    nonmanifold_faces = int((counts > 2).sum())

    if boundary_faces.shape[0] == 0:
        return TetBoundaryAudit(
            int(tet.shape[0]),
            0,
            0,
            0,
            nonmanifold_faces,
            0,
            duplicate_tets,
            degenerate_tets,
            inverted_tets,
            sidedness.n_internal_faces,
            sidedness.n_same_side_internal_faces,
            sidedness.n_ambiguous_internal_faces,
        )

    edges = np.concatenate(
        [
            boundary_faces[:, (0, 1)],
            boundary_faces[:, (1, 2)],
            boundary_faces[:, (0, 2)],
        ],
        axis=0,
    )
    edges = np.sort(edges, axis=1)
    unique_edges, edge_counts = np.unique(edges, axis=0, return_counts=True)
    open_edges = int((edge_counts == 1).sum())
    nonmanifold_edges = int((edge_counts > 2).sum())

    parent = np.arange(boundary_faces.shape[0], dtype=np.int64)

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = int(parent[item])
        return item

    def union(left: int, right: int) -> None:
        a = find(left)
        b = find(right)
        if a != b:
            parent[b] = a

    order = np.lexsort((edges[:, 1], edges[:, 0]))
    sorted_edges = edges[order]
    face_ids = np.tile(np.arange(boundary_faces.shape[0], dtype=np.int64), 3)[order]
    starts = np.r_[0, 1 + np.flatnonzero(np.any(sorted_edges[1:] != sorted_edges[:-1], axis=1))]
    ends = np.r_[starts[1:], len(sorted_edges)]
    for start, end in zip(starts, ends):
        first = int(face_ids[start])
        for index in range(int(start) + 1, int(end)):
            union(first, int(face_ids[index]))
    components = len({find(index) for index in range(boundary_faces.shape[0])})

    return TetBoundaryAudit(
        n_tets=int(tet.shape[0]),
        n_boundary_faces=int(boundary_faces.shape[0]),
        n_open_edges=open_edges,
        n_nonmanifold_edges=nonmanifold_edges,
        n_nonmanifold_faces=nonmanifold_faces,
        n_boundary_components=int(components),
        n_duplicate_tets=duplicate_tets,
        n_degenerate_tets=degenerate_tets,
        n_inverted_tets=inverted_tets,
        n_internal_faces=sidedness.n_internal_faces,
        n_same_side_internal_faces=sidedness.n_same_side_internal_faces,
        n_ambiguous_internal_faces=sidedness.n_ambiguous_internal_faces,
    )


__all__ = [
    "DuplicateTetGroupRepair",
    "InternalFaceSidednessAudit",
    "SourceComponentBijectionAudit",
    "SourcePrefixRoundoffRestore",
    "SourceTopologyAudit",
    "TetBoundaryAudit",
    "audit_source_component_bijection",
    "audit_internal_face_sidedness",
    "audit_source_topology",
    "audit_tet_boundary",
    "drop_duplicate_tet_groups_if_strict_topology_restored",
    "has_strict_writer_topology",
    "restore_source_prefix_roundoff",
]
