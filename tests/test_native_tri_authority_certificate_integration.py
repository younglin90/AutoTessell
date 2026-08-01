"""Actual native-Tri route plus measured authority evidence integration."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.evaluator.actual_source_output_certificate import (
    certify_exact_surface_output,
)
from core.preprocessor.native_tri.product_output_certificate_l0 import (
    diagnose_native_tri_product_output_l0,
)
from core.preprocessor.native_tri.route import run_native_tri_l2_route


def test_actual_tri_route_has_measured_source_authority_but_no_product_claim(
    tmp_path: Path,
) -> None:
    vertices = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        dtype=np.float64,
    )
    faces = np.asarray(((0, 1, 2),), dtype=np.int64)
    source = tmp_path / "source.stl"
    source.write_bytes(b"authoritative-stl-snapshot")

    route = run_native_tri_l2_route(vertices, faces, target_faces=None, boundary_layers=0)
    authority = certify_exact_surface_output(
        source,
        vertices,
        faces,
        route.vertices,
        route.faces,
        source_feature_ids=("surface",),
        source_patch_ids=("surface",),
        source_physical_groups=("wall",),
        output_feature_ids=("surface",),
        output_patch_ids=("surface",),
        output_physical_groups=("wall",),
        output_to_source_faces=(0,),
    )
    product = diagnose_native_tri_product_output_l0(vertices, faces, route)

    assert authority.status == "measured_authoritative_source_output"
    assert authority.authoritative is True
    assert product.accepted is False
    assert product.product_claimed is False
    assert product.mesher_success_allowed is False
    assert product.rejection_reason == "source_contract_unavailable"
