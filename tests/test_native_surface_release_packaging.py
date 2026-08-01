from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import numpy as np

from core.evaluator.surface_physical_group_provenance import AuthoritativePhysicalGroupMapping
from core.preprocessor.native_quad.strict_pair_transaction_l0 import materialize_strict_quad_pair_transaction_l0
from core.preprocessor.native_quad.strict_quad_fixed_pair_writer_l0 import write_strict_quad_fixed_pair_product_l0
from core.preprocessor.native_quad.tri_quad_fixed_pair_product_l0 import AuthoritativeTriQuadFeatureEdges, AuthoritativeTriQuadPatchIds, materialize_tri_quad_fixed_pair_product_l0
from core.preprocessor.native_quad.tri_quad_fixed_pair_writer_l0 import write_tri_quad_fixed_pair_product_l0

_STRICT_PRODUCT = "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_PRODUCT_L0"
_STRICT_WRITER = "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_WRITER_L0"
_MIX_PRODUCT = "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_PRODUCT_L0"
_MIX_WRITER = "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_WRITER_L0"


def _strict_product():
    points = np.asarray(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)), dtype=np.float64)
    triangles = np.asarray(((0, 1, 2), (0, 2, 3)), dtype=np.int64)
    with patch.dict(os.environ, {_STRICT_PRODUCT: "1"}):
        result = materialize_strict_quad_pair_transaction_l0(
            points, triangles, np.asarray(((0, 1),), dtype=np.int64),
            np.asarray(((0, 1), (1, 2), (2, 3), (0, 3)), dtype=np.int64),
            source_patch_ids=("wall", "wall"),
            source_physical_groups=AuthoritativePhysicalGroupMapping(("wall", "wall"), True),
        )
    assert result.accepted and result.product_result is not None
    return result.product_result


def _mixed_product():
    points = np.asarray(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0), (3.0, 0.0, 0.0), (4.0, 0.0, 0.0), (3.0, 1.0, 0.0), (6.0, 0.0, 0.0), (7.0, 0.0, 0.0), (6.0, 1.0, 0.0)), dtype=np.float64)
    triangles = np.asarray(((0, 1, 2), (0, 2, 3), (4, 5, 6), (7, 8, 9)), dtype=np.int64)
    with patch.dict(os.environ, {_MIX_PRODUCT: "1"}):
        result = materialize_tri_quad_fixed_pair_product_l0(
            points, triangles, np.asarray(((0, 1),), dtype=np.int64),
            AuthoritativeTriQuadFeatureEdges((), True),
            source_patch_ids=AuthoritativeTriQuadPatchIds(("wall", "wall", "outlet", "far"), True),
            source_physical_groups=AuthoritativePhysicalGroupMapping(("inlet", "inlet", "outlet", "far"), True),
        )
    assert result.accepted and result.product is not None
    return result


def test_strict_quad_and_tri_quad_publish_independent_repeatable_artifacts(tmp_path: Path) -> None:
    strict_hashes = []
    mixed_hashes = []
    with patch.dict(os.environ, {_STRICT_WRITER: "1", _MIX_WRITER: "1"}):
        for index in range(3):
            strict = write_strict_quad_fixed_pair_product_l0(_strict_product(), tmp_path / f"strict-{index}")
            mixed = write_tri_quad_fixed_pair_product_l0(_mixed_product(), tmp_path / f"mixed-{index}")
            assert strict.written and strict.readback_verified
            assert mixed.written and mixed.readback_verified
            assert strict.product_claimed is False
            assert mixed.product_claimed is False
            strict_hashes.append((strict.content_sha256, strict.manifest_sha256))
            mixed_hashes.append((mixed.content_sha256, mixed.manifest_sha256))
            assert not (tmp_path / f"strict-{index}" / "triangles.npy").exists()
            assert (tmp_path / f"mixed-{index}" / "quads.npy").exists()
            assert (tmp_path / f"mixed-{index}" / "triangles.npy").exists()
    assert strict_hashes == [strict_hashes[0]] * 3
    assert mixed_hashes == [mixed_hashes[0]] * 3
