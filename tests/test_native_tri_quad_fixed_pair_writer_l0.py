"""Focused atomic-artifact tests for the fixed-pair tri+quad writer."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import numpy as np

import core.preprocessor.native_quad.tri_quad_fixed_pair_writer_l0 as writer
from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_quad.tri_quad_fixed_pair_product_l0 import (
    AuthoritativeTriQuadFeatureEdges,
    AuthoritativeTriQuadPatchIds,
    materialize_tri_quad_fixed_pair_product_l0,
)
from core.preprocessor.native_quad.tri_quad_fixed_pair_writer_l0 import (
    tri_quad_fixed_pair_writer_l0_enabled,
    write_tri_quad_fixed_pair_product_l0,
)

_PRODUCT_ENV = "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_PRODUCT_L0"
_WRITER_ENV = "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_WRITER_L0"


def _product_result():
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
    with patch.dict(os.environ, {_PRODUCT_ENV: "1"}):
        result = materialize_tri_quad_fixed_pair_product_l0(
            vertices,
            triangles,
            np.array(((0, 1),), dtype=np.int64),
            AuthoritativeTriQuadFeatureEdges((), True),
            source_patch_ids=AuthoritativeTriQuadPatchIds(
                ("wall", "wall", "outlet", "far"), True,
            ),
            source_physical_groups=AuthoritativePhysicalGroupMapping(
                ("inlet", "inlet", "outlet", "far"), True,
            ),
        )
    assert result.accepted and result.product is not None
    return result


def test_default_off_does_not_emit_an_artifact(tmp_path: Path) -> None:
    with patch.dict(os.environ, {}, clear=True):
        result = write_tri_quad_fixed_pair_product_l0(_product_result(), tmp_path / "surface")

    assert tri_quad_fixed_pair_writer_l0_enabled() is False
    assert result.written is False
    assert result.status == "reject_tri_quad_fixed_pair_writer_disabled"
    assert result.product_claimed is False
    assert not (tmp_path / "surface").exists()


def test_writer_requires_accepted_product_and_a_fresh_real_target(tmp_path: Path) -> None:
    product = _product_result()
    existing = tmp_path / "existing"
    existing.mkdir()
    real_target = tmp_path / "real-target"
    real_target.mkdir()
    symlink_target = tmp_path / "symlink-target"
    symlink_target.symlink_to(real_target, target_is_directory=True)
    with patch.dict(os.environ, {_WRITER_ENV: "1"}):
        rejected_product = write_tri_quad_fixed_pair_product_l0(None, tmp_path / "none")
        rejected_target = write_tri_quad_fixed_pair_product_l0(product, existing)
        rejected_symlink = write_tri_quad_fixed_pair_product_l0(product, symlink_target)

    assert rejected_product.status == "reject_tri_quad_fixed_pair_writer_product"
    assert rejected_target.status == "reject_tri_quad_fixed_pair_writer_target"
    assert rejected_symlink.status == "reject_tri_quad_fixed_pair_writer_target"
    assert existing.is_dir()
    assert list(existing.iterdir()) == []
    assert real_target.is_dir()
    assert list(real_target.iterdir()) == []


def test_enabled_writer_publishes_separate_arrays_canonical_manifest_and_readback(tmp_path: Path) -> None:
    product_result = _product_result()
    target = tmp_path / "mixed-surface"
    with patch.dict(os.environ, {_WRITER_ENV: "1"}):
        result = write_tri_quad_fixed_pair_product_l0(product_result, target)

    assert result.written is True
    assert result.status == "pass_tri_quad_fixed_pair_writer_unrouted"
    assert result.readback_verified is True
    assert result.product_claimed is False
    assert result.artifact_path == target
    assert result.content_sha256 is not None
    assert result.manifest_sha256 is not None
    assert set(path.name for path in target.iterdir()) == {
        "vertices.npy", "triangles.npy", "quads.npy",
        "triangle_source_indices.npy", "quad_source_pairs.npy", "manifest.json",
    }
    raw_manifest = (target / "manifest.json").read_bytes()
    manifest = json.loads(raw_manifest)
    assert raw_manifest == json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    assert sha256(raw_manifest).hexdigest() == result.manifest_sha256
    assert manifest["content_sha256"] == result.content_sha256
    product = product_result.product
    assert product is not None
    np.testing.assert_array_equal(np.load(target / "vertices.npy", allow_pickle=False), product.vertices)
    np.testing.assert_array_equal(np.load(target / "triangles.npy", allow_pickle=False), product.triangles)
    np.testing.assert_array_equal(np.load(target / "quads.npy", allow_pickle=False), product.quads)
    np.testing.assert_array_equal(
        np.load(target / "triangle_source_indices.npy", allow_pickle=False),
        product.triangle_source_indices,
    )
    np.testing.assert_array_equal(
        np.load(target / "quad_source_pairs.npy", allow_pickle=False),
        product.quad_source_pairs,
    )
    assert manifest["payloads"]["triangle_patch_ids"] == list(product.triangle_patch_ids)
    assert manifest["payloads"]["quad_physical_groups"] == list(product.quad_physical_groups)


def test_readback_or_write_failure_never_publishes_or_keeps_stage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    product = _product_result()
    readback_target = tmp_path / "readback-failure"
    write_target = tmp_path / "write-failure"
    monkeypatch.setattr(writer, "_readback", lambda *_args: None)
    with patch.dict(os.environ, {_WRITER_ENV: "1"}):
        readback = write_tri_quad_fixed_pair_product_l0(product, readback_target)
    assert readback.status == "reject_tri_quad_fixed_pair_writer_readback"
    assert not readback_target.exists()
    assert list(tmp_path.iterdir()) == []

    monkeypatch.undo()
    monkeypatch.setattr(writer, "_write_array", lambda *_args: (_ for _ in ()).throw(OSError("injected")))
    with patch.dict(os.environ, {_WRITER_ENV: "1"}):
        write_failure = write_tri_quad_fixed_pair_product_l0(product, write_target)
    assert write_failure.status == "reject_tri_quad_fixed_pair_writer_io"
    assert not write_target.exists()
    assert list(tmp_path.iterdir()) == []
