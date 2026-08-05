"""Atomic certificate integration for the C++ shared surface front."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np

BUILD = Path("/tmp/autotessell_surface_bl_front_shared_build")
if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))

from native_surface_bl_front_shared import plan_shared_surface_wall_edge_front  # noqa: E402

from core.layers.native_bl_atomic_certificate import SourceAuthority  # noqa: E402
from core.layers.native_tet_shared_front_atomic_adapter import certify_and_persist_shared_surface_plan  # noqa: E402
from core.layers.surface_bl_atomic_adapter import _hash  # noqa: E402


def _case() -> tuple[dict[str, object], SourceAuthority, dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]], dtype=float)
    edges = np.array([[11, 0, 1, 0], [12, 1, 2, 0]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, 1.0]], dtype=float)
    plan = plan_shared_surface_wall_edge_front(points, edges, normals, ["wall"], ["unclassified_boundary"], ["fluid_wall"], 2, 0.1, 1.2)
    source = {"vertices": points.tolist(), "edges": edges.tolist()}
    authority = SourceAuthority(
        topology="surface-topo", source="shared-front", feature="unclassified_boundary",
        patch="wall", physical_group="fluid_wall", provenance="shared-front",
        wall_edges=("11", "12"),
    )
    evidence = {"source_sha256": _hash(source), "authority_sha256": _hash({
        "topology": authority.topology, "source": authority.source, "feature": authority.feature,
        "patch": authority.patch, "physical_group": authority.physical_group, "provenance": authority.provenance,
        "wall_faces": authority.wall_faces, "wall_edges": authority.wall_edges,
        "ambiguous": authority.ambiguous, "already_layered": authority.already_layered,
    }), "wall_edges": ["11", "12"]}
    topology = {"invalid": 0, "inverted": 0, "duplicate": 0, "non_manifold": 0, "self_intersecting": 0}
    quality = {"min_jacobian": 0.1, "min_area": float(plan["quality"]["min_signed_area"]),
               "max_non_orthogonality": 25.0, "max_skewness": 0.2,
               "metric_distortion": 1.1, "metric_aspect_ratio": 1.5}
    return source, authority, plan, evidence, topology, quality


def _certify(source, authority, plan, evidence, topology, quality, destination):
    return certify_and_persist_shared_surface_plan(
        source, authority, plan, destination, requested_layers=2,
        first_height=0.1, growth_ratio=1.2, authority_evidence=evidence,
        topology_evidence=topology, quality_evidence=quality,
    )


def test_shared_front_certifies_without_expanding_shared_vertices() -> None:
    source, authority, plan, evidence, topology, quality = _case()
    certificates = []
    for _ in range(2):
        destination = copy.deepcopy(source)
        certificate = _certify(source, authority, plan, evidence, topology, quality, destination)
        assert certificate.accepted
        certificates.append(certificate.serialized())
    assert certificates[0] == certificates[1]


def test_shared_lineage_and_quality_failures_refuse_atomically() -> None:
    source, authority, plan, evidence, topology, quality = _case()
    malformed = copy.deepcopy(plan)
    malformed["provenance"][0]["generated_vertices"] = [999, 1000]  # type: ignore[index]
    destination = copy.deepcopy(source)
    certificate = _certify(source, authority, malformed, evidence, topology, quality, destination)
    assert not certificate.accepted and certificate.reasons == ("shared_lineage_vertex_not_generated",)
    assert destination == source

    missing_quality = dict(quality)
    missing_quality.pop("max_skewness")
    destination = copy.deepcopy(source)
    certificate = _certify(source, authority, plan, evidence, topology, missing_quality, destination)
    assert not certificate.accepted and certificate.reasons == ("missing_quality_evidence",)
    assert destination == source

    bad_topology = dict(topology, non_manifold=1)
    destination = copy.deepcopy(source)
    certificate = _certify(source, authority, plan, evidence, bad_topology, quality, destination)
    assert not certificate.accepted and certificate.reasons == ("topology_non_manifold",)
    assert destination == source


def test_shared_front_bl0_remains_exact_source_bypass() -> None:
    source, authority, _, _, topology, quality = _case()
    destination = copy.deepcopy(source)
    certificate = certify_and_persist_shared_surface_plan(
        source, authority, None, destination, requested_layers=0,
        first_height=0.0, growth_ratio=1.0, authority_evidence=None,
        topology_evidence=topology, quality_evidence=quality,
    )
    assert certificate.accepted and destination == source
