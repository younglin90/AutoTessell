"""Measured authority for the independent strict-quad and TRI+QUAD lanes."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from core.evaluator.native_surface_release_evidence import certify_fixed_pair_surface_output
from core.preprocessor.native_quad.strict_quad_fixed_pair_writer_l0 import (
    write_strict_quad_fixed_pair_product_l0,
)
from core.preprocessor.native_quad.tri_quad_fixed_pair_writer_l0 import (
    write_tri_quad_fixed_pair_product_l0,
)
from tests.test_native_surface_complex_release_corpus import _products, _stepped_prism


def test_fixed_pair_products_have_measured_source_output_authority(tmp_path: Path) -> None:
    strict_result, mixed_result = _products()
    vertices, triangles, _pairs, _patches, _features = _stepped_prism()
    source = tmp_path / "stepped-source.snapshot"
    source.write_bytes(b"authoritative stepped source snapshot")
    with patch.dict(
        os.environ,
        {
            "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_WRITER_L0": "1",
            "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_WRITER_L0": "1",
        },
    ):
        strict_written = write_strict_quad_fixed_pair_product_l0(strict_result, tmp_path / "strict")
        mixed_written = write_tri_quad_fixed_pair_product_l0(mixed_result, tmp_path / "mixed")
    strict = certify_fixed_pair_surface_output(
        strict_result, strict_written, source, vertices, triangles
    )
    mixed = certify_fixed_pair_surface_output(
        mixed_result, mixed_written, source, vertices, triangles
    )
    for evidence in (strict, mixed):
        assert evidence["authoritative"] is True, evidence
        assert evidence["shape_preserved"] is True
        assert evidence["source_face_provenance"] is True
        assert evidence["provenance_complete"] is True
        assert evidence["surface_topology"]["n_open_edges"] == 0
        assert len(evidence["source_shape_sha256"]) == 64
        assert len(evidence["output_shape_sha256"]) == 64


def test_fixed_pair_cube_artifacts_bind_their_closed_source(tmp_path: Path) -> None:
    import numpy as np

    from core.evaluator.surface_physical_group_provenance import AuthoritativePhysicalGroupMapping
    from core.preprocessor.native_quad.strict_pair_transaction_l0 import (
        materialize_strict_quad_pair_transaction_l0,
    )
    from core.preprocessor.native_quad.tri_quad_fixed_pair_product_l0 import (
        AuthoritativeTriQuadFeatureEdges,
        AuthoritativeTriQuadPatchIds,
        materialize_tri_quad_fixed_pair_product_l0,
    )
    from tests.test_native_strict_quad_fixed_pair_product_l0 import _cube

    vertices, triangles, _quads, pairs, features, patches, _groups = _cube()
    groups = AuthoritativePhysicalGroupMapping(tuple("wall" for _ in patches), True)
    with patch.dict(
        os.environ,
        {
            "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_PRODUCT_L0": "1",
            "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_PRODUCT_L0": "1",
        },
    ):
        strict = materialize_strict_quad_pair_transaction_l0(
            vertices,
            triangles,
            pairs,
            features,
            source_patch_ids=patches,
            source_physical_groups=groups,
        )
        mixed = materialize_tri_quad_fixed_pair_product_l0(
            vertices,
            triangles,
            np.asarray(((0, 1),), dtype=np.int64),
            AuthoritativeTriQuadFeatureEdges(tuple(map(tuple, features.tolist())), True),
            source_patch_ids=AuthoritativeTriQuadPatchIds(tuple(patches), True),
            source_physical_groups=groups,
        )
    assert strict.accepted and strict.product_result is not None
    assert mixed.accepted and mixed.product is not None
    source = tmp_path / "cube-source.snapshot"
    source.write_bytes(b"authoritative closed cube source snapshot")
    with patch.dict(
        os.environ,
        {
            "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_WRITER_L0": "1",
            "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_WRITER_L0": "1",
        },
    ):
        strict_written = write_strict_quad_fixed_pair_product_l0(
            strict.product_result, tmp_path / "strict-cube"
        )
        mixed_written = write_tri_quad_fixed_pair_product_l0(mixed, tmp_path / "mixed-cube")
    for result, written in ((strict.product_result, strict_written), (mixed, mixed_written)):
        evidence = certify_fixed_pair_surface_output(result, written, source, vertices, triangles)
        assert evidence["authoritative"] is True, evidence
        assert evidence["surface_topology"]["n_open_edges"] == 0
