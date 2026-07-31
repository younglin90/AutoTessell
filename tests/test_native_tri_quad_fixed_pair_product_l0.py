"""Focused contract tests for the independent fixed-pair tri+quad product."""

from __future__ import annotations

import os
from unittest.mock import patch

import numpy as np
import pytest

from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_quad.tri_quad_fixed_pair_product_l0 import (
    AuthoritativeTriQuadFeatureEdges,
    materialize_tri_quad_fixed_pair_product_l0,
    tri_quad_fixed_pair_product_l0_enabled,
)
from core.preprocessor.native_remesh.surface_mode_contract import (
    SurfaceProductClassification,
)

_ENV = "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_PRODUCT_L0"


def _fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray, object, object, object]:
    vertices = np.array(
        (
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0),
            (3.0, 0.0, 0.0), (4.0, 0.0, 0.0), (3.0, 1.0, 0.0),
            (6.0, 0.0, 0.0), (7.0, 0.0, 0.0), (6.0, 1.0, 0.0),
        ),
        dtype=np.float64,
    )
    triangles = np.array(
        ((0, 1, 2), (0, 2, 3), (4, 5, 6), (7, 8, 9)), dtype=np.int64,
    )
    plan = np.array(((0, 1),), dtype=np.int64)
    features = AuthoritativeTriQuadFeatureEdges((), True)
    patches = ("wall", "wall", "outlet", "far")
    groups = AuthoritativePhysicalGroupMapping(("inlet", "inlet", "outlet", "far"), True)
    return vertices, triangles, plan, features, patches, groups


def _materialize(*, plan: object | None = None, features: object | None = None, patches: object | None = None, groups: object | None = None):
    vertices, triangles, fixture_plan, fixture_features, fixture_patches, fixture_groups = _fixture()
    return materialize_tri_quad_fixed_pair_product_l0(
        vertices,
        triangles,
        fixture_plan if plan is None else plan,
        fixture_features if features is None else features,
        source_patch_ids=fixture_patches if patches is None else patches,
        source_physical_groups=fixture_groups if groups is None else groups,
    )


def test_default_off_rejects_valid_genuine_mix_without_product_or_writer() -> None:
    with patch.dict(os.environ, {}, clear=True):
        result = _materialize()

    assert tri_quad_fixed_pair_product_l0_enabled() is False
    assert result.preflight.accepted is True
    assert result.product_certificate is not None and result.product_certificate.accepted
    assert result.accepted is False
    assert result.status == "reject_tri_quad_fixed_pair_product_disabled"
    assert result.transaction_applied is False
    assert result.independent_product_ready is False
    assert result.product_claimed is False
    assert result.product is None


def test_enabled_fixed_pair_transaction_materializes_separate_genuine_mix_unwritten() -> None:
    vertices, triangles, *_ = _fixture()
    before = (vertices.copy(), triangles.copy())
    with patch.dict(os.environ, {_ENV: "1"}):
        result = _materialize()

    assert result.accepted is True
    assert result.status == "pass_tri_quad_fixed_pair_product_unwritten"
    assert result.transaction_applied is True
    assert result.independent_product_ready is False
    assert result.product_claimed is False
    assert result.product_certificate is not None
    assert result.product_certificate.classification is SurfaceProductClassification.CANDIDATE_MIXED
    product = result.product
    assert product is not None
    np.testing.assert_array_equal(product.triangles, np.array(((4, 5, 6), (7, 8, 9)), dtype=np.int64))
    np.testing.assert_array_equal(product.quads, np.array(((1, 2, 3, 0),), dtype=np.int64))
    np.testing.assert_array_equal(product.triangle_source_indices, np.array((2, 3), dtype=np.int64))
    np.testing.assert_array_equal(product.quad_source_pairs, np.array(((0, 1),), dtype=np.int64))
    assert product.triangle_patch_ids == ("outlet", "far")
    assert product.quad_patch_ids == ("wall",)
    assert product.triangle_physical_groups == ("outlet", "far")
    assert product.quad_physical_groups == ("inlet",)
    assert all(not array.flags.writeable for array in (
        product.vertices, product.triangles, product.quads,
        product.triangle_source_indices, product.quad_source_pairs,
    ))
    np.testing.assert_array_equal(vertices, before[0])
    np.testing.assert_array_equal(triangles, before[1])


@pytest.mark.parametrize(
    ("plan", "reason"),
    (
        (np.empty((0, 2), dtype=np.int64), "partial_pair_plan_required"),
        (np.array(((0, 1), (2, 3)), dtype=np.int64), "partial_pair_plan_required"),
        (np.array(((0, 0),), dtype=np.int64), "partial_pair_plan_required"),
    ),
)
def test_noop_full_or_malformed_pair_plan_rejects(plan: np.ndarray, reason: str) -> None:
    with patch.dict(os.environ, {_ENV: "1"}):
        result = _materialize(plan=plan)

    assert result.accepted is False
    assert result.preflight.rejection_reason == reason
    assert result.product is None


@pytest.mark.parametrize(
    ("patches", "groups", "reason"),
    (
        (("wall", "other", "outlet", "far"), None, "quad_pair_patch_payload_ambiguous"),
        (None, AuthoritativePhysicalGroupMapping(("inlet", "other", "outlet", "far"), True), "quad_pair_physical_group_payload_ambiguous"),
    ),
)
def test_cross_pair_patch_or_physical_group_rejects(patches: object, groups: object, reason: str) -> None:
    with patch.dict(os.environ, {_ENV: "1"}):
        result = _materialize(patches=patches, groups=groups)

    assert result.accepted is False
    assert result.preflight.rejection_reason == reason
    assert result.product is None


def test_feature_removing_pair_and_non_authoritative_groups_reject() -> None:
    with patch.dict(os.environ, {_ENV: "1"}):
        feature = _materialize(features=AuthoritativeTriQuadFeatureEdges(((0, 2),), True))
        groups = _materialize(groups=AuthoritativePhysicalGroupMapping(("inlet", "inlet", "outlet", "far"), False))

    assert feature.accepted is False
    assert feature.preflight.rejection_reason == "mixed_source_contract_rejected"
    assert groups.accepted is False
    assert groups.preflight.rejection_reason == "authoritative_source_physical_groups_required"


def test_nonmanifold_source_rejects_before_any_mixed_product() -> None:
    vertices, triangles, plan, features, patches, groups = _fixture()
    triangles = triangles.copy()
    triangles[3] = triangles[2]
    with patch.dict(os.environ, {_ENV: "1"}):
        result = materialize_tri_quad_fixed_pair_product_l0(
            vertices,
            triangles,
            plan,
            features,
            source_patch_ids=patches,
            source_physical_groups=groups,
        )

    assert result.accepted is False
    assert result.preflight.rejection_reason == "source_topology_invalid"
    assert result.product is None
