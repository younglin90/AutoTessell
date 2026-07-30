"""Deterministic native quad-dominant surface conversion.

This is a conservative post-process for an oriented triangle surface, not a
cross-field or global parameterisation solver. It joins only triangle pairs
whose shared edge is neither a wall/boundary nor a sharp feature. Every merged
quad must pass local convexity, scaled-Jacobian, aspect, and warpage gates.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from numbers import Integral
from typing import TypeGuard, cast

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, field_validator

_INT64_MIN = int(np.iinfo(np.int64).min)
_INT64_MAX = int(np.iinfo(np.int64).max)


def _is_exact_index(value: object) -> TypeGuard[Integral]:
    return not isinstance(value, (bool, np.bool_)) and isinstance(value, Integral)


def _decode_triangle_indices(values: object) -> NDArray[np.int64]:
    """Return exact signed-int64 triangle indices without lossy coercion."""
    try:
        raw_triangles = np.asarray(values)
    except (OverflowError, TypeError, ValueError):
        raise ValueError("triangles must have shape (M, 3)") from None
    if raw_triangles.ndim != 2 or raw_triangles.shape[1] != 3:
        raise ValueError("triangles must have shape (M, 3)")
    if raw_triangles.dtype == np.dtype(np.int64):
        return np.array(raw_triangles, dtype=np.int64, order="C", copy=True)
    if any(not _is_exact_index(value) for value in raw_triangles.flat):
        raise ValueError("triangles must contain exact finite signed int64 indices")
    if any(int(value) < _INT64_MIN or int(value) > _INT64_MAX for value in raw_triangles.flat):
        raise ValueError("triangle indices exceed signed int64 range")
    try:
        return np.asarray(raw_triangles, dtype=np.int64).copy()
    except (OverflowError, TypeError, ValueError):
        raise ValueError("triangle indices exceed signed int64 range") from None


def _decode_python_vertex_scalar(value: object) -> float:
    """Decode one Python/NumPy scalar without allowing coercion to hide loss."""
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("vertices must be a real numeric array")
    if isinstance(value, Integral):
        integer_value = int(value)
        try:
            converted = float(integer_value)
        except OverflowError:
            raise ValueError(
                "vertex coordinates must be exactly representable as float64"
            ) from None
        if not math.isfinite(converted) or int(converted) != integer_value:
            raise ValueError("vertex coordinates must be exactly representable as float64")
        return converted
    if not isinstance(value, (float, np.floating)):
        raise ValueError("vertices must be a real numeric array")
    if not bool(np.isfinite(value)):
        raise ValueError("surface contains non-finite vertices")
    try:
        converted = float(value)
    except OverflowError:
        raise ValueError("vertex coordinates must be exactly representable as float64") from None
    if not math.isfinite(converted) or value != converted:
        raise ValueError("vertex coordinates must be exactly representable as float64")
    return converted


def _decode_python_vertex_array(values: object) -> NDArray[np.float64]:
    """Decode non-ndarray inputs before NumPy may apply a lossy common dtype."""
    try:
        raw_vertices = np.asarray(values, dtype=object)
    except (OverflowError, TypeError, ValueError):
        raise ValueError("vertices must be a real numeric array with shape (N, 3)") from None
    if raw_vertices.ndim != 2 or raw_vertices.shape[1] != 3:
        raise ValueError("vertices must have shape (N, 3)")
    converted = np.empty(raw_vertices.shape, dtype=np.float64, order="C")
    for index, value in enumerate(raw_vertices.flat):
        converted.flat[index] = _decode_python_vertex_scalar(value)
    return converted


def _decode_vertex_coordinates(values: object) -> NDArray[np.float64]:
    """Return float64 coordinates only when conversion preserves every value."""
    if not isinstance(values, np.ndarray):
        return _decode_python_vertex_array(values)
    try:
        raw_vertices = np.asarray(values)
    except (OverflowError, TypeError, ValueError):
        raise ValueError("vertices must be a real numeric array with shape (N, 3)") from None
    if raw_vertices.ndim != 2 or raw_vertices.shape[1] != 3:
        raise ValueError("vertices must have shape (N, 3)")
    if raw_vertices.dtype.kind not in {"i", "u", "f"}:
        raise ValueError("vertices must be a real numeric array")
    if not np.isfinite(raw_vertices).all():
        raise ValueError("surface contains non-finite vertices")

    if raw_vertices.dtype.kind == "f" and raw_vertices.dtype.itemsize > 8:
        float64_limit = np.asarray(np.finfo(np.float64).max, dtype=raw_vertices.dtype)
        if np.any(np.abs(raw_vertices) > float64_limit):
            raise ValueError("vertex coordinates must be exactly representable as float64")

    converted = np.asarray(raw_vertices, dtype=np.float64, order="C")
    if raw_vertices.dtype.kind == "i":
        bit_count = np.iinfo(raw_vertices.dtype).bits
        lower_bound = -float(2 ** (bit_count - 1))
        upper_bound = float(2 ** (bit_count - 1))
        if np.any(converted < lower_bound) or np.any(converted >= upper_bound):
            raise ValueError("vertex coordinates must be exactly representable as float64")
    elif raw_vertices.dtype.kind == "u":
        bit_count = np.iinfo(raw_vertices.dtype).bits
        upper_bound = float(2**bit_count)
        if np.any(converted < 0.0) or np.any(converted >= upper_bound):
            raise ValueError("vertex coordinates must be exactly representable as float64")

    if raw_vertices.dtype != np.dtype(np.float64):
        restored = converted.astype(raw_vertices.dtype)
        if not np.array_equal(restored, raw_vertices):
            raise ValueError("vertex coordinates must be exactly representable as float64")
    if np.shares_memory(converted, raw_vertices):
        return converted.copy(order="C")
    return converted


def _decode_protected_wall_edge(value: object) -> tuple[int, int]:
    """Decode one wall edge without accepting Pydantic/NumPy coercions."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ValueError("protected_wall_edges must contain pairs of exact signed int64 indices")
    raw_edge: tuple[object, ...] = tuple(value)
    if len(raw_edge) != 2:
        raise ValueError("protected_wall_edges must contain pairs of exact signed int64 indices")
    first, second = raw_edge
    if not _is_exact_index(first) or not _is_exact_index(second):
        raise ValueError("protected_wall_edges must contain pairs of exact signed int64 indices")
    first_index, second_index = int(first), int(second)
    if not (_INT64_MIN <= first_index <= _INT64_MAX and _INT64_MIN <= second_index <= _INT64_MAX):
        raise ValueError("protected_wall_edges contain indices outside signed int64 range")
    return first_index, second_index


class QuadDominantConfig(BaseModel):
    """Conservative controls for :func:`native_quad_dominant_remesh`."""

    feature_angle_deg: float = Field(default=45.0, gt=0.0, lt=180.0)
    min_scaled_jacobian: float = Field(default=0.2, gt=0.0, le=1.0)
    max_aspect_ratio: float = Field(default=4.0, ge=1.0)
    max_warpage: float = Field(default=0.05, ge=0.0, le=1.0)
    protected_wall_edges: list[tuple[int, int]] = Field(default_factory=list)

    @field_validator("protected_wall_edges", mode="before")
    @classmethod
    def _decode_protected_wall_edges(cls, values: object) -> list[tuple[int, int]]:
        if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
            raise ValueError(
                "protected_wall_edges must contain pairs of exact signed int64 indices"
            )
        return [_decode_protected_wall_edge(value) for value in values]


class QuadDominantDiagnostics(BaseModel):
    """Exact topology and local-quality evidence for a conversion attempt."""

    input_triangles: int
    output_quads: int = 0
    output_triangles: int = 0
    protected_boundary_edges: int = 0
    protected_feature_edges: int = 0
    protected_wall_edges: int = 0
    candidate_pairs: int = 0
    accepted_pairs: int = 0
    rejected_protected: int = 0
    rejected_quality: int = 0
    min_quad_scaled_jacobian: float | None = None
    max_quad_aspect_ratio: float | None = None
    max_quad_warpage: float | None = None
    route: str = "native_quad_dominant"
    contract: str = "native_quad"
    fallback_reason: str | None = None


class QuadDominantResult(BaseModel):
    """Mixed triangle/quad surface; face ordering is deterministic."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vertices: np.ndarray
    triangles: np.ndarray
    quads: np.ndarray
    diagnostics: QuadDominantDiagnostics


def _edge_key(first: int, second: int) -> tuple[int, int]:
    return (first, second) if first < second else (second, first)


def _similarity_normalized_points(
    points: NDArray[np.float64],
) -> NDArray[np.float64] | None:
    """Return local points after exact power-of-two similarity scaling."""
    coordinate_magnitude = float(np.abs(points).max(initial=0.0))
    if not np.isfinite(coordinate_magnitude) or coordinate_magnitude == 0.0:
        return None
    _, coordinate_exponent = np.frexp(coordinate_magnitude)
    scaled = np.ldexp(points, -coordinate_exponent)
    relative = scaled - scaled[0]
    local_magnitude = float(np.abs(relative).max(initial=0.0))
    if not np.isfinite(local_magnitude) or local_magnitude == 0.0:
        return None
    _, local_exponent = np.frexp(local_magnitude)
    return cast(NDArray[np.float64], np.ldexp(relative, -local_exponent))


def _cross3(left: NDArray[np.float64], right: NDArray[np.float64]) -> NDArray[np.float64]:
    return cast(
        NDArray[np.float64],
        np.asarray(
            (
                float(left[1]) * float(right[2]) - float(left[2]) * float(right[1]),
                float(left[2]) * float(right[0]) - float(left[0]) * float(right[2]),
                float(left[0]) * float(right[1]) - float(left[1]) * float(right[0]),
            ),
            dtype=np.float64,
        ),
    )


def _dot3(left: NDArray[np.float64], right: NDArray[np.float64]) -> float:
    return (
        float(left[0]) * float(right[0])
        + float(left[1]) * float(right[1])
        + float(left[2]) * float(right[2])
    )


def _norm3(value: NDArray[np.float64]) -> float:
    return math.sqrt(_dot3(value, value))


def _validate_vertex_links(triangles: NDArray[np.int64]) -> None:
    """Reject vertices whose incident-triangle link has multiple components."""
    links: dict[int, dict[int, set[int]]] = {}
    for triangle in triangles:
        first, second, third = (int(vertex) for vertex in triangle)
        for vertex, left, right in (
            (first, second, third),
            (second, third, first),
            (third, first, second),
        ):
            link = links.setdefault(vertex, {})
            link.setdefault(left, set()).add(right)
            link.setdefault(right, set()).add(left)

    for vertex in sorted(links):
        link = links[vertex]
        visited: set[int] = set()
        pending = [min(link)]
        while pending:
            neighbor = pending.pop()
            if neighbor in visited:
                continue
            visited.add(neighbor)
            pending.extend(link[neighbor] - visited)
        if len(visited) != len(link):
            raise ValueError(f"surface contains non-manifold vertex {vertex}")


def _validate_input(
    vertices: np.ndarray,
    triangles: np.ndarray,
) -> dict[tuple[int, int], list[int]]:
    if vertices.ndim != 2 or vertices.shape[1] != 3:
        raise ValueError("vertices must have shape (N, 3)")
    if triangles.ndim != 2 or triangles.shape[1] != 3:
        raise ValueError("triangles must have shape (M, 3)")
    if not np.isfinite(vertices).all():
        raise ValueError("surface contains non-finite vertices")
    if (triangles < 0).any() or (triangles >= len(vertices)).any():
        raise ValueError("triangle indices are outside the input vertex range")

    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is not None and hasattr(native, "validate_triangle_surface_and_build_edge_faces"):
        return native.validate_triangle_surface_and_build_edge_faces(
            vertices,
            triangles,
        )

    seen_faces: set[tuple[int, int, int]] = set()
    edge_directions: dict[tuple[int, int], list[int]] = defaultdict(list)
    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, triangle in enumerate(triangles):
        first, second, third = (int(vertex) for vertex in triangle)
        face_key = tuple(sorted((first, second, third)))
        if len(set(face_key)) != 3:
            raise ValueError("surface contains a degenerate triangle")
        if face_key in seen_faces:
            raise ValueError("surface contains a duplicate triangle")
        seen_faces.add(face_key)
        points = vertices[np.asarray((first, second, third), dtype=np.int64)]
        normalized = _similarity_normalized_points(points)
        if normalized is None or _norm3(_cross3(normalized[1], normalized[2])) <= 1e-30:
            raise ValueError("surface contains a zero-area triangle")
        for start, end in ((first, second), (second, third), (third, first)):
            edge = _edge_key(start, end)
            edge_directions[edge].append(1 if (start, end) == edge else -1)
            edge_faces[edge].append(face_index)
    for edge, directions in edge_directions.items():
        if len(directions) > 2:
            raise ValueError(f"surface contains non-manifold edge {edge}")
        if len(directions) == 2 and directions[0] == directions[1]:
            raise ValueError(f"surface contains inconsistent orientation at edge {edge}")
    _validate_vertex_links(triangles)
    return dict(edge_faces)


def _edge_faces(triangles: np.ndarray) -> dict[tuple[int, int], list[int]]:
    edges: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, triangle in enumerate(triangles):
        for local_index in range(3):
            first, second = int(triangle[local_index]), int(triangle[(local_index + 1) % 3])
            edges[_edge_key(first, second)].append(face_index)
    return dict(edges)


def _validated_wall_edges(
    protected_wall_edges: object,
    input_edges: dict[tuple[int, int], list[int]],
) -> set[tuple[int, int]]:
    """Return canonical declared wall edges only when they exist in the input."""
    if isinstance(protected_wall_edges, (str, bytes)) or not isinstance(
        protected_wall_edges, Iterable
    ):
        raise ValueError("protected_wall_edges must contain pairs of exact signed int64 indices")
    supplied = tuple(protected_wall_edges)

    wall_edges: set[tuple[int, int]] = set()
    for value in supplied:
        first, second = _decode_protected_wall_edge(value)
        if first == second:
            raise ValueError("protected wall edge must have distinct endpoints")
        edge = _edge_key(first, second)
        if edge not in input_edges:
            raise ValueError(f"protected wall edge {edge} is not an input surface edge")
        wall_edges.add(edge)
    return wall_edges


def _unit_normal(points: np.ndarray) -> np.ndarray:
    normalized = _similarity_normalized_points(points)
    if normalized is None:
        return np.zeros(3, dtype=np.float64)
    normal = _cross3(normalized[1], normalized[2])
    length = _norm3(normal)
    return normal / length if length > 1e-30 else np.zeros(3, dtype=np.float64)


def _feature_edges(
    vertices: np.ndarray,
    triangles: np.ndarray,
    edges: dict[tuple[int, int], list[int]],
    angle_deg: float,
) -> set[tuple[int, int]]:
    normals = np.array([_unit_normal(vertices[triangle]) for triangle in triangles])
    cos_limit = float(np.cos(np.deg2rad(angle_deg)))
    protected: set[tuple[int, int]] = set()
    for edge, incident in edges.items():
        if len(incident) == 2 and _dot3(*normals[incident]) < cos_limit:
            protected.add(edge)
    return protected


def _oriented_quads_for_pairs(
    triangles: NDArray[np.int64],
    face_pairs: NDArray[np.int64],
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Return exact oriented quads and canonical shared edges for face pairs."""
    if not len(face_pairs):
        return np.empty((0, 4), dtype=np.int64), np.empty((0, 2), dtype=np.int64)
    first_triangles = triangles[face_pairs[:, 0]]
    second_triangles = triangles[face_pairs[:, 1]]
    equality = first_triangles[:, :, None] == second_triangles[:, None, :]
    first_shared = equality.any(axis=2)
    second_shared = equality.any(axis=1)
    if not ((first_shared.sum(axis=1) == 2) & (second_shared.sum(axis=1) == 2)).all():
        raise RuntimeError("native quad transaction returned a non-adjacent face pair")
    oriented_edges = first_shared & np.roll(first_shared, -1, axis=1)
    if not (oriented_edges.sum(axis=1) == 1).all():
        raise RuntimeError("native quad transaction returned an invalid shared edge")
    row = np.arange(len(face_pairs), dtype=np.int64)
    start = np.argmax(oriented_edges, axis=1)
    second_opposite = np.argmax(~second_shared, axis=1)
    edge_start = first_triangles[row, start]
    edge_end = first_triangles[row, (start + 1) % 3]
    quads = np.column_stack(
        (
            first_triangles[row, (start + 2) % 3],
            edge_start,
            second_triangles[row, second_opposite],
            edge_end,
        )
    )
    shared_edges = np.sort(np.column_stack((edge_start, edge_end)), axis=1)
    return np.ascontiguousarray(quads), np.ascontiguousarray(shared_edges)


def _validate_preparation_result(
    vertices: np.ndarray,
    triangles: NDArray[np.int64],
    decoded_wall_edges: list[tuple[int, int]],
    feature_angle_deg: float,
    result: object,
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Fail closed on malformed native preflight arrays and provenance."""
    if not isinstance(result, tuple) or len(result) != 2:
        raise RuntimeError("native prepare_quad_pairs returned an invalid result")
    face_pairs, diagnostics = result
    if (
        not isinstance(face_pairs, np.ndarray)
        or face_pairs.dtype != np.dtype(np.int64)
        or face_pairs.ndim != 2
        or face_pairs.shape[1] != 2
        or not face_pairs.flags.c_contiguous
    ):
        raise RuntimeError("native prepare_quad_pairs returned invalid face_pairs")
    if (
        not isinstance(diagnostics, np.ndarray)
        or diagnostics.dtype != np.dtype(np.int64)
        or diagnostics.shape != (5,)
        or not diagnostics.flags.c_contiguous
        or (diagnostics < 0).any()
    ):
        raise RuntimeError("native prepare_quad_pairs returned invalid diagnostics")
    if face_pairs.size and (
        face_pairs.min() < 0
        or face_pairs.max() >= len(triangles)
        or (face_pairs[:, 0] >= face_pairs[:, 1]).any()
    ):
        raise RuntimeError("native prepare_quad_pairs returned invalid face-pair indices")
    if len(np.unique(face_pairs, axis=0)) != len(face_pairs):
        raise RuntimeError("native prepare_quad_pairs returned duplicate face pairs")

    _, shared_edges = _oriented_quads_for_pairs(triangles, face_pairs)
    unique_wall_edges = np.asarray(
        sorted({_edge_key(first, second) for first, second in decoded_wall_edges}),
        dtype=np.int64,
    ).reshape((-1, 2))
    if len(shared_edges) and len(unique_wall_edges):
        edge_dtype = np.dtype([("first", np.int64), ("second", np.int64)])
        returned_edges = shared_edges.view(edge_dtype).reshape(-1)
        protected_edges = np.ascontiguousarray(unique_wall_edges).view(edge_dtype).reshape(-1)
        if np.isin(returned_edges, protected_edges).any():
            raise RuntimeError("native prepare_quad_pairs returned a protected wall pair")
    if len(face_pairs):
        with np.errstate(over="ignore", invalid="ignore"):
            face_points = vertices[triangles]
            normals = np.cross(
                face_points[:, 1] - face_points[:, 0],
                face_points[:, 2] - face_points[:, 0],
            )
            lengths = np.linalg.norm(normals, axis=1)
            if not np.isfinite(lengths).all() or (lengths <= 1e-30).any():
                normals = np.asarray(
                    [_unit_normal(points) for points in face_points],
                    dtype=np.float64,
                )
                lengths = np.linalg.norm(normals, axis=1)
                if not np.isfinite(lengths).all() or (lengths <= 1e-30).any():
                    raise RuntimeError(
                        "native prepare_quad_pairs accepted an invalid source normal"
                    )
            unit_normals = np.divide(
                normals,
                lengths[:, None],
                out=np.zeros_like(normals),
                where=lengths[:, None] > 1e-30,
            )
            normal_dots = np.einsum(
                "ij,ij->i",
                unit_normals[face_pairs[:, 0]],
                unit_normals[face_pairs[:, 1]],
            )
        cosine_limit = float(np.cos(np.deg2rad(feature_angle_deg)))
        if (normal_dots < cosine_limit).any():
            raise RuntimeError("native prepare_quad_pairs returned a protected feature pair")
    if int(diagnostics[2]) != len(unique_wall_edges):
        raise RuntimeError("native prepare_quad_pairs returned invalid wall-edge count")
    if (
        int(diagnostics[1]) > int(diagnostics[3])
        or int(diagnostics[4]) > int(diagnostics[3])
        or int(diagnostics[3]) != len(face_pairs) + int(diagnostics[4])
    ):
        raise RuntimeError("native prepare_quad_pairs returned inconsistent diagnostics")
    return face_pairs, diagnostics


def _prepare_quad_pairs_python(
    vertices: np.ndarray,
    triangles: NDArray[np.int64],
    protected_wall_edges: object,
    feature_angle_deg: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Reference topology preflight and pair-preparation implementation."""
    edge_faces = _validate_input(vertices, triangles)
    wall_edges = _validated_wall_edges(protected_wall_edges, edge_faces)
    boundary_edges = {edge for edge, incident in edge_faces.items() if len(incident) == 1}
    feature_edges = _feature_edges(vertices, triangles, edge_faces, feature_angle_deg)
    protected = boundary_edges | feature_edges | wall_edges
    unprotected_face_pairs: list[tuple[int, int]] = []
    candidate_pairs = 0
    rejected_protected = 0
    for edge, incident in edge_faces.items():
        if len(incident) != 2:
            continue
        candidate_pairs += 1
        if edge in protected:
            rejected_protected += 1
            continue
        first, second = sorted(incident)
        unprotected_face_pairs.append((first, second))
    face_pairs = np.asarray(unprotected_face_pairs, dtype=np.int64).reshape((-1, 2))
    diagnostics = np.asarray(
        (
            len(boundary_edges),
            len(feature_edges),
            len(wall_edges),
            candidate_pairs,
            rejected_protected,
        ),
        dtype=np.int64,
    )
    return face_pairs, diagnostics


def _prepare_quad_pairs(
    vertices: np.ndarray,
    triangles: NDArray[np.int64],
    protected_wall_edges: object,
    feature_angle_deg: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Use the flat-array native preflight when its exact ABI is available."""
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "prepare_quad_pairs"):
        return _prepare_quad_pairs_python(
            vertices,
            triangles,
            protected_wall_edges,
            feature_angle_deg,
        )
    if isinstance(protected_wall_edges, (str, bytes)) or not isinstance(
        protected_wall_edges, Iterable
    ):
        raise ValueError("protected_wall_edges must contain pairs of exact signed int64 indices")
    supplied_wall_edges = tuple(protected_wall_edges)
    decoded_wall_edges = [_decode_protected_wall_edge(value) for value in supplied_wall_edges]
    wall_edges = np.asarray(decoded_wall_edges, dtype=np.int64).reshape((-1, 2))
    result = native.prepare_quad_pairs(
        vertices,
        triangles,
        wall_edges,
        feature_angle_deg,
    )
    return _validate_preparation_result(
        vertices,
        triangles,
        decoded_wall_edges,
        feature_angle_deg,
        result,
    )


def _oriented_quad(first: np.ndarray, second: np.ndarray) -> np.ndarray | None:
    """Return the oriented four-cycle formed by two adjacent triangles."""
    shared = set(map(int, first)) & set(map(int, second))
    if len(shared) != 2:
        return None
    for local_index in range(3):
        edge_start, edge_end = int(first[local_index]), int(first[(local_index + 1) % 3])
        if {edge_start, edge_end} == shared:
            opposite_first = int(first[(local_index + 2) % 3])
            opposite_second = next(int(vertex) for vertex in second if int(vertex) not in shared)
            return np.array([opposite_first, edge_start, opposite_second, edge_end], dtype=np.int64)
    return None


def _quad_quality(points: np.ndarray) -> tuple[float, float, float] | None:
    """Return min scaled-Jacobian, aspect, warpage; reject concave cases."""
    normalized = _similarity_normalized_points(points)
    if normalized is None:
        return None
    normal = _cross3(normalized[1], normalized[2]) + _cross3(normalized[2], normalized[3])
    normal_length = _norm3(normal)
    if normal_length <= 1e-30:
        return None
    unit_normal = normal * (1.0 / normal_length)
    edges = np.roll(normalized, -1, axis=0) - normalized
    lengths = np.asarray([_norm3(edge) for edge in edges], dtype=np.float64)
    if float(lengths.min()) <= 1e-30:
        return None
    scaled: list[float] = []
    for index in range(4):
        next_edge = normalized[(index + 1) % 4] - normalized[index]
        previous_edge = normalized[(index - 1) % 4] - normalized[index]
        denominator = _norm3(next_edge) * _norm3(previous_edge)
        value = _dot3(_cross3(next_edge, previous_edge), unit_normal) / denominator
        if value <= 1e-12:
            return None
        scaled.append(value)
    plane_normal = _cross3(normalized[1], normalized[2])
    plane_length = _norm3(plane_normal)
    if plane_length <= 1e-30:
        return None
    warpage = abs(_dot3(normalized[3], plane_normal * (1.0 / plane_length))) / float(lengths.max())
    return min(scaled), float(lengths.max() / lengths.min()), warpage


def _select_quad_pairs_python(
    vertices: np.ndarray,
    triangles: np.ndarray,
    face_pairs: np.ndarray,
    *,
    min_scaled_jacobian: float,
    max_aspect_ratio: float,
    max_warpage: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Reference pair-quality, ordering, and greedy-selection implementation."""
    candidates: list[tuple[float, int, int, np.ndarray, tuple[float, float, float]]] = []
    rejected_quality = 0
    for first_raw, second_raw in face_pairs:
        first, second = sorted((int(first_raw), int(second_raw)))
        quad = _oriented_quad(triangles[first], triangles[second])
        if quad is None:
            rejected_quality += 1
            continue
        quality = _quad_quality(vertices[quad])
        if quality is None or not np.isfinite(quality).all():
            rejected_quality += 1
            continue
        scaled_jacobian, aspect_ratio, warpage = quality
        if (
            scaled_jacobian < min_scaled_jacobian
            or aspect_ratio > max_aspect_ratio
            or warpage > max_warpage
        ):
            rejected_quality += 1
            continue
        score = scaled_jacobian - warpage
        if not np.isfinite(score):
            rejected_quality += 1
            continue
        candidates.append((score, first, second, quad, quality))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    consumed: set[int] = set()
    accepted: list[tuple[int, int, np.ndarray, tuple[float, float, float]]] = []
    for _, first, second, quad, quality in candidates:
        if first not in consumed and second not in consumed:
            consumed.update((first, second))
            accepted.append((first, second, quad, quality))
    accepted.sort(key=lambda item: (item[0], item[1]))
    accepted_pairs = np.asarray([(item[0], item[1]) for item in accepted], dtype=np.int64).reshape(
        (-1, 2)
    )
    quads = np.asarray([item[2] for item in accepted], dtype=np.int64).reshape((-1, 4))
    quality = np.asarray([item[3] for item in accepted], dtype=np.float64).reshape((-1, 3))
    return accepted_pairs, quads, quality, rejected_quality


def _validate_selection_result(
    vertices: np.ndarray,
    triangles: NDArray[np.int64],
    face_pairs: NDArray[np.int64],
    result: object,
    *,
    min_scaled_jacobian: float,
    max_aspect_ratio: float,
    max_warpage: float,
) -> tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64], int]:
    """Fail closed on malformed native selection arrays and provenance."""
    if not isinstance(result, dict):
        raise RuntimeError("native select_quad_pairs returned a non-dict result")

    def exact_array(name: str, dtype: np.dtype[np.generic], columns: int) -> np.ndarray:
        value = result.get(name)
        if (
            not isinstance(value, np.ndarray)
            or value.dtype != dtype
            or value.ndim != 2
            or value.shape[1] != columns
            or not value.flags.c_contiguous
        ):
            raise RuntimeError(f"native select_quad_pairs returned invalid {name} array")
        return value

    accepted_pairs = exact_array("accepted_face_pairs", np.dtype(np.int64), 2)
    quads = exact_array("quads", np.dtype(np.int64), 4)
    quality = exact_array("quality", np.dtype(np.float64), 3)
    accepted_count = len(accepted_pairs)
    if len(quads) != accepted_count or len(quality) != accepted_count:
        raise RuntimeError("native select_quad_pairs returned inconsistent row counts")
    if quality.size and not np.isfinite(quality).all():
        raise RuntimeError("native select_quad_pairs returned non-finite quality")
    if quality.size and (
        (quality[:, 0] < min_scaled_jacobian).any()
        or (quality[:, 0] > 1.0 + 1e-14).any()
        or (quality[:, 1] < 1.0 - 1e-14).any()
        or (quality[:, 1] > max_aspect_ratio).any()
        or (quality[:, 2] < 0.0).any()
        or (quality[:, 2] > max_warpage).any()
    ):
        raise RuntimeError("native select_quad_pairs returned out-of-range quality")
    if accepted_pairs.size and (
        accepted_pairs.min() < 0
        or accepted_pairs.max() >= len(triangles)
        or (accepted_pairs[:, 0] >= accepted_pairs[:, 1]).any()
    ):
        raise RuntimeError("native select_quad_pairs returned an invalid face index")
    if quads.size and (quads.min() < 0 or quads.max() >= len(vertices)):
        raise RuntimeError("native select_quad_pairs returned an invalid vertex index")
    if accepted_count:
        sorted_quads = np.sort(quads, axis=1)
        if (sorted_quads[:, 1:] == sorted_quads[:, :-1]).any():
            raise RuntimeError("native select_quad_pairs returned a repeated quad vertex")
        if len(np.unique(accepted_pairs.reshape(-1))) != accepted_pairs.size:
            raise RuntimeError("native select_quad_pairs consumed one face more than once")
        if len(accepted_pairs) > 1:
            previous, current = accepted_pairs[:-1], accepted_pairs[1:]
            if (
                (current[:, 0] < previous[:, 0])
                | ((current[:, 0] == previous[:, 0]) & (current[:, 1] <= previous[:, 1]))
            ).any():
                raise RuntimeError("native select_quad_pairs returned unsorted face pairs")
        supplied = (
            np.ascontiguousarray(face_pairs)
            .view(np.dtype([("first", np.int64), ("second", np.int64)]))
            .reshape(-1)
        )
        returned = accepted_pairs.view(
            np.dtype([("first", np.int64), ("second", np.int64)])
        ).reshape(-1)
        if not np.isin(returned, supplied).all():
            raise RuntimeError("native select_quad_pairs returned invalid face-pair provenance")
        expected_quads, _ = _oriented_quads_for_pairs(triangles, accepted_pairs)
        if not np.array_equal(quads, expected_quads):
            raise RuntimeError("native select_quad_pairs returned invalid quad provenance")
    rejected_quality = result.get("rejected_quality")
    if (
        isinstance(rejected_quality, (bool, np.bool_))
        or not isinstance(rejected_quality, Integral)
        or int(rejected_quality) < 0
        or int(rejected_quality) > len(face_pairs)
    ):
        raise RuntimeError("native select_quad_pairs returned invalid rejected_quality")
    return accepted_pairs, quads, quality, int(rejected_quality)


def _select_quad_pairs(
    vertices: np.ndarray,
    triangles: np.ndarray,
    face_pairs: np.ndarray,
    *,
    min_scaled_jacobian: float,
    max_aspect_ratio: float,
    max_warpage: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Use the allocation-bounded native selector when its ABI is available."""
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "select_quad_pairs"):
        return _select_quad_pairs_python(
            vertices,
            triangles,
            face_pairs,
            min_scaled_jacobian=min_scaled_jacobian,
            max_aspect_ratio=max_aspect_ratio,
            max_warpage=max_warpage,
        )
    result = native.select_quad_pairs(
        vertices,
        triangles,
        face_pairs,
        min_scaled_jacobian,
        max_aspect_ratio,
        max_warpage,
    )
    return _validate_selection_result(
        vertices,
        triangles,
        face_pairs,
        result,
        min_scaled_jacobian=min_scaled_jacobian,
        max_aspect_ratio=max_aspect_ratio,
        max_warpage=max_warpage,
    )


def _native_quad_transaction(
    vertices: np.ndarray,
    triangles: NDArray[np.int64],
    settings: QuadDominantConfig,
) -> (
    tuple[
        NDArray[np.int64],
        NDArray[np.int64],
        NDArray[np.int64],
        NDArray[np.float64],
        NDArray[np.int64],
        int,
    ]
    | None
):
    """Run one fused native transaction and independently audit provenance."""
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "quad_dominant_transaction"):
        return None
    decoded_wall_edges = [
        _decode_protected_wall_edge(value) for value in settings.protected_wall_edges
    ]
    wall_edges = np.asarray(decoded_wall_edges, dtype=np.int64).reshape((-1, 2))
    result = native.quad_dominant_transaction(
        vertices,
        triangles,
        wall_edges,
        settings.feature_angle_deg,
        settings.min_scaled_jacobian,
        settings.max_aspect_ratio,
        settings.max_warpage,
    )
    if not isinstance(result, dict):
        raise RuntimeError("native quad_dominant_transaction returned a non-dict result")
    candidate_pairs, preparation_diagnostics = _validate_preparation_result(
        vertices,
        triangles,
        decoded_wall_edges,
        settings.feature_angle_deg,
        (result.get("candidate_face_pairs"), result.get("preparation_diagnostics")),
    )
    accepted_pairs, quads, quality, rejected_quality = _validate_selection_result(
        vertices,
        triangles,
        candidate_pairs,
        result,
        min_scaled_jacobian=settings.min_scaled_jacobian,
        max_aspect_ratio=settings.max_aspect_ratio,
        max_warpage=settings.max_warpage,
    )
    remaining_triangles = result.get("remaining_triangles")
    if (
        not isinstance(remaining_triangles, np.ndarray)
        or remaining_triangles.dtype != np.dtype(np.int64)
        or remaining_triangles.ndim != 2
        or remaining_triangles.shape[1] != 3
        or not remaining_triangles.flags.c_contiguous
    ):
        raise RuntimeError("native quad_dominant_transaction returned invalid remaining_triangles")
    consumed = np.zeros(len(triangles), dtype=bool)
    if accepted_pairs.size:
        consumed[accepted_pairs.reshape(-1)] = True
    expected_remaining = triangles[~consumed]
    if not np.array_equal(remaining_triangles, expected_remaining):
        raise RuntimeError("native quad_dominant_transaction returned invalid triangle provenance")
    return (
        accepted_pairs,
        remaining_triangles,
        quads,
        quality,
        preparation_diagnostics,
        rejected_quality,
    )


def native_quad_dominant_remesh(
    vertices: np.ndarray,
    triangles: np.ndarray,
    *,
    config: QuadDominantConfig | None = None,
) -> QuadDominantResult:
    """Convert safe adjacent triangle pairs into quads without moving vertices."""
    settings = config or QuadDominantConfig()
    input_triangles = _decode_triangle_indices(triangles)
    output_vertices = _decode_vertex_coordinates(vertices)
    diagnostics = QuadDominantDiagnostics(input_triangles=int(len(input_triangles)))
    native_transaction = _native_quad_transaction(output_vertices, input_triangles, settings)
    if native_transaction is None:
        face_pairs, preparation_diagnostics = _prepare_quad_pairs(
            output_vertices,
            input_triangles,
            settings.protected_wall_edges,
            settings.feature_angle_deg,
        )
    else:
        (
            accepted_pairs,
            output_triangles,
            output_quads,
            qualities,
            preparation_diagnostics,
            rejected_quality,
        ) = native_transaction
    diagnostics.protected_boundary_edges = int(preparation_diagnostics[0])
    diagnostics.protected_feature_edges = int(preparation_diagnostics[1])
    diagnostics.protected_wall_edges = int(preparation_diagnostics[2])
    diagnostics.candidate_pairs = int(preparation_diagnostics[3])
    diagnostics.rejected_protected = int(preparation_diagnostics[4])
    if not len(input_triangles):
        diagnostics.fallback_reason = "empty_input"
        return QuadDominantResult(
            vertices=output_vertices,
            triangles=np.empty((0, 3), dtype=np.int64),
            quads=np.empty((0, 4), dtype=np.int64),
            diagnostics=diagnostics,
        )

    if native_transaction is None:
        accepted_pairs, output_quads, qualities, rejected_quality = _select_quad_pairs(
            output_vertices,
            input_triangles,
            face_pairs,
            min_scaled_jacobian=settings.min_scaled_jacobian,
            max_aspect_ratio=settings.max_aspect_ratio,
            max_warpage=settings.max_warpage,
        )
        consumed = set(accepted_pairs.reshape(-1).tolist())
        output_triangles = np.array(
            [triangle for index, triangle in enumerate(input_triangles) if index not in consumed],
            dtype=np.int64,
        ).reshape((-1, 3))
    diagnostics.rejected_quality = rejected_quality
    diagnostics.accepted_pairs = len(accepted_pairs)
    diagnostics.output_quads = int(len(output_quads))
    diagnostics.output_triangles = int(len(output_triangles))
    if len(accepted_pairs):
        diagnostics.min_quad_scaled_jacobian = float(qualities[:, 0].min())
        diagnostics.max_quad_aspect_ratio = float(qualities[:, 1].max())
        diagnostics.max_quad_warpage = float(qualities[:, 2].max())
    else:
        diagnostics.fallback_reason = (
            "no_valid_pair_accepted" if diagnostics.candidate_pairs else "no_merge_candidate"
        )
    return QuadDominantResult(
        vertices=output_vertices,
        triangles=output_triangles,
        quads=output_quads,
        diagnostics=diagnostics,
    )
