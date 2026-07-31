"""L0/L1 default-OFF strict fixed-pair surface-product contract."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.preprocessor.native_quad.strict_pair_product_l0 import (
    materialize_strict_quad_fixed_pair_product_l0,
    strict_quad_fixed_pair_product_l0_enabled,
)
from core.preprocessor.native_remesh.surface_mode_contract import (
    SurfaceProductClassification,
)

_ENV = "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_PRODUCT_L0"


def _empty_triangles() -> np.ndarray:
    return np.empty((0, 3), dtype=np.int64)


def _square() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    vertices = np.array(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)),
        dtype=np.float64,
    )
    triangles = np.array(((0, 1, 2), (0, 2, 3)), dtype=np.int64)
    quads = np.array(((1, 2, 3, 0),), dtype=np.int64)
    provenance = np.array(((0, 1),), dtype=np.int64)
    features = np.array(((0, 1), (1, 2), (2, 3), (0, 3)), dtype=np.int64)
    return vertices, triangles, quads, provenance, features


def _cube() -> tuple[
    np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[int], list[int]
]:
    vertices = np.array(
        (
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 1.0), (0.0, 1.0, 1.0),
        ),
        dtype=np.float64,
    )
    source_quads = (
        (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    )
    triangles = np.asarray(
        [
            triangle
            for quad in source_quads
            for triangle in ((quad[0], quad[1], quad[2]), (quad[0], quad[2], quad[3]))
        ],
        dtype=np.int64,
    )
    quads = np.asarray(
        [(quad[1], quad[2], quad[3], quad[0]) for quad in source_quads], dtype=np.int64
    )
    provenance = np.asarray([(2 * index, 2 * index + 1) for index in range(6)], dtype=np.int64)
    features = np.asarray(
        sorted(
            {
                tuple(sorted((quad[index], quad[(index + 1) % 4])))
                for quad in source_quads
                for index in range(4)
            }
        ),
        dtype=np.int64,
    )
    source_patches = [index for index in range(6) for _ in range(2)]
    return vertices, triangles, quads, provenance, features, source_patches, list(range(6))


def _materialize(
    vertices: np.ndarray,
    triangles: np.ndarray,
    quads: np.ndarray,
    provenance: np.ndarray,
    features: np.ndarray,
    source_patches: object,
    quad_patches: object,
    *,
    candidate_vertices: np.ndarray | None = None,
    candidate_triangles: np.ndarray | None = None,
):
    return materialize_strict_quad_fixed_pair_product_l0(
        vertices,
        vertices.copy() if candidate_vertices is None else candidate_vertices,
        triangles,
        _empty_triangles() if candidate_triangles is None else candidate_triangles,
        quads,
        provenance,
        features,
        source_patch_ids=source_patches,
        candidate_quad_patch_ids=quad_patches,
    )


def test_l0_default_off_rejects_valid_candidate_without_product_or_fallback() -> None:
    vertices, triangles, quads, provenance, features = _square()
    with patch.dict(os.environ, {}, clear=True):
        result = _materialize(
            vertices, triangles, quads, provenance, features, ["wall", "wall"], ["wall"]
        )

    assert strict_quad_fixed_pair_product_l0_enabled() is False
    assert result.accepted is False
    assert result.status == "reject_strict_quad_fixed_pair_product_disabled"
    assert result.rejection_reason == "strict_quad_fixed_pair_product_l0_disabled"
    assert result.preflight.accepted is True
    assert result.product_certificate is not None and result.product_certificate.accepted
    assert result.product is None


def test_l0_enabled_square_materializes_read_only_strict_quad_three_times() -> None:
    vertices, triangles, quads, provenance, features = _square()
    with patch.dict(os.environ, {_ENV: "1"}):
        results = [
            _materialize(
                vertices, triangles, quads, provenance, features, ["wall", "wall"], ["wall"]
            )
            for _ in range(3)
        ]

    assert all(result.accepted and result.product is not None for result in results)
    assert [result.status for result in results] == ["pass_strict_quad_fixed_pair_product"] * 3
    assert [result.preflight for result in results] == [results[0].preflight] * 3
    product = results[0].product
    assert product is not None
    assert product.triangles.shape == (0, 3)
    assert product.quads.shape == (1, 4)
    assert product.quad_patch_ids == ("wall",)
    assert not product.vertices.flags.writeable
    assert not product.triangles.flags.writeable
    assert not product.quads.flags.writeable
    assert np.array_equal(product.vertices, vertices)
    assert np.array_equal(product.quads, quads)
    assert results[0].product_certificate is not None
    assert results[0].product_certificate.classification is SurfaceProductClassification.STRICT_QUAD


@pytest.mark.parametrize(
    "kind",
    ("triangles", "vertex", "quad_order", "provenance", "feature", "patch", "noncoplanar"),
)
def test_l0_unsafe_candidate_explicitly_rejects_without_any_fallback(kind: str) -> None:
    vertices, triangles, quads, provenance, features = _square()
    kwargs: dict[str, object] = {}
    if kind == "triangles":
        kwargs["candidate_triangles"] = triangles[:1].copy()
    elif kind == "vertex":
        candidate = vertices.copy()
        candidate[0, 0] = 0.25
        kwargs["candidate_vertices"] = candidate
    elif kind == "quad_order":
        quads = quads[:, ::-1].copy()
    elif kind == "provenance":
        provenance = np.array(((0, 0),), dtype=np.int64)
    elif kind == "feature":
        features = np.array(((0, 2),), dtype=np.int64)
    elif kind == "noncoplanar":
        vertices = vertices.copy()
        vertices[3, 2] = 0.5
    else:
        kwargs["quad_patches"] = ["other"]
    with patch.dict(os.environ, {_ENV: "1"}):
        result = _materialize(
            vertices,
            triangles,
            quads,
            provenance,
            features,
            ["wall", "wall"],
            kwargs.pop("quad_patches", ["wall"]),
            **kwargs,
        )

    assert result.accepted is False
    assert result.status == "reject_strict_quad_fixed_pair_preflight"
    assert result.rejection_reason == "strict_quad_pair_preflight_rejected"
    assert result.product_certificate is None
    assert result.product is None


def test_l1_cube_materializes_strict_fixed_pair_product_deterministically() -> None:
    vertices, triangles, quads, provenance, features, source_patches, quad_patches = _cube()
    with patch.dict(os.environ, {_ENV: "1"}):
        results = [
            _materialize(
                vertices,
                triangles,
                quads,
                provenance,
                features,
                source_patches,
                quad_patches,
            )
            for _ in range(3)
        ]

    assert all(result.accepted and result.product is not None for result in results)
    assert [result.preflight for result in results] == [results[0].preflight] * 3
    product = results[0].product
    assert product is not None
    assert product.triangles.shape == (0, 3)
    assert product.quads.shape == (6, 4)
    assert product.quad_patch_ids == tuple(quad_patches)
    assert np.array_equal(product.vertices, vertices)
    assert np.array_equal(product.quads, quads)


@pytest.mark.parametrize("fixture", ("cylinder.stl", "sphere.stl"))
def test_l1_missing_fixed_pair_candidate_rejects_without_tri_quad_fallback(fixture: str) -> None:
    mesh = read_stl(Path(__file__).parent / "benchmarks" / fixture)
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    triangles = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    with patch.dict(os.environ, {_ENV: "1"}):
        result = _materialize(
            vertices,
            triangles,
            np.empty((0, 4), dtype=np.int64),
            np.empty((0, 2), dtype=np.int64),
            np.empty((0, 2), dtype=np.int64),
            [None] * len(triangles),
            [],
        )

    assert result.accepted is False
    assert result.status == "reject_strict_quad_fixed_pair_preflight"
    assert result.product is None
