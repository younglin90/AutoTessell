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
