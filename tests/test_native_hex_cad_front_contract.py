"""Contract-only CAD entity ingress for the native all-hex research lane."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers.step import (
    CadNativeTriangulation,
    load_cad_native,
    load_cad_native_with_provenance,
)
from core.generator.native_hex.source_feature_provenance_l0 import (
    audit_source_entity_boundaries_l0,
)
from core.generator.native_hex.source_quad_feature_provenance_l1 import (
    audit_quadized_entity_boundaries_l1,
)

FIXTURE = Path("tests/benchmarks/t_junction.step")
LEGACY_VERTEX_SHA256 = "12d7fe77d022a49bb2b877302fd30472b0dbfef65b1c268439c9e76d70930a9c"
LEGACY_FACE_SHA256 = "80462a27612ef87554a947f946529569cea22b22d2b124bd5443d015c2fb0a3c"


def _ocp_available() -> bool:
    try:
        from OCP.STEPControl import STEPControl_Reader  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(not _ocp_available(), reason="OCP not installed")


def _load() -> CadNativeTriangulation:
    return load_cad_native_with_provenance(FIXTURE, ".step")


def test_legacy_array_byte_and_order_contract_is_unchanged() -> None:
    legacy_vertices, legacy_faces = load_cad_native(FIXTURE, ".step")
    result = _load()

    assert np.array_equal(result.vertices, legacy_vertices)
    assert np.array_equal(result.faces, legacy_faces)
    assert sha256(result.vertices.tobytes()).hexdigest() == LEGACY_VERTEX_SHA256
    assert sha256(result.faces.tobytes()).hexdigest() == LEGACY_FACE_SHA256


def test_t_junction_exposes_authoritative_face_orientation_and_seams() -> None:
    result = _load()
    provenance = result.provenance

    assert provenance.status == "partial_authority_physical_groups_unavailable"
    assert provenance.face_count == 12
    assert provenance.topological_edge_count == 18
    assert len(result.vertices) == 3404
    assert len(result.faces) == 3392
    assert len(provenance.canonical_vertex_source_ids) == 1696
    assert provenance.face_ordinals_authoritative
    assert provenance.face_orientation_authoritative
    assert provenance.seam_connectivity_authoritative
    assert set(provenance.triangle_face_ordinals) == set(range(12))
    assert np.count_nonzero(provenance.triangle_orientation_reversed) > 0

    directed_edges: Counter[tuple[int, int]] = Counter()
    for face in provenance.oriented_canonical_faces:
        for first, second in zip(face, np.roll(face, -1), strict=True):
            directed_edges[(int(first), int(second))] += 1
    assert directed_edges
    assert all(count == 1 for count in directed_edges.values())
    assert all(directed_edges[(second, first)] == 1 for first, second in directed_edges)


def test_cad_face_authority_reaches_exact_source_quads_without_routing() -> None:
    result = _load()
    provenance = result.provenance
    canonical_vertices = result.vertices[provenance.canonical_vertex_source_ids]
    entities = tuple(
        ("t-junction", f"brep-face-{int(face)}") for face in provenance.triangle_face_ordinals
    )

    source = audit_source_entity_boundaries_l0(
        canonical_vertices, provenance.oriented_canonical_faces, entities
    )
    quads = audit_quadized_entity_boundaries_l1(
        canonical_vertices, provenance.oriented_canonical_faces, entities
    )

    assert source.status == "pass_authoritative_source_entity_boundaries"
    assert len(source.entity_boundaries) == 1696
    assert len(source.entity_boundary_components) == 12
    assert quads.status == "pass_exact_quad_entity_boundary_provenance"
    assert quads.expected_quad_entity_boundary_segment_count == 3392
    assert quads.observed_quad_entity_boundary_segment_count == 3392
    assert quads.no_spurious_quad_entity_boundaries
    assert quads.quadization.max_support_distance == 0.0
    assert quads.quadization.max_relative_area_error == 0.0


def test_missing_xde_names_and_physical_groups_stay_unknown() -> None:
    provenance = _load().provenance

    assert not provenance.physical_groups_authoritative
    assert provenance.face_names == (None,) * 12
    assert provenance.physical_group_names == (None,) * 12


def test_entity_orientation_and_seam_hashes_repeat_three_times() -> None:
    reports = [_load().provenance for _ in range(3)]
    signatures = {
        (
            report.ordered_triangle_coordinate_sha256,
            report.ordered_face_ordinal_sha256,
            report.ordered_orientation_sha256,
            report.seam_connectivity_sha256,
        )
        for report in reports
    }
    assert len(signatures) == 1
