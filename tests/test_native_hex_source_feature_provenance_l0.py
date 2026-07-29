"""L0 source-entity boundary tests; geometry-derived feature inference is forbidden."""

from __future__ import annotations

import numpy as np

from core.generator.native_hex.source_feature_provenance_l0 import (
    audit_source_entity_boundaries_l0,
)

_TETRA_POINTS = np.asarray(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
_TETRA_FACES = np.asarray(((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)), dtype=np.int64)


def test_one_authoritative_entity_has_no_invented_feature_boundaries() -> None:
    report = audit_source_entity_boundaries_l0(
        _TETRA_POINTS,
        _TETRA_FACES,
        (("source", "wall"),) * 4,
    )

    assert report.status == "pass_authoritative_source_entity_boundaries"
    assert report.two_manifold_edge_count == 6
    assert not report.entity_boundaries
    assert not report.entity_boundary_components
    assert report.supplied_entities_are_authoritative
    assert report.source_geometry_unchanged
    assert not report.production_mesh_changed


def test_patch_discontinuity_is_preserved_as_an_authoritative_edge_set() -> None:
    entities = (("source", "low"), ("source", "high"), ("source", "low"), ("source", "low"))
    first = audit_source_entity_boundaries_l0(_TETRA_POINTS, _TETRA_FACES, entities)
    second = audit_source_entity_boundaries_l0(_TETRA_POINTS, _TETRA_FACES, entities)

    assert first.status == "pass_authoritative_source_entity_boundaries"
    assert tuple(item.edge for item in first.entity_boundaries) == ((0, 1), (0, 3), (1, 3))
    assert all(
        item.incident_entities[0] != item.incident_entities[1] for item in first.entity_boundaries
    )
    assert first.entity_boundary_components == ((0, 1, 3),)
    assert first.entity_boundaries == second.entity_boundaries


def test_missing_entities_and_open_surface_fail_closed() -> None:
    missing = audit_source_entity_boundaries_l0(_TETRA_POINTS, _TETRA_FACES, ())
    open_surface = audit_source_entity_boundaries_l0(
        _TETRA_POINTS[:3],
        np.asarray(((0, 1, 2),), dtype=np.int64),
        (("source", "wall"),),
    )

    assert missing.status == "reject_missing_authoritative_face_entities"
    assert not missing.supplied_entities_are_authoritative
    assert open_surface.status == "reject_source_not_closed_two_manifold"
    assert not open_surface.supplied_entities_are_authoritative
