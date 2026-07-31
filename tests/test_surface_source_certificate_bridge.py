"""Deferred bridge contracts for existing tri and strict-quad diagnostics."""

from __future__ import annotations

from hashlib import sha256

import numpy as np
import trimesh

from core.evaluator.surface_source_certificate_bridge import (
    report_native_tri_source_certificate_bridge,
    report_strict_quad_pair_source_certificate_bridge,
)
from core.preprocessor.native_quad.strict_pair_preflight import (
    diagnose_strict_quad_pair_preflight,
)
from core.preprocessor.native_tri.certificate import diagnose_native_tri_source_certificate

_ALL_EVIDENCE = ("source_shape", "feature", "patch", "physical_group", "provenance")


def _cube_tri_diagnostic():
    mesh = trimesh.creation.box()
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    source_edges = tuple(
        sorted(
            {
                (min(int(first), int(second)), max(int(first), int(second)))
                for face in faces.tolist()
                for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))
            }
        )
    )
    before = sha256(vertices.tobytes() + faces.tobytes()).hexdigest()
    diagnostic = diagnose_native_tri_source_certificate(
        vertices,
        faces,
        vertices.copy(),
        faces.copy(),
        face_provenance=tuple((index,) for index in range(len(faces))),
        source_patch_ids=tuple("wall" for _ in faces),
        source_feature_edges=source_edges,
    )
    assert sha256(vertices.tobytes() + faces.tobytes()).hexdigest() == before
    assert diagnostic.feature_ownership_explicit
    assert diagnostic.declared_feature_edges_sha256 is not None
    return diagnostic


def _strict_quad_preflight():
    vertices = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)),
        dtype=np.float64,
    )
    triangles = np.asarray(((0, 1, 2), (0, 2, 3)), dtype=np.int64)
    report = diagnose_strict_quad_pair_preflight(
        vertices,
        vertices.copy(),
        triangles,
        np.empty((0, 3), dtype=np.int64),
        np.asarray(((1, 2, 3, 0),), dtype=np.int64),
        np.asarray(((0, 1),), dtype=np.int64),
        np.asarray(((0, 1), (1, 2), (2, 3), (0, 3)), dtype=np.int64),
        source_patch_ids=("wall", "wall"),
        candidate_quad_patch_ids=("wall",),
    )
    assert report.accepted
    return report


def _assert_deferred(report: object) -> None:
    assert getattr(report, "product_accepted") is False
    assert getattr(report, "candidate_constructed") is False
    assert getattr(report, "production_mesh_changed") is False
    assert getattr(report, "artifact_delta") == 0
    schema = getattr(report, "schema_report")
    assert schema.product_accepted is False
    assert schema.product_rejection == "source_product_certificate_required"


def test_tri_bridge_binds_only_existing_explicit_feature_hash_and_defers_rest() -> None:
    diagnostic = _cube_tri_diagnostic()
    reports = tuple(report_native_tri_source_certificate_bridge(diagnostic) for _ in range(3))

    assert reports == (reports[0],) * 3
    report = reports[0]
    assert report.status == "defer_missing_authoritative_source_certificate_evidence"
    assert report.directly_bound_evidence == ("feature",)
    assert report.deferred_evidence == (
        "source_shape",
        "patch",
        "physical_group",
        "provenance",
    )
    _assert_deferred(report)


def test_strict_quad_bridge_does_not_relabel_structural_hashes_as_authority() -> None:
    preflight = _strict_quad_preflight()
    reports = tuple(report_strict_quad_pair_source_certificate_bridge(preflight) for _ in range(3))

    assert reports == (reports[0],) * 3
    report = reports[0]
    assert report.status == "defer_missing_authoritative_source_certificate_evidence"
    assert report.directly_bound_evidence == ()
    assert report.deferred_evidence == _ALL_EVIDENCE
    _assert_deferred(report)


def test_invalid_bridge_objects_fail_closed_without_schema_completion() -> None:
    tri_report = report_native_tri_source_certificate_bridge(object())
    quad_report = report_strict_quad_pair_source_certificate_bridge(object())

    assert tri_report.status == "defer_invalid_native_tri_source_certificate"
    assert quad_report.status == "defer_invalid_strict_quad_pair_preflight"
    assert tri_report.deferred_evidence == _ALL_EVIDENCE
    assert quad_report.deferred_evidence == _ALL_EVIDENCE
    _assert_deferred(tri_report)
    _assert_deferred(quad_report)
