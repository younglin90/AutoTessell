"""Actual native-tri route-output certificate L0 contracts."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import trimesh

from core.preprocessor.native_tri.product_output_certificate_l0 import (
    diagnose_native_tri_product_output_l0,
)
from core.preprocessor.native_tri.route import run_native_tri_l2_route


def _cube() -> tuple[np.ndarray, np.ndarray]:
    mesh = trimesh.creation.box()
    return (
        np.ascontiguousarray(mesh.vertices, dtype=np.float64),
        np.ascontiguousarray(mesh.faces, dtype=np.int64),
    )


def _assert_never_product_success(certificate: object) -> None:
    assert getattr(certificate, "accepted") is False
    assert getattr(certificate, "mesher_success_allowed") is False
    assert getattr(certificate, "product_claimed") is False


def test_actual_route_clone_has_complete_l0_source_evidence_but_not_product_success() -> None:
    vertices, faces = _cube()
    route = run_native_tri_l2_route(vertices, faces, target_faces=6, boundary_layers=0)
    certificates = tuple(
        diagnose_native_tri_product_output_l0(vertices, faces, route) for _ in range(3)
    )

    certificate = certificates[0]
    assert certificates == (certificate,) * 3
    assert certificate.status == "reject_native_tri_route_not_product_ready"
    assert certificate.rejection_reason == "source_contract_unavailable"
    assert certificate.source_output_hashes_match is True
    assert certificate.route_flags_match_certificate is True
    assert certificate.source_vertices_preserved is True
    assert certificate.source_faces_preserved is True
    assert certificate.topology_preserved is True
    assert certificate.provenance_preserved is True
    assert certificate.source_certificate.accepted is True
    _assert_never_product_success(certificate)


def test_forged_output_or_route_flag_rejects_before_product_claim() -> None:
    vertices, faces = _cube()
    route = run_native_tri_l2_route(vertices, faces, target_faces=None)
    moved_output = route.vertices.copy()
    moved_output[0, 0] += 1e-6
    forged_output = replace(route, vertices=moved_output)
    forged_flag = replace(route, topology_preserved=False)

    output_certificate = diagnose_native_tri_product_output_l0(vertices, faces, forged_output)
    flag_certificate = diagnose_native_tri_product_output_l0(vertices, faces, forged_flag)

    for certificate in (output_certificate, flag_certificate):
        assert certificate.status == "reject_native_tri_output_source_certificate_invalid"
        assert certificate.rejection_reason == "native_tri_output_source_certificate_invalid"
        _assert_never_product_success(certificate)
    assert output_certificate.source_vertices_preserved is False
    assert flag_certificate.route_flags_match_certificate is False


def test_boundary_layer_request_remains_explicit_route_rejection_not_mesher_success() -> None:
    vertices, faces = _cube()
    route = run_native_tri_l2_route(vertices, faces, target_faces=12, boundary_layers=2)
    certificate = diagnose_native_tri_product_output_l0(vertices, faces, route)

    assert route.reason == "boundary_layers_unsupported_by_surface_route"
    assert certificate.status == "reject_native_tri_route_not_product_ready"
    assert certificate.rejection_reason == "boundary_layers_unsupported_by_surface_route"
    assert certificate.source_certificate.accepted is True
    _assert_never_product_success(certificate)
