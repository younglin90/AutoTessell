"""HEX-TRANSITION-DIAG1 read-only input audit and quality baseline.

The Elsheikh and Chen transition-chain mechanisms require information that is
not recoverable from a final ``points``/``cells`` cache alone: octree lineage,
hanging-node valence, the selected transition template, and authoritative
boundary provenance.  This module therefore refuses to infer those labels.

It reuses :mod:`patch_layer_diagnostic` for the existing patch/layer census and
computes only geometry-only baselines that are valid on the cached mesh.  The
report is intentionally ``BLOCKED`` until a cache bundle carries the metadata
listed in :data:`REQUIRED_METADATA_INPUTS`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np

from core.generator.native_hex.metrics import CellFaces
from core.generator.native_hex.patch_layer_diagnostic import (
    PatchLayerDiagnosticReport,
    analyze_patch_layer_subsets,
    reconstruct_native_hex_patch_provenance,
)
from core.generator.native_hex.sheet_diagnostic import _face_records

REQUIRED_METADATA_INPUTS: tuple[str, ...] = (
    "per-cell octree level and stable leaf lineage/origin",
    "per-face transition_chain_id and hanging_node_valence",
    "per-cell emitted template_class",
    "authoritative per-boundary-face patch and source provenance",
)


@dataclass(frozen=True)
class ScalarSummary:
    """Finite-value summary for a geometry-only diagnostic quantity."""

    n: int
    minimum: float | None
    p50: float | None
    p95: float | None
    maximum: float | None


@dataclass(frozen=True)
class TransitionDiagnosticReport:
    """Blocked exact cross-tab plus measurable geometry-only baselines."""

    shape_name: str
    n_points: int
    n_cells: int
    cache_fields: tuple[str, ...]
    status: Literal["BLOCKED"]
    blocker_reasons: tuple[str, ...]
    required_metadata_inputs: tuple[str, ...]
    patch_provenance_mode: str
    patch_layer: PatchLayerDiagnosticReport
    all_face_warpage: ScalarSummary
    boundary_face_warpage: ScalarSummary
    cell_local_scaled_jacobian_magnitude: ScalarSummary

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable report without changing the source mesh."""
        return asdict(self)


def _summary(values: list[float]) -> ScalarSummary:
    finite = np.asarray([value for value in values if np.isfinite(value)], dtype=np.float64)
    if finite.size == 0:
        return ScalarSummary(0, None, None, None, None)
    return ScalarSummary(
        n=int(finite.size),
        minimum=float(np.min(finite)),
        p50=float(np.percentile(finite, 50)),
        p95=float(np.percentile(finite, 95)),
        maximum=float(np.max(finite)),
    )


def _quad_face_warpage(points: np.ndarray, face: tuple[int, ...]) -> float:
    """Chen-style quad warpage, ``1 - min(n0·n2, n1·n3)``.

    The face must be cyclic.  Degenerate faces return ``nan`` so the caller
    cannot silently turn an invalid face into a good quality value.
    """
    if len(face) != 4 or len(set(face)) != 4:
        return float("nan")
    corners = points[np.asarray(face, dtype=np.int64)]
    normals: list[np.ndarray] = []
    for index in range(4):
        current = corners[index]
        next_point = corners[(index + 1) % 4]
        previous = corners[(index - 1) % 4]
        normal = np.cross(next_point - current, previous - current)
        norm = float(np.linalg.norm(normal))
        if norm <= 1.0e-30:
            return float("nan")
        normals.append(normal / norm)
    value = 1.0 - min(
        float(np.dot(normals[0], normals[2])),
        float(np.dot(normals[1], normals[3])),
    )
    return float(np.clip(value, 0.0, 1.0))


def _cell_local_scaled_jacobian_magnitude(points: np.ndarray, cell: list[list[int]]) -> float:
    """Return the minimum absolute corner scaled-Jacobian magnitude.

    This is deliberately a magnitude baseline.  A signed validity claim needs
    the production cell orientation/lineage, which is one of the missing card
    inputs and is not reconstructed here.
    """
    if len(cell) != 6 or any(len(face) != 4 for face in cell):
        return float("nan")
    vertex_ids = sorted({int(vertex) for face in cell for vertex in face})
    if len(vertex_ids) != 8:
        return float("nan")
    incident: dict[int, set[int]] = {vertex: set() for vertex in vertex_ids}
    for face in cell:
        for index, vertex_raw in enumerate(face):
            vertex = int(vertex_raw)
            incident[vertex].update((int(face[index - 1]), int(face[(index + 1) % len(face)])))
    values: list[float] = []
    for vertex in vertex_ids:
        neighbors = sorted(incident[vertex])
        if len(neighbors) != 3:
            return float("nan")
        edges = points[np.asarray(neighbors, dtype=np.int64)] - points[vertex]
        lengths = np.linalg.norm(edges, axis=1)
        denominator = float(np.prod(lengths))
        if denominator <= 1.0e-30:
            return float("nan")
        determinant = abs(float(np.dot(edges[0], np.cross(edges[1], edges[2]))))
        values.append(determinant / denominator)
    return min(values, default=float("nan"))


def audit_transition_inputs(
    shape_name: str,
    points: np.ndarray,
    cell_faces: CellFaces,
    *,
    cache_fields: tuple[str, ...] = ("points", "cells"),
) -> TransitionDiagnosticReport:
    """Audit a cache without inferring transition labels or mutating inputs.

    ``patch_layer`` is the existing PATCH-LAYER-DIAG1 report.  Its
    writer-equivalent ``patch/defaultWall`` labels are retained as an explicit
    reconstruction mode, not promoted to authoritative source provenance.
    """
    pts = np.asarray(points, dtype=np.float64)
    cells = [[[int(vertex) for vertex in face] for face in cell] for cell in cell_faces]
    points_before = pts.copy()
    cells_before = [[list(face) for face in cell] for cell in cells]

    labels = reconstruct_native_hex_patch_provenance(pts, cells)
    patch_layer = analyze_patch_layer_subsets(
        shape_name,
        pts,
        cells,
        boundary_patch_provenance=labels,
        log_only=False,
    )

    records = _face_records(cells)
    all_face_warpage = [
        _quad_face_warpage(pts, tuple(cyclic)) for cyclic, _owners in records.values()
    ]
    boundary_face_warpage = [
        _quad_face_warpage(pts, tuple(cyclic))
        for cyclic, owners in records.values()
        if len(owners) == 1
    ]
    local_scaled_jacobians = [_cell_local_scaled_jacobian_magnitude(pts, cell) for cell in cells]

    if not np.array_equal(pts, points_before) or cells != cells_before:
        raise AssertionError("HEX-TRANSITION-DIAG1 mutated its input mesh")

    blockers = (
        "cache contains points/cells only; octree leaf lineage and per-cell levels are absent",
        "transition-chain IDs and hanging-node valence are absent",
        "emitted transition template classes are absent",
        "authoritative boundary patch/source provenance is absent; "
        "PATCH-LAYER reconstruction is not source metadata",
    )
    return TransitionDiagnosticReport(
        shape_name=str(shape_name),
        n_points=int(pts.shape[0]),
        n_cells=len(cells),
        cache_fields=tuple(sorted(str(field) for field in cache_fields)),
        status="BLOCKED",
        blocker_reasons=blockers,
        required_metadata_inputs=REQUIRED_METADATA_INPUTS,
        patch_provenance_mode="writer-equivalent feature patch + defaultWall (reconstructed)",
        patch_layer=patch_layer,
        all_face_warpage=_summary(all_face_warpage),
        boundary_face_warpage=_summary(boundary_face_warpage),
        cell_local_scaled_jacobian_magnitude=_summary(local_scaled_jacobians),
    )
