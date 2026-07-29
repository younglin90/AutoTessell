"""Report-only quality census for octree mixed-level transition cells.

This module deliberately does not repair, reject, or reorder cells.  It makes
the geometry and writer-boundary evidence needed by HEX-OCT-TRANSITION-
QUALITY-1 explicit while keeping the experimental mixed-level realization
behind its existing opt-in flag.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

import numpy as np

from core.generator.native_hex.match_diagnostic import (
    _cell_centroid,
    _quad_skewness,
)
from core.generator.native_hex.metrics import CellFaces, _cell_volume
from core.generator.native_hex.sheet_diagnostic import _face_records
from core.generator.native_hex.transition_diagnostic import (
    ScalarSummary,
    _quad_face_warpage,
    _summary,
)

QUALITY_ENV = "AUTO_TESSELL_HEX_TRANSITION_QUALITY_DIAG"
BAD_BOUNDARY_SKEW_THRESHOLD = 2.0


def enabled() -> bool:
    """Return whether the opt-in transition quality census is enabled."""

    import os

    return os.environ.get(QUALITY_ENV, "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class TransitionQualityReport:
    """Deterministic, non-gating quality census for a builder output."""

    mode: str
    n_builder_points: int
    n_builder_cells: int
    n_transition_cells: int
    n_transition_faces_reported: int
    builder_face_incidence_histogram: dict[str, int]
    builder_boundary_face_count: int
    builder_boundary_area: float
    all_face_warpage: ScalarSummary
    transition_cell_face_warpage: ScalarSummary
    all_face_skewness: ScalarSummary
    transition_cell_face_skewness: ScalarSummary
    all_signed_volume: ScalarSummary
    transition_cell_signed_volume: ScalarSummary
    n_negative_signed_volume: int
    n_negative_transition_signed_volume: int
    all_orientation_free_volume: ScalarSummary
    transition_cell_orientation_free_volume: ScalarSummary
    writer_cells: int | None
    writer_dropped_cells: int | None
    writer_boundary_face_count: int | None
    writer_boundary_area: float | None
    writer_boundary_face_set_equal: bool | None
    writer_boundary_area_delta: float | None
    writer_boundary_added_face_count: int | None
    writer_boundary_removed_face_count: int | None
    writer_boundary_added_face_sample: tuple[tuple[int, ...], ...]
    predicted_writer_drop_count: int
    predicted_writer_drop_sample: tuple[int, ...]
    predicted_writer_drop_detail_sample: tuple[dict[str, object], ...]
    predicted_drop_exposed_internal_face_count: int
    predicted_drop_exposed_internal_face_sample: tuple[tuple[int, ...], ...]
    writer_drop_prediction_matches_actual: bool | None
    boundary_skew_threshold: float
    n_boundary_skew_bad_faces: int
    n_boundary_skew_bad_faces_transition_owner: int
    n_boundary_skew_bad_faces_transition_vertex_adjacent: int
    n_boundary_faces_transition_owner: int
    n_boundary_faces_transition_vertex_adjacent: int
    bad_face_transition_owner_rate: float | None
    bad_face_transition_vertex_adjacent_rate: float | None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable snapshot without mutating mesh inputs."""

        return asdict(self)


def _face_area(points: np.ndarray, face: Sequence[int]) -> float:
    """Return polygon area by a deterministic fan triangulation."""

    if len(face) < 3 or len(set(int(vertex) for vertex in face)) != len(face):
        return 0.0
    anchor = points[int(face[0])]
    area = 0.0
    for index in range(1, len(face) - 1):
        area += 0.5 * float(
            np.linalg.norm(
                np.cross(
                    points[int(face[index])] - anchor,
                    points[int(face[index + 1])] - anchor,
                )
            )
        )
    return float(area)


def _boundary_snapshot(
    points: np.ndarray,
    cell_faces: CellFaces,
) -> tuple[set[tuple[int, ...]], float, dict[str, int]]:
    """Return boundary keys, area, and face-incidence histogram."""

    records = _face_records(cell_faces)
    keys = {
        tuple(key)
        for key, (_cyclic, owners) in records.items()
        if len(owners) == 1
    }
    area = sum(
        _face_area(points, cyclic)
        for key, (cyclic, owners) in records.items()
        if len(owners) == 1 and tuple(key) in keys
    )
    incidence = {}
    for _key, (_cyclic, owners) in records.items():
        incidence[str(len(owners))] = incidence.get(str(len(owners)), 0) + 1
    return keys, float(area), dict(sorted(incidence.items()))


def _signed_cell_volume(points: np.ndarray, cell: Sequence[Sequence[int]]) -> float:
    """Return the signed volume implied by the emitted cyclic face winding."""

    if not cell:
        return 0.0
    vertex_ids = sorted({int(vertex) for face in cell for vertex in face})
    if len(vertex_ids) < 4:
        return 0.0
    center = points[np.asarray(vertex_ids, dtype=np.int64)].mean(axis=0)
    value = 0.0
    for face in cell:
        if len(face) < 3:
            continue
        anchor = points[int(face[0])] - center
        for index in range(1, len(face) - 1):
            edge_a = points[int(face[index])] - center
            edge_b = points[int(face[index + 1])] - center
            value += float(np.dot(anchor, np.cross(edge_a, edge_b))) / 6.0
    return float(value)


def _clean_face_for_writer(
    points: np.ndarray,
    face: Sequence[int],
    area_eps: float,
) -> list[int] | None:
    """Mirror the generic writer's reportable face-cleaning contract."""

    cleaned: list[int] = []
    seen: set[int] = set()
    for raw_vertex in face:
        vertex = int(raw_vertex)
        if cleaned and cleaned[-1] == vertex:
            continue
        if vertex in seen:
            continue
        cleaned.append(vertex)
        seen.add(vertex)
    if len(cleaned) >= 2 and cleaned[-1] == cleaned[0]:
        cleaned.pop()
    if len(cleaned) < 3:
        return None
    if _face_area(points, cleaned) <= area_eps:
        return None
    return cleaned


def _predicted_writer_drop_cells(
    points: np.ndarray,
    cells: Sequence[Sequence[Sequence[int]]],
) -> tuple[list[int], list[dict[str, object]]]:
    """Find cells rejected by the generic writer's visible face contract."""

    if len(points) == 0:
        area_eps = 1.0e-30
    else:
        bbox_diag = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
        area_eps = max((bbox_diag * 1.0e-12) ** 2, 1.0e-30)
    rejected: list[int] = []
    details: list[dict[str, object]] = []
    for cell_index, cell in enumerate(cells):
        cleaned_count = 0
        drop_cell = False
        for face_index, face in enumerate(cell):
            if _clean_face_for_writer(points, face, area_eps) is None:
                drop_cell = True
                unique_vertices = tuple(sorted({int(vertex) for vertex in face}))
                details.append(
                    {
                        "cell_index": int(cell_index),
                        "face_index": int(face_index),
                        "face_vertices": tuple(int(vertex) for vertex in face),
                        "face_coordinates": tuple(
                            tuple(float(value) for value in points[int(vertex)])
                            for vertex in face
                        ),
                        "n_unique_vertices": int(len(unique_vertices)),
                        "face_area": float(_face_area(points, face)),
                        "writer_area_eps": float(area_eps),
                    }
                )
                break
            cleaned_count += 1
        if drop_cell or cleaned_count < 4:
            rejected.append(int(cell_index))
    return rejected, details


def _metadata_transition_indices(
    cell_metadata: Sequence[Mapping[str, object]] | None,
    n_cells: int,
) -> tuple[list[int], int]:
    """Extract builder-side transition labels without inferring missing ones."""

    if cell_metadata is None or len(cell_metadata) != n_cells:
        return [], 0
    indices = [
        index
        for index, item in enumerate(cell_metadata)
        if int(item.get("transition_face_count", 0)) > 0
    ]
    n_faces = sum(
        int(cell_metadata[index].get("transition_face_count", 0)) for index in indices
    )
    return indices, n_faces


def _cell_face_warpage(points: np.ndarray, cell: Sequence[Sequence[int]]) -> list[float]:
    return [_quad_face_warpage(points, tuple(face)) for face in cell]


def _cell_face_skewness(points: np.ndarray, cell: Sequence[Sequence[int]]) -> list[float]:
    centroid = _cell_centroid(points, cell)
    values: list[float] = []
    for face in cell:
        if len(face) != 4 or len(set(int(vertex) for vertex in face)) != 4:
            continue
        skew, _area = _quad_skewness(points, centroid, face)
        values.append(float(skew))
    return values


def _boundary_transition_census(
    points: np.ndarray,
    cells: Sequence[Sequence[Sequence[int]]],
    records: Mapping[tuple[int, ...], tuple[Sequence[int], Sequence[int]]],
    transition_indices: Sequence[int],
) -> dict[str, object]:
    """Cross-tab bad boundary skew against builder transition adjacency.

    ``transition_vertex_adjacent`` is intentionally a broad, report-only
    one-ring proxy: it means a boundary face touches a vertex belonging to a
    metadata-labelled transition cell.  It is not promoted to an authoritative
    hanging-node label because the current metadata does not carry per-face
    transition-chain IDs.
    """

    transition_set = set(int(index) for index in transition_indices)
    transition_vertices = {
        int(vertex)
        for index in transition_set
        for face in cells[index]
        for vertex in face
    }
    n_boundary = 0
    n_bad = 0
    n_boundary_transition_owner = 0
    n_boundary_transition_vertex = 0
    n_bad_transition_owner = 0
    n_bad_transition_vertex = 0
    for key, (cyclic, owners) in records.items():
        if len(owners) != 1:
            continue
        n_boundary += 1
        owner = int(owners[0])
        owner_transition = owner in transition_set
        vertex_transition = bool(set(int(vertex) for vertex in key) & transition_vertices)
        n_boundary_transition_owner += int(owner_transition)
        n_boundary_transition_vertex += int(vertex_transition)
        if len(cyclic) != 4 or len(set(int(vertex) for vertex in cyclic)) != 4:
            continue
        skew, _area = _quad_skewness(
            points,
            _cell_centroid(points, cells[owner]),
            cyclic,
        )
        if skew < BAD_BOUNDARY_SKEW_THRESHOLD:
            continue
        n_bad += 1
        n_bad_transition_owner += int(owner_transition)
        n_bad_transition_vertex += int(vertex_transition)
    return {
        "n_boundary_skew_bad_faces": int(n_bad),
        "n_boundary_skew_bad_faces_transition_owner": int(n_bad_transition_owner),
        "n_boundary_skew_bad_faces_transition_vertex_adjacent": int(
            n_bad_transition_vertex
        ),
        "n_boundary_faces_transition_owner": int(n_boundary_transition_owner),
        "n_boundary_faces_transition_vertex_adjacent": int(n_boundary_transition_vertex),
        "bad_face_transition_owner_rate": (
            float(n_bad_transition_owner / n_bad) if n_bad else None
        ),
        "bad_face_transition_vertex_adjacent_rate": (
            float(n_bad_transition_vertex / n_bad) if n_bad else None
        ),
    }


def audit_transition_quality(
    points: np.ndarray,
    cell_faces: CellFaces,
    *,
    cell_metadata: Sequence[Mapping[str, object]] | None = None,
    writer_points: np.ndarray | None = None,
    writer_cell_faces: CellFaces | None = None,
) -> TransitionQualityReport:
    """Measure mixed-level quality and optional writer loss without gating.

    ``cell_metadata`` is accepted only from the builder that emitted
    ``cell_faces``.  If absent or misaligned, the report intentionally shows
    zero transition cells rather than guessing from face degree or topology.
    ``writer_cell_faces`` is optional so this function can be used both before
    and after a generic polyMesh writer boundary.
    """

    pts = np.asarray(points, dtype=np.float64)
    cells = [
        [[int(vertex) for vertex in face] for face in cell]
        for cell in cell_faces
    ]
    transition_indices, n_transition_faces = _metadata_transition_indices(
        cell_metadata, len(cells)
    )
    transition_set = set(transition_indices)
    records = _face_records(cells)
    _builder_boundary_keys, builder_boundary_area, incidence = _boundary_snapshot(
        pts, cells
    )

    all_warpage = [
        _quad_face_warpage(pts, tuple(cyclic))
        for cyclic, _owners in records.values()
    ]
    transition_warpage = [
        value
        for index in transition_indices
        for value in _cell_face_warpage(pts, cells[index])
    ]
    all_skewness = [
        value for cell in cells for value in _cell_face_skewness(pts, cell)
    ]
    transition_skewness = [
        value
        for index in transition_indices
        for value in _cell_face_skewness(pts, cells[index])
    ]
    signed_volumes = [_signed_cell_volume(pts, cell) for cell in cells]
    transition_signed_volumes = [signed_volumes[index] for index in transition_indices]
    orientation_free_volumes = [_cell_volume(pts, cell) for cell in cells]
    transition_orientation_free_volumes = [
        orientation_free_volumes[index] for index in transition_indices
    ]
    predicted_writer_drop_cells, predicted_writer_drop_details = _predicted_writer_drop_cells(
        pts, cells
    )
    predicted_drop_set = set(predicted_writer_drop_cells)
    predicted_drop_exposed_internal_faces = sorted(
        tuple(int(vertex) for vertex in key)
        for key, (_cyclic, owners) in records.items()
        if len(owners) == 2
        and ((int(owners[0]) in predicted_drop_set) != (int(owners[1]) in predicted_drop_set))
    )
    transition_census = _boundary_transition_census(
        pts,
        cells,
        records,
        transition_indices,
    )

    writer_cells: int | None = None
    writer_dropped: int | None = None
    writer_boundary_count: int | None = None
    writer_boundary_area: float | None = None
    writer_boundary_equal: bool | None = None
    writer_area_delta: float | None = None
    writer_boundary_added: list[tuple[int, ...]] = []
    writer_boundary_removed: list[tuple[int, ...]] = []
    if writer_cell_faces is not None:
        out_pts = pts if writer_points is None else np.asarray(writer_points, dtype=np.float64)
        writer_cells = len(writer_cell_faces)
        writer_dropped = max(0, len(cells) - writer_cells)
        writer_keys, writer_boundary_area_value, writer_incidence = _boundary_snapshot(
            out_pts, writer_cell_faces
        )
        writer_boundary_count = int(writer_incidence.get("1", 0))
        writer_boundary_area = float(writer_boundary_area_value)
        writer_boundary_equal = writer_keys == _builder_boundary_keys
        writer_area_delta = float(writer_boundary_area_value - builder_boundary_area)
        writer_boundary_added = sorted(writer_keys - _builder_boundary_keys)
        writer_boundary_removed = sorted(_builder_boundary_keys - writer_keys)
        writer_drop_prediction_matches_actual = len(predicted_writer_drop_cells) == writer_dropped
    else:
        writer_drop_prediction_matches_actual = None

    if not np.array_equal(pts, np.asarray(points, dtype=np.float64)):
        raise AssertionError("HEX-OCT-TRANSITION-QUALITY-1 mutated points")

    return TransitionQualityReport(
        mode="report-only",
        n_builder_points=int(pts.shape[0]),
        n_builder_cells=len(cells),
        n_transition_cells=len(transition_indices),
        n_transition_faces_reported=int(n_transition_faces),
        builder_face_incidence_histogram=incidence,
        builder_boundary_face_count=int(incidence.get("1", 0)),
        builder_boundary_area=float(builder_boundary_area),
        all_face_warpage=_summary(all_warpage),
        transition_cell_face_warpage=_summary(transition_warpage),
        all_face_skewness=_summary(all_skewness),
        transition_cell_face_skewness=_summary(transition_skewness),
        all_signed_volume=_summary(signed_volumes),
        transition_cell_signed_volume=_summary(transition_signed_volumes),
        n_negative_signed_volume=sum(value < 0.0 for value in signed_volumes),
        n_negative_transition_signed_volume=sum(
            value < 0.0 for value in transition_signed_volumes
        ),
        all_orientation_free_volume=_summary(orientation_free_volumes),
        transition_cell_orientation_free_volume=_summary(
            transition_orientation_free_volumes
        ),
        writer_cells=writer_cells,
        writer_dropped_cells=writer_dropped,
        writer_boundary_face_count=writer_boundary_count,
        writer_boundary_area=writer_boundary_area,
        writer_boundary_face_set_equal=writer_boundary_equal,
        writer_boundary_area_delta=writer_area_delta,
        writer_boundary_added_face_count=(
            len(writer_boundary_added) if writer_cell_faces is not None else None
        ),
        writer_boundary_removed_face_count=(
            len(writer_boundary_removed) if writer_cell_faces is not None else None
        ),
        writer_boundary_added_face_sample=tuple(writer_boundary_added[:16]),
        predicted_writer_drop_count=len(predicted_writer_drop_cells),
        predicted_writer_drop_sample=tuple(predicted_writer_drop_cells[:32]),
        predicted_writer_drop_detail_sample=tuple(predicted_writer_drop_details[:8]),
        predicted_drop_exposed_internal_face_count=len(
            predicted_drop_exposed_internal_faces
        ),
        predicted_drop_exposed_internal_face_sample=tuple(
            predicted_drop_exposed_internal_faces[:16]
        ),
        writer_drop_prediction_matches_actual=writer_drop_prediction_matches_actual,
        boundary_skew_threshold=BAD_BOUNDARY_SKEW_THRESHOLD,
        **transition_census,
    )
