"""Deterministic native quad-dominant surface conversion.

This is a conservative post-process for an oriented triangle surface, not a
cross-field or global parameterisation solver. It joins only triangle pairs
whose shared edge is neither a wall/boundary nor a sharp feature. Every merged
quad must pass local convexity, scaled-Jacobian, aspect, and warpage gates.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from numbers import Integral
from typing import TypeGuard

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
    if any(not _is_exact_index(value) for value in raw_triangles.flat):
        raise ValueError("triangles must contain exact finite signed int64 indices")
    if any(int(value) < _INT64_MIN or int(value) > _INT64_MAX for value in raw_triangles.flat):
        raise ValueError("triangle indices exceed signed int64 range")
    try:
        return np.asarray(raw_triangles, dtype=np.int64).copy()
    except (OverflowError, TypeError, ValueError):
        raise ValueError("triangle indices exceed signed int64 range") from None


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
    if native is not None and hasattr(
        native, "validate_triangle_surface_and_build_edge_faces"
    ):
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
        if float(np.linalg.norm(np.cross(points[1] - points[0], points[2] - points[0]))) <= 1e-30:
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
    normal = np.cross(points[1] - points[0], points[2] - points[0])
    length = float(np.linalg.norm(normal))
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
        if len(incident) == 2 and float(np.dot(*normals[incident])) < cos_limit:
            protected.add(edge)
    return protected


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
    normal = np.cross(points[1] - points[0], points[2] - points[0]) + np.cross(
        points[2] - points[0], points[3] - points[0]
    )
    normal_length = float(np.linalg.norm(normal))
    if normal_length <= 1e-30:
        return None
    unit_normal = normal / normal_length
    edges = np.roll(points, -1, axis=0) - points
    lengths = np.linalg.norm(edges, axis=1)
    if float(lengths.min()) <= 1e-30:
        return None
    scaled: list[float] = []
    for index in range(4):
        next_edge = points[(index + 1) % 4] - points[index]
        previous_edge = points[(index - 1) % 4] - points[index]
        denominator = float(np.linalg.norm(next_edge) * np.linalg.norm(previous_edge))
        value = float(np.dot(np.cross(next_edge, previous_edge), unit_normal)) / denominator
        if value <= 1e-12:
            return None
        scaled.append(value)
    plane_normal = np.cross(points[1] - points[0], points[2] - points[0])
    plane_length = float(np.linalg.norm(plane_normal))
    if plane_length <= 1e-30:
        return None
    warpage = abs(float(np.dot(points[3] - points[0], plane_normal / plane_length))) / float(
        lengths.max()
    )
    return min(scaled), float(lengths.max() / lengths.min()), warpage


def native_quad_dominant_remesh(
    vertices: np.ndarray,
    triangles: np.ndarray,
    *,
    config: QuadDominantConfig | None = None,
) -> QuadDominantResult:
    """Convert safe adjacent triangle pairs into quads without moving vertices."""
    settings = config or QuadDominantConfig()
    input_triangles = _decode_triangle_indices(triangles)
    output_vertices = np.asarray(vertices, dtype=np.float64).copy()
    edge_faces = _validate_input(output_vertices, input_triangles)
    diagnostics = QuadDominantDiagnostics(input_triangles=int(len(input_triangles)))
    wall_edges = _validated_wall_edges(settings.protected_wall_edges, edge_faces)
    if not len(input_triangles):
        diagnostics.fallback_reason = "empty_input"
        return QuadDominantResult(
            vertices=output_vertices,
            triangles=np.empty((0, 3), dtype=np.int64),
            quads=np.empty((0, 4), dtype=np.int64),
            diagnostics=diagnostics,
        )

    boundary_edges = {edge for edge, incident in edge_faces.items() if len(incident) == 1}
    feature_edges = _feature_edges(
        output_vertices, input_triangles, edge_faces, settings.feature_angle_deg
    )
    protected = boundary_edges | feature_edges | wall_edges
    diagnostics.protected_boundary_edges = len(boundary_edges)
    diagnostics.protected_feature_edges = len(feature_edges)
    diagnostics.protected_wall_edges = len(wall_edges)

    candidates: list[tuple[float, int, int, np.ndarray, tuple[float, float, float]]] = []
    for edge, incident in edge_faces.items():
        if len(incident) != 2:
            continue
        diagnostics.candidate_pairs += 1
        if edge in protected:
            diagnostics.rejected_protected += 1
            continue
        first, second = sorted(incident)
        quad = _oriented_quad(input_triangles[first], input_triangles[second])
        quality = _quad_quality(output_vertices[quad]) if quad is not None else None
        if quality is None:
            diagnostics.rejected_quality += 1
            continue
        scaled_jacobian, aspect_ratio, warpage = quality
        if (
            scaled_jacobian < settings.min_scaled_jacobian
            or aspect_ratio > settings.max_aspect_ratio
            or warpage > settings.max_warpage
        ):
            diagnostics.rejected_quality += 1
            continue
        candidates.append((scaled_jacobian - warpage, first, second, quad, quality))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    consumed: set[int] = set()
    accepted: list[tuple[int, int, np.ndarray, tuple[float, float, float]]] = []
    for _, first, second, quad, quality in candidates:
        if first not in consumed and second not in consumed:
            consumed.update((first, second))
            accepted.append((first, second, quad, quality))
    accepted.sort(key=lambda item: (item[0], item[1]))
    output_quads = np.array([item[2] for item in accepted], dtype=np.int64).reshape((-1, 4))
    output_triangles = np.array(
        [triangle for index, triangle in enumerate(input_triangles) if index not in consumed],
        dtype=np.int64,
    ).reshape((-1, 3))
    diagnostics.accepted_pairs = len(accepted)
    diagnostics.output_quads = int(len(output_quads))
    diagnostics.output_triangles = int(len(output_triangles))
    if accepted:
        qualities = np.asarray([item[3] for item in accepted], dtype=np.float64)
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
