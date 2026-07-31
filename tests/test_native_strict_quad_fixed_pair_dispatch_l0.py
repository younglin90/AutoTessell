"""Focused offline-dispatch tests for fixed-pair strict-quad artifacts."""

from __future__ import annotations

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
