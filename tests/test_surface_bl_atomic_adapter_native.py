"""Native planner to atomic-certificate integration evidence."""

from __future__ import annotations

import copy
from dataclasses import asdict

import numpy as np
import pytest

from core.layers.native_bl_atomic_certificate import SourceAuthority
from core.layers.surface_bl_atomic_adapter import _hash, certify_and_persist_surface_plan


native_sector = pytest.importorskip("native_surface_bl_front_sector")


def test_native_integer_wall_edge_ids_are_normalized_and_certified() -> None:
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, -1, 0]], dtype=np.float64)
    edges = np.array([[17, 0, 1, 0, 0]], dtype=np.int64)
    normals = np.array([[0, 0, 1]], dtype=np.float64)
    plan = native_sector.plan_surface_wall_edge_sectors(
        points, edges, normals, ["wall"], ["feature"], ["fluid"], ["left"],
        1, 0.2, 1.0, np.array([[0, 1, 2], [0, 1, 3]], dtype=np.int64),
    )
    assert plan["accepted"] is True
    source = {"source": "native-test", "faces": ["wall"]}
    authority = SourceAuthority(
        topology="surface-topo", source="native-test", feature="feature", patch="wall",
        physical_group="fluid", provenance="ledger", wall_edges=("17",),
    )
    evidence = {"source_sha256": _hash(source), "authority_sha256": _hash(asdict(authority)), "wall_edges": ["17"]}
    topology = {"invalid": 0, "inverted": 0, "duplicate": 0, "non_manifold": 0, "self_intersecting": 0}
    quality = {"min_jacobian": 0.1, "min_area": 0.2, "max_non_orthogonality": 20.0, "max_skewness": 0.1, "metric_distortion": 1.0, "metric_aspect_ratio": 1.0}
    destination = copy.deepcopy(source)
    certificate = certify_and_persist_surface_plan(
        source, authority, dict(plan), destination, requested_layers=1, first_height=0.2,
        growth_ratio=1.0, authority_evidence=evidence, topology_evidence=topology,
        quality_evidence=quality,
    )
    assert certificate.accepted
    assert destination["status"] == "candidate_plan_ready"
