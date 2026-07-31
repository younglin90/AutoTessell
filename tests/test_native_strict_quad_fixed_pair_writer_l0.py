"""Focused atomic-artifact tests for fixed-pair strict-quad products."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import numpy as np

import core.preprocessor.native_quad.strict_quad_fixed_pair_writer_l0 as writer
from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_quad.strict_pair_transaction_l0 import (
    materialize_strict_quad_pair_transaction_l0,
)
from core.preprocessor.native_quad.strict_quad_fixed_pair_writer_l0 import (
    strict_quad_fixed_pair_writer_l0_enabled,
    write_strict_quad_fixed_pair_product_l0,
)

_PRODUCT_ENV = "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_PRODUCT_L0"
_WRITER_ENV = "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_WRITER_L0"


def _product_result():
    vertices = np.array(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)),
        dtype=np.float64,
    )
    triangles = np.array(((0, 1, 2), (0, 2, 3)), dtype=np.int64)
    with patch.dict(os.environ, {_PRODUCT_ENV: "1"}):
        result = materialize_strict_quad_pair_transaction_l0(
            vertices,
            triangles,
            np.array(((0, 1),), dtype=np.int64),
            np.array(((0, 1), (1, 2), (2, 3), (0, 3)), dtype=np.int64),
            source_patch_ids=("wall", "wall"),
            source_physical_groups=AuthoritativePhysicalGroupMapping(("wall", "wall"), True),
        )
    assert result.accepted and result.product_result is not None
    return result.product_result


def test_default_off_does_not_emit_strict_quad_artifact(tmp_path: Path) -> None:
    target = tmp_path / "surface"
    with patch.dict(os.environ, {}, clear=True):
        result = write_strict_quad_fixed_pair_product_l0(_product_result(), target)

    assert strict_quad_fixed_pair_writer_l0_enabled() is False
    assert result.written is False
    assert result.status == "reject_strict_quad_fixed_pair_writer_disabled"
    assert result.product_claimed is False
    assert not target.exists()


def test_writer_requires_admitted_product_and_fresh_real_target(tmp_path: Path) -> None:
    product = _product_result()
    existing = tmp_path / "existing"
    existing.mkdir()
    real_target = tmp_path / "real-target"
    real_target.mkdir()
    symlink_target = tmp_path / "symlink-target"
    symlink_target.symlink_to(real_target, target_is_directory=True)
    with patch.dict(os.environ, {_WRITER_ENV: "1"}):
        rejected_product = write_strict_quad_fixed_pair_product_l0(None, tmp_path / "none")
        rejected_target = write_strict_quad_fixed_pair_product_l0(product, existing)
        rejected_symlink = write_strict_quad_fixed_pair_product_l0(product, symlink_target)

    assert rejected_product.status == "reject_strict_quad_fixed_pair_writer_product"
    assert rejected_target.status == "reject_strict_quad_fixed_pair_writer_target"
    assert rejected_symlink.status == "reject_strict_quad_fixed_pair_writer_target"
    assert list(existing.iterdir()) == []
    assert list(real_target.iterdir()) == []


def test_enabled_writer_publishes_only_strict_quad_arrays_and_manifest(tmp_path: Path) -> None:
    product_result = _product_result()
    target = tmp_path / "strict-surface"
    with patch.dict(os.environ, {_WRITER_ENV: "1"}):
        result = write_strict_quad_fixed_pair_product_l0(product_result, target)

    assert result.written is True
    assert result.status == "pass_strict_quad_fixed_pair_writer_unrouted"
    assert result.readback_verified is True
    assert result.product_claimed is False
    assert result.artifact_path == target
    assert set(path.name for path in target.iterdir()) == {
        "vertices.npy",
        "quads.npy",
        "quad_source_pairs.npy",
        "manifest.json",
    }
    assert not (target / "triangles.npy").exists()
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["strict_quad"] == {"triangle_count": 0, "quad_count": 1}
    assert manifest["payloads"] == {
        "quad_patch_ids": ["wall"],
        "quad_physical_groups": ["wall"],
    }
    assert set(manifest["source"]) == {
        "vertices_sha256",
        "triangles_sha256",
        "patch_sha256",
        "physical_group_sha256",
        "feature_sha256",
    }
    product = product_result.product
    assert product is not None
    np.testing.assert_array_equal(
        np.load(target / "vertices.npy", allow_pickle=False), product.vertices
    )
    np.testing.assert_array_equal(np.load(target / "quads.npy", allow_pickle=False), product.quads)
    np.testing.assert_array_equal(
        np.load(target / "quad_source_pairs.npy", allow_pickle=False),
        product.quad_source_pairs,
    )


def test_readback_failure_never_publishes_or_keeps_owned_stage(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "failed-surface"
    monkeypatch.setattr(writer, "_readback", lambda *_args: None)
    with patch.dict(os.environ, {_WRITER_ENV: "1"}):
        result = write_strict_quad_fixed_pair_product_l0(_product_result(), target)

    assert result.status == "reject_strict_quad_fixed_pair_writer_readback"
    assert result.written is False
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []
