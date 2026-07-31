"""Focused offline-dispatch tests for fixed-pair tri+quad artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import NoReturn
from unittest.mock import patch

import numpy as np
import pytest

import core.preprocessor.native_quad.tri_quad_fixed_pair_dispatch_l0 as dispatch
from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_quad.tri_quad_fixed_pair_dispatch_l0 import (
    TriQuadFixedPairDispatchRequest,
    TriQuadFixedPairDispatchResult,
    dispatch_tri_quad_fixed_pair_product_l0,
)
from core.preprocessor.native_quad.tri_quad_fixed_pair_product_l0 import (
    AuthoritativeTriQuadFeatureEdges,
    AuthoritativeTriQuadPatchIds,
)
from core.preprocessor.native_remesh.surface_mode_contract import (
    SurfaceProductClassification,
)

_PRODUCT_ENV = "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_PRODUCT_L0"
_WRITER_ENV = "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_WRITER_L0"


def _request(target: Path, *, patches: object | None = None) -> TriQuadFixedPairDispatchRequest:
    vertices = np.array(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
            (3.0, 0.0, 0.0),
            (4.0, 0.0, 0.0),
            (3.0, 1.0, 0.0),
            (6.0, 0.0, 0.0),
            (7.0, 0.0, 0.0),
            (6.0, 1.0, 0.0),
        ),
        dtype=np.float64,
    )
    return TriQuadFixedPairDispatchRequest(
        source_vertices=vertices,
        source_triangles=np.array(((0, 1, 2), (0, 2, 3), (4, 5, 6), (7, 8, 9)), dtype=np.int64),
        pair_plan=np.array(((0, 1),), dtype=np.int64),
        feature_edges=AuthoritativeTriQuadFeatureEdges((), True),
        source_patch_ids=(
            AuthoritativeTriQuadPatchIds(("wall", "wall", "outlet", "far"), True)
            if patches is None
            else patches
        ),
        source_physical_groups=AuthoritativePhysicalGroupMapping(
            ("inlet", "inlet", "outlet", "far"),
            True,
        ),
        target_directory=target,
    )


def _cube_request(
    target: Path,
) -> tuple[
    TriQuadFixedPairDispatchRequest,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    tuple[int, ...],
    tuple[str, ...],
]:
    vertices = np.array(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 1.0),
            (1.0, 1.0, 1.0),
            (0.0, 1.0, 1.0),
        ),
        dtype=np.float64,
    )
    source_quads = (
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    )
    triangles = np.ascontiguousarray(
        [
            triangle
            for quad in source_quads
            for triangle in ((quad[0], quad[1], quad[2]), (quad[0], quad[2], quad[3]))
        ],
        dtype=np.int64,
    )
    pair_plan = np.ascontiguousarray(((0, 1),), dtype=np.int64)
    feature_edges = tuple(
        sorted(
            {
                tuple(sorted((quad[index], quad[(index + 1) % 4])))
                for quad in source_quads
                for index in range(4)
            }
        )
    )
    patches = tuple(index for index in range(6) for _ in range(2))
    groups = tuple(f"face-{index}" for index in range(6) for _ in range(2))
    return (
        TriQuadFixedPairDispatchRequest(
            source_vertices=vertices,
            source_triangles=triangles,
            pair_plan=pair_plan,
            feature_edges=AuthoritativeTriQuadFeatureEdges(feature_edges, True),
            source_patch_ids=AuthoritativeTriQuadPatchIds(patches, True),
            source_physical_groups=AuthoritativePhysicalGroupMapping(groups, True),
            target_directory=target,
        ),
        vertices.copy(),
        triangles.copy(),
        pair_plan,
        patches,
        groups,
    )


def _assert_never_claimed(result: TriQuadFixedPairDispatchResult) -> None:
    assert result.route_selected is False
    assert result.ui_claimed is False
    assert result.product_claimed is False


def test_both_gates_off_rejects_without_writer_or_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _writer(*_args: object) -> NoReturn:
        nonlocal called
        called = True
        raise AssertionError("writer must stay disconnected")

    monkeypatch.setattr(dispatch, "write_tri_quad_fixed_pair_product_l0", _writer)
    target = tmp_path / "surface"
    with patch.dict(os.environ, {}, clear=True):
        result = dispatch_tri_quad_fixed_pair_product_l0(_request(target))

    assert result.accepted is False
    assert result.status == "reject_tri_quad_fixed_pair_product_disabled"
    assert result.product_result is not None
    assert result.writer_result is None
    assert result.artifact_path is None
    assert result.artifact_written is False
    assert called is False
    assert not target.exists()
    _assert_never_claimed(result)


def test_product_only_gate_admits_unwritten_product_without_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _writer(*_args: object) -> NoReturn:
        nonlocal called
        called = True
        raise AssertionError("writer gate required")

    monkeypatch.setattr(dispatch, "write_tri_quad_fixed_pair_product_l0", _writer)
    target = tmp_path / "surface"
    with patch.dict(os.environ, {_PRODUCT_ENV: "1"}, clear=True):
        result = dispatch_tri_quad_fixed_pair_product_l0(_request(target))

    assert result.accepted is True
    assert result.status == "pass_tri_quad_fixed_pair_dispatch_unwritten"
    assert result.product_result is not None and result.product_result.accepted
    assert result.writer_result is None
    assert result.artifact_path is None
    assert result.artifact_written is False
    assert called is False
    assert not target.exists()
    _assert_never_claimed(result)


def test_both_gates_publish_separate_arrays_and_manifest(tmp_path: Path) -> None:
    target = tmp_path / "surface"
    with patch.dict(os.environ, {_PRODUCT_ENV: "1", _WRITER_ENV: "1"}, clear=True):
        result = dispatch_tri_quad_fixed_pair_product_l0(_request(target))

    assert result.accepted is True
    assert result.status == "pass_tri_quad_fixed_pair_dispatch_unrouted"
    assert result.writer_result is not None and result.writer_result.written
    assert result.artifact_path == target
    assert result.artifact_written is True
    assert set(path.name for path in target.iterdir()) == {
        "vertices.npy",
        "triangles.npy",
        "quads.npy",
        "triangle_source_indices.npy",
        "quad_source_pairs.npy",
        "manifest.json",
    }
    assert np.load(target / "triangles.npy", allow_pickle=False).shape == (2, 3)
    assert np.load(target / "quads.npy", allow_pickle=False).shape == (1, 4)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["product_contract"] == "tri_quad_fixed_pair_product_l0"
    _assert_never_claimed(result)


def test_enabled_cube_partial_transaction_dispatches_authoritative_mixed_artifact(
    tmp_path: Path,
) -> None:
    target = tmp_path / "cube-mixed-surface"
    request, source_vertices, source_triangles, pair_plan, patches, groups = _cube_request(target)
    assert request.source_patch_ids == AuthoritativeTriQuadPatchIds(patches, True)
    assert request.source_physical_groups == AuthoritativePhysicalGroupMapping(groups, True)
    with patch.dict(os.environ, {_PRODUCT_ENV: "1", _WRITER_ENV: "1"}, clear=True):
        result = dispatch_tri_quad_fixed_pair_product_l0(request)

    assert result.accepted and result.artifact_written
    assert result.status == "pass_tri_quad_fixed_pair_dispatch_unrouted"
    assert result.artifact_path == target
    product_result = result.product_result
    assert (
        product_result is not None
        and product_result.accepted
        and product_result.product is not None
    )
    assert product_result.transaction_applied
    assert product_result.independent_product_ready is False
    assert product_result.product_claimed is False
    assert product_result.product_certificate is not None
    assert (
        product_result.product_certificate.classification
        is SurfaceProductClassification.CANDIDATE_MIXED
    )
    preflight = product_result.preflight
    assert preflight.accepted and preflight.rejection_reason is None
    assert preflight.source_oriented_manifold and preflight.output_oriented_manifold
    assert preflight.boundary_equal and preflight.feature_edges_preserved
    assert preflight.component_count_equal and preflight.euler_characteristic_equal
    assert preflight.provenance_complete
    assert preflight.patch_payload_preserved and preflight.physical_group_payload_preserved
    product = product_result.product
    assert product.contract == "tri_quad_fixed_pair_product_l0"
    assert product.triangles.shape == (10, 3) and product.quads.shape == (1, 4)
    np.testing.assert_array_equal(product.triangle_source_indices, np.arange(2, 12, dtype=np.int64))
    np.testing.assert_array_equal(product.quad_source_pairs, pair_plan)
    partition = np.concatenate(
        (product.triangle_source_indices, product.quad_source_pairs.reshape(-1))
    )
    np.testing.assert_array_equal(np.sort(partition), np.arange(12, dtype=np.int64))
    assert product.triangle_patch_ids == patches[2:]
    assert product.quad_patch_ids == (patches[0],)
    assert product.triangle_physical_groups == groups[2:]
    assert product.quad_physical_groups == (groups[0],)
    assert all(
        not values.flags.writeable
        for values in (
            product.vertices,
            product.triangles,
            product.quads,
            product.triangle_source_indices,
            product.quad_source_pairs,
        )
    )
    np.testing.assert_array_equal(request.source_vertices, source_vertices)
    np.testing.assert_array_equal(request.source_triangles, source_triangles)
    assert result.writer_result is not None and result.writer_result.readback_verified
    assert result.writer_result.content_sha256 is not None
    assert result.writer_result.manifest_sha256 is not None
    assert set(path.name for path in target.iterdir()) == {
        "vertices.npy",
        "triangles.npy",
        "quads.npy",
        "triangle_source_indices.npy",
        "quad_source_pairs.npy",
        "manifest.json",
    }
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["product_contract"] == product.contract
    assert manifest["source"] == {
        "vertices_sha256": product.source_vertices_hash,
        "triangles_sha256": product.source_triangles_hash,
        "patch_sha256": product.source_patch_hash,
        "physical_group_sha256": product.source_physical_group_hash,
        "feature_sha256": product.feature_hash,
    }
    assert manifest["payloads"] == {
        "triangle_patch_ids": list(patches[2:]),
        "quad_patch_ids": [patches[0]],
        "triangle_physical_groups": list(groups[2:]),
        "quad_physical_groups": [groups[0]],
    }
    assert manifest["provenance"] == {
        "triangle_source_indices_file": "triangle_source_indices.npy",
        "quad_source_pairs_file": "quad_source_pairs.npy",
    }
    assert manifest["content_sha256"] == result.writer_result.content_sha256
    assert set(manifest["arrays"]) == {
        "vertices",
        "triangles",
        "quads",
        "triangle_source_indices",
        "quad_source_pairs",
    }
    np.testing.assert_array_equal(
        np.load(target / "vertices.npy", allow_pickle=False), source_vertices
    )
    np.testing.assert_array_equal(
        np.load(target / "triangles.npy", allow_pickle=False), product.triangles
    )
    np.testing.assert_array_equal(np.load(target / "quads.npy", allow_pickle=False), product.quads)
    np.testing.assert_array_equal(
        np.load(target / "triangle_source_indices.npy", allow_pickle=False),
        product.triangle_source_indices,
    )
    np.testing.assert_array_equal(
        np.load(target / "quad_source_pairs.npy", allow_pickle=False), product.quad_source_pairs
    )
    _assert_never_claimed(result)


def test_non_authoritative_payload_rejects_before_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _writer(*_args: object) -> NoReturn:
        nonlocal called
        called = True
        raise AssertionError("unauthoritative payload must reject before writer")

    monkeypatch.setattr(dispatch, "write_tri_quad_fixed_pair_product_l0", _writer)
    target = tmp_path / "surface"
    with patch.dict(os.environ, {_PRODUCT_ENV: "1", _WRITER_ENV: "1"}, clear=True):
        result = dispatch_tri_quad_fixed_pair_product_l0(
            _request(target, patches=("wall", "wall", "outlet", "far")),
        )

    assert result.accepted is False
    assert result.status == "reject_tri_quad_fixed_pair_preflight"
    assert result.rejection_reason == "source_patch_payload_required"
    assert result.writer_result is None
    assert called is False
    assert not target.exists()
    _assert_never_claimed(result)


def test_preexisting_target_rejects_without_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "surface"
    target.mkdir()
    sentinel = target / "keep"
    sentinel.write_text("keep", encoding="utf-8")
    with patch.dict(os.environ, {_PRODUCT_ENV: "1", _WRITER_ENV: "1"}, clear=True):
        result = dispatch_tri_quad_fixed_pair_product_l0(_request(target))

    assert result.accepted is False
    assert result.status == "reject_tri_quad_fixed_pair_writer_target"
    assert result.rejection_reason == "fresh_real_target_directory_required"
    assert result.writer_result is not None and result.writer_result.written is False
    assert result.artifact_path is None
    assert result.artifact_written is False
    assert sentinel.read_text(encoding="utf-8") == "keep"
    _assert_never_claimed(result)
