"""Focused offline-dispatch tests for fixed-pair strict-quad artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import NoReturn
from unittest.mock import patch

import numpy as np
import pytest

import core.preprocessor.native_quad.strict_quad_fixed_pair_dispatch_l0 as dispatch
from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_quad.strict_quad_fixed_pair_dispatch_l0 import (
    AuthoritativeStrictQuadPatchIds,
    StrictQuadFixedPairDispatchRequest,
    StrictQuadFixedPairDispatchResult,
    dispatch_strict_quad_fixed_pair_product_l0,
)

_PRODUCT_ENV = "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_PRODUCT_L0"
_WRITER_ENV = "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_WRITER_L0"


def _request(
    target: Path,
    *,
    patches: object | None = None,
    groups: object | None = None,
) -> StrictQuadFixedPairDispatchRequest:
    return StrictQuadFixedPairDispatchRequest(
        source_vertices=np.array(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)),
            dtype=np.float64,
        ),
        source_triangles=np.array(((0, 1, 2), (0, 2, 3)), dtype=np.int64),
        pair_plan=np.array(((0, 1),), dtype=np.int64),
        feature_edges=np.array(((0, 1), (1, 2), (2, 3), (0, 3)), dtype=np.int64),
        source_patch_ids=(
            AuthoritativeStrictQuadPatchIds(("wall", "wall"), True) if patches is None else patches
        ),
        source_physical_groups=(
            AuthoritativePhysicalGroupMapping(("wall", "wall"), True) if groups is None else groups
        ),
        target_directory=target,
    )


def _cube_request(
    target: Path,
) -> tuple[
    StrictQuadFixedPairDispatchRequest,
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
    pair_plan = np.ascontiguousarray(
        [(2 * index, 2 * index + 1) for index in range(6)], dtype=np.int64
    )
    features = np.ascontiguousarray(
        sorted(
            {
                tuple(sorted((quad[index], quad[(index + 1) % 4])))
                for quad in source_quads
                for index in range(4)
            }
        ),
        dtype=np.int64,
    )
    patches = tuple(index for index in range(6) for _ in range(2))
    groups = tuple(f"face-{index}" for index in range(6) for _ in range(2))
    return (
        StrictQuadFixedPairDispatchRequest(
            source_vertices=vertices,
            source_triangles=triangles,
            pair_plan=pair_plan,
            feature_edges=features,
            source_patch_ids=AuthoritativeStrictQuadPatchIds(patches, True),
            source_physical_groups=AuthoritativePhysicalGroupMapping(groups, True),
            target_directory=target,
        ),
        vertices.copy(),
        triangles.copy(),
        pair_plan,
        patches,
        groups,
    )


def _assert_never_claimed(result: StrictQuadFixedPairDispatchResult) -> None:
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

    monkeypatch.setattr(dispatch, "write_strict_quad_fixed_pair_product_l0", _writer)
    target = tmp_path / "surface"
    with patch.dict(os.environ, {}, clear=True):
        result = dispatch_strict_quad_fixed_pair_product_l0(_request(target))

    assert result.accepted is False
    assert result.status == "reject_strict_quad_fixed_pair_product_disabled"
    assert result.transaction_result is not None
    assert result.writer_result is None
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

    monkeypatch.setattr(dispatch, "write_strict_quad_fixed_pair_product_l0", _writer)
    target = tmp_path / "surface"
    with patch.dict(os.environ, {_PRODUCT_ENV: "1"}, clear=True):
        result = dispatch_strict_quad_fixed_pair_product_l0(_request(target))

    assert result.accepted is True
    assert result.status == "pass_strict_quad_fixed_pair_dispatch_unwritten"
    assert result.transaction_result is not None and result.transaction_result.accepted
    assert result.writer_result is None
    assert result.artifact_written is False
    assert called is False
    assert not target.exists()
    _assert_never_claimed(result)


def test_both_gates_publish_only_strict_quad_artifact(tmp_path: Path) -> None:
    target = tmp_path / "surface"
    with patch.dict(os.environ, {_PRODUCT_ENV: "1", _WRITER_ENV: "1"}, clear=True):
        result = dispatch_strict_quad_fixed_pair_product_l0(_request(target))

    assert result.accepted is True
    assert result.status == "pass_strict_quad_fixed_pair_dispatch_unrouted"
    assert result.writer_result is not None and result.writer_result.written
    assert result.artifact_path == target
    assert result.artifact_written is True
    assert set(path.name for path in target.iterdir()) == {
        "vertices.npy",
        "quads.npy",
        "quad_source_pairs.npy",
        "manifest.json",
    }
    assert not (target / "triangles.npy").exists()
    _assert_never_claimed(result)


def test_enabled_cube_transaction_dispatches_authoritative_strict_quad_artifact(
    tmp_path: Path,
) -> None:
    target = tmp_path / "cube-strict-surface"
    request, source_vertices, source_triangles, pair_plan, patches, groups = _cube_request(target)
    assert request.source_patch_ids == AuthoritativeStrictQuadPatchIds(patches, True)
    assert request.source_physical_groups == AuthoritativePhysicalGroupMapping(groups, True)
    with patch.dict(os.environ, {_PRODUCT_ENV: "1", _WRITER_ENV: "1"}, clear=True):
        result = dispatch_strict_quad_fixed_pair_product_l0(request)

    assert result.accepted and result.artifact_written
    assert result.status == "pass_strict_quad_fixed_pair_dispatch_unrouted"
    assert result.artifact_path == target
    transaction = result.transaction_result
    assert transaction is not None and transaction.accepted and transaction.transaction_applied
    assert transaction.independent_product_ready is False
    product_result = transaction.product_result
    assert (
        product_result is not None
        and product_result.accepted
        and product_result.product is not None
    )
    assert product_result.preflight.accepted and product_result.preflight.rejection_reasons == ()
    assert product_result.preflight.patch_payload_preserved
    assert product_result.preflight.physical_group_payload_preserved
    assert dict(product_result.preflight.structural_facts) == {
        "valid": True,
        "coordinates_finite": True,
        "vertices_exact": True,
        "source_triangles_non_degenerate": True,
        "candidate_triangles_empty": True,
        "quads_degree_four": True,
        "provenance_complete": True,
        "pair_quads_exact": True,
        "pairs_coplanar": True,
        "source_manifold": True,
        "quad_manifold": True,
        "boundary_equal": True,
        "features_preserved": True,
        "source_component_count": 1,
        "quad_component_count": 1,
        "source_euler_characteristic": 2,
        "quad_euler_characteristic": 2,
    }
    product = product_result.product
    assert product.triangles.shape == (0, 3) and product.quads.shape == (6, 4)
    np.testing.assert_array_equal(product.quad_source_pairs, pair_plan)
    assert product.quad_patch_ids == tuple(range(6))
    assert product.quad_physical_groups == tuple(f"face-{index}" for index in range(6))
    assert all(
        not values.flags.writeable
        for values in (
            product.vertices,
            product.triangles,
            product.quads,
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
        "quads.npy",
        "quad_source_pairs.npy",
        "manifest.json",
    }
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["strict_quad"] == {"triangle_count": 0, "quad_count": 6}
    assert manifest["source"] == {
        "vertices_sha256": product.source_vertices_hash,
        "triangles_sha256": product.source_triangles_hash,
        "patch_sha256": product.source_patch_hash,
        "physical_group_sha256": product.source_physical_group_hash,
        "feature_sha256": product.feature_hash,
    }
    assert manifest["payloads"] == {
        "quad_patch_ids": list(range(6)),
        "quad_physical_groups": [f"face-{index}" for index in range(6)],
    }
    assert manifest["provenance"] == {
        "quad_source_pairs_file": "quad_source_pairs.npy",
        "quad_source_pairs_sha256": product.pair_provenance_hash,
        "quads_sha256": product.quads_hash,
    }
    assert manifest["content_sha256"] == result.writer_result.content_sha256
    assert set(manifest["arrays"]) == {"vertices", "quads", "quad_source_pairs"}
    np.testing.assert_array_equal(
        np.load(target / "vertices.npy", allow_pickle=False), source_vertices
    )
    np.testing.assert_array_equal(np.load(target / "quads.npy", allow_pickle=False), product.quads)
    np.testing.assert_array_equal(
        np.load(target / "quad_source_pairs.npy", allow_pickle=False), pair_plan
    )
    _assert_never_claimed(result)


@pytest.mark.parametrize(
    "patches,groups",
    (
        (("wall", "wall"), None),
        (AuthoritativeStrictQuadPatchIds(("wall", "wall"), False), None),
        (None, AuthoritativePhysicalGroupMapping(("wall", "wall"), False)),
    ),
)
def test_non_authoritative_patch_or_physical_authority_rejects_before_writer(
    tmp_path: Path,
    patches: object,
    groups: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _writer(*_args: object) -> NoReturn:
        nonlocal called
        called = True
        raise AssertionError("authority rejection must precede writer")

    monkeypatch.setattr(dispatch, "write_strict_quad_fixed_pair_product_l0", _writer)
    target = tmp_path / "surface"
    with patch.dict(os.environ, {_PRODUCT_ENV: "1", _WRITER_ENV: "1"}, clear=True):
        result = dispatch_strict_quad_fixed_pair_product_l0(
            _request(target, patches=patches, groups=groups),
        )

    assert result.accepted is False
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
        result = dispatch_strict_quad_fixed_pair_product_l0(_request(target))

    assert result.accepted is False
    assert result.status == "reject_strict_quad_fixed_pair_writer_target"
    assert result.writer_result is not None and result.writer_result.written is False
    assert sentinel.read_text(encoding="utf-8") == "keep"
    _assert_never_claimed(result)
