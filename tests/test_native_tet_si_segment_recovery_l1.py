"""Canonical cube L1 for the deterministic Si segment-recovery experiment.

This is deliberately a candidate-array experiment, not a production mesher
integration.  It establishes the source-ledger gate required before such an
integration can be considered.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import Delaunay

from core.generator.native_tet.chen_source_edge_chain_l1 import audit_source_edge_chain_l1
from core.generator.native_tet.chen_source_facet_worklist_l0 import (
    build_source_facet_recovery_worklist_l0,
)
from core.generator.native_tet.input_surface_ledger_l0 import audit_input_surface_ledger_l0
from core.generator.native_tet.mesher import _inside_winding_number, _seed_points_uniform
from core.generator.native_tet.seed_source_coordinate_dedupe_l0 import (
    plan_seed_source_coordinate_dedupe_l0,
)
from core.generator.native_tet.si_segment_split_plan_l0 import plan_si_segment_split_l0
from core.generator.native_tet.source_complex_canonicalization_l0 import (
    canonicalize_source_complex_l0,
)


def _canonical_cube_seed() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    fixture = Path(__file__).parent / "benchmarks" / "cube.stl"
    raw = trimesh.load_mesh(fixture, process=False)
    assert isinstance(raw, trimesh.Trimesh)
    canonical = canonicalize_source_complex_l0(raw.vertices, raw.faces)
    assert canonical.accepted
    points = np.asarray(canonical.canonical_points, dtype=np.float64)
    faces = np.asarray(canonical.canonical_faces, dtype=np.int64)
    target = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0))) / 4
    grid = _seed_points_uniform(points.min(axis=0), points.max(axis=0), target)
    grid = grid[_inside_winding_number(grid, points, faces)]
    dedupe = plan_seed_source_coordinate_dedupe_l0(points, grid)
    assert dedupe.accepted and len(dedupe.removed_grid_indices) == 1
    return points, faces, np.asarray(dedupe.filtered_grid_points, dtype=np.float64)


def _source_edges(faces: np.ndarray) -> tuple[tuple[int, int], ...]:
    edges: set[tuple[int, int]] = set()
    for face in faces:
        for index in range(3):
            first, second = int(face[index]), int(face[(index + 1) % 3])
            edges.add((first, second) if first < second else (second, first))
    return tuple(sorted(edges))


def test_two_deterministic_si_midpoints_close_cube_source_edge_and_surface_ledgers() -> None:
    source_points, source_faces, grid = _canonical_cube_seed()
    base_points = np.vstack((source_points, grid))
    edges = _source_edges(source_faces)
    base_tets = np.asarray(Delaunay(base_points).simplices, dtype=np.int64)
    base_audits = tuple(audit_source_edge_chain_l1(base_points, edge, base_tets) for edge in edges)
    assert Counter(audit.reason for audit in base_audits) == Counter(
        {"accepted": 16, "source_edge_partition_gap": 2}
    )
    plans = tuple(
        plan_si_segment_split_l0(base_points, edge, edges)
        for edge, audit in zip(edges, base_audits, strict=True)
        if audit.reason == "source_edge_partition_gap"
    )
    assert all(plan.accepted and plan.candidate_point is not None for plan in plans)
    proposals = np.asarray([plan.candidate_point for plan in plans], dtype=np.float64)
    candidate_points = np.vstack((base_points, proposals))
    first_tets = np.asarray(Delaunay(candidate_points).simplices, dtype=np.int64)
    second_tets = np.asarray(Delaunay(candidate_points).simplices, dtype=np.int64)
    assert np.array_equal(np.sort(first_tets, axis=1), np.sort(second_tets, axis=1))
    candidate_audits = tuple(
        audit_source_edge_chain_l1(candidate_points, edge, first_tets) for edge in edges
    )
    assert all(audit.accepted for audit in candidate_audits)
    assert audit_input_surface_ledger_l0(
        source_points, source_faces, candidate_points, first_tets
    ).accepted
    assert (
        len(
            build_source_facet_recovery_worklist_l0(
                candidate_points, first_tets, source_faces
            ).items
        )
        == 10
    )
