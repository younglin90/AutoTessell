"""Complex stepped-prism corpus for the independent Quad products."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import numpy as np

from core.evaluator.surface_physical_group_provenance import AuthoritativePhysicalGroupMapping
from core.preprocessor.native_quad.strict_pair_transaction_l0 import materialize_strict_quad_pair_transaction_l0
from core.preprocessor.native_quad.strict_quad_fixed_pair_writer_l0 import write_strict_quad_fixed_pair_product_l0
from core.preprocessor.native_quad.tri_quad_fixed_pair_product_l0 import (
    AuthoritativeTriQuadFeatureEdges,
    AuthoritativeTriQuadPatchIds,
    materialize_tri_quad_fixed_pair_product_l0,
)
from core.preprocessor.native_quad.tri_quad_fixed_pair_writer_l0 import write_tri_quad_fixed_pair_product_l0


def _stepped_prism() -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[str, ...], np.ndarray]:
    polygon = np.asarray(((0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0), (1.0, 2.0), (0.0, 2.0)))
    vertices = np.asarray([(x, y, z) for z in (0.0, 1.0) for x, y in polygon], dtype=np.float64)
    triangles: list[tuple[int, int, int]] = []
    pair_plan: list[tuple[int, int]] = []
    patch_ids: list[str] = []
    def add_pair(first: tuple[int, int, int], second: tuple[int, int, int], patch: str) -> None:
        start = len(triangles)
        triangles.extend((first, second))
        pair_plan.append((start, start + 1))
        patch_ids.extend((patch, patch))
    add_pair((0, 5, 4), (0, 4, 3), "bottom")
    add_pair((0, 3, 2), (0, 2, 1), "bottom")
    add_pair((6, 7, 8), (6, 8, 9), "top")
    add_pair((6, 9, 10), (6, 10, 11), "top")
    for a, b, patch in (
        (0, 1, "side0"), (1, 2, "side1"), (2, 3, "side2"),
        (3, 4, "side3"), (4, 5, "side4"), (5, 0, "side5"),
    ):
        add_pair((a, b, b + 6), (a, b + 6, a + 6), patch)
    features = sorted(
        {tuple(sorted(edge)) for edge in (
            (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (0, 5),
            (6, 7), (7, 8), (8, 9), (9, 10), (10, 11), (6, 11),
        )}
        | {tuple(sorted((index, index + 6))) for index in range(6)}
    )
    return (
        vertices,
        np.asarray(triangles, dtype=np.int64),
        np.asarray(pair_plan, dtype=np.int64),
        tuple(patch_ids),
        np.asarray(features, dtype=np.int64),
    )


def _products():
    vertices, triangles, pair_plan, patches, features = _stepped_prism()
    groups = AuthoritativePhysicalGroupMapping(tuple(f"group-{patch}" for patch in patches), True)
    with patch.dict(os.environ, {
        "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_PRODUCT_L0": "1",
        "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_PRODUCT_L0": "1",
    }):
        strict = materialize_strict_quad_pair_transaction_l0(
            vertices, triangles, pair_plan, features,
            source_patch_ids=patches, source_physical_groups=groups,
        )
        mixed = materialize_tri_quad_fixed_pair_product_l0(
            vertices, triangles, pair_plan[:3],
            AuthoritativeTriQuadFeatureEdges(tuple(map(tuple, features.tolist())), True),
            source_patch_ids=AuthoritativeTriQuadPatchIds(patches, True),
            source_physical_groups=AuthoritativePhysicalGroupMapping(
                tuple(f"group-{patch}" for patch in patches), True,
            ),
        )
    assert strict.accepted and strict.product_result is not None
    assert mixed.accepted and mixed.product is not None
    return strict.product_result, mixed


def test_complex_stepped_source_has_independent_repeatable_quad_artifacts(tmp_path: Path) -> None:
    strict_hashes: list[tuple[str | None, str | None]] = []
    mixed_hashes: list[tuple[str | None, str | None]] = []
    for repeat in range(3):
        strict_product, mixed_product = _products()
        with patch.dict(os.environ, {
            "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_WRITER_L0": "1",
            "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_WRITER_L0": "1",
        }):
            strict = write_strict_quad_fixed_pair_product_l0(
                strict_product, tmp_path / f"strict-stepped-{repeat}",
            )
            mixed = write_tri_quad_fixed_pair_product_l0(
                mixed_product, tmp_path / f"mixed-stepped-{repeat}",
            )
        assert strict.written and strict.readback_verified
        assert mixed.written and mixed.readback_verified
        assert strict.product_claimed is False
        assert mixed.product_claimed is False
        strict_hashes.append((strict.content_sha256, strict.manifest_sha256))
        mixed_hashes.append((mixed.content_sha256, mixed.manifest_sha256))
        strict_manifest = json.loads((tmp_path / f"strict-stepped-{repeat}" / "manifest.json").read_text())
        mixed_manifest = json.loads((tmp_path / f"mixed-stepped-{repeat}" / "manifest.json").read_text())
        assert strict_manifest["strict_quad"]["triangle_count"] == 0
        assert strict_manifest["strict_quad"]["quad_count"] == 10
        assert len(mixed_manifest["payloads"]["triangle_patch_ids"]) > 0
        assert len(mixed_manifest["payloads"]["quad_patch_ids"]) == 3
        assert (tmp_path / f"mixed-stepped-{repeat}" / "triangles.npy").is_file()
        assert (tmp_path / f"mixed-stepped-{repeat}" / "quads.npy").is_file()
    assert strict_hashes == [strict_hashes[0]] * 3
    assert mixed_hashes == [mixed_hashes[0]] * 3
