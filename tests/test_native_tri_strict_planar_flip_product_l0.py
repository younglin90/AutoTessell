from __future__ import annotations

import os
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import numpy as np

import core.preprocessor.native_tri.strict_planar_flip_product_l0 as product_module
from core.analyzer.readers import read_stl
from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_tri.strict_planar_flip_product_l0 import (
    materialize_strict_planar_flip_product_l0,
)
from core.preprocessor.native_tri.strict_planar_flip_source_l0 import (
    AuthoritativeNativeTriFeatureEdges,
    AuthoritativeNativeTriPatchIds,
    StrictPlanarFlipSourceRequest,
    ingest_strict_planar_flip_source_l0,
)

_ENV = "AUTO_TESSELL_TRI_STRICT_PLANAR_FLIP_PRODUCT_L0"


def _array_hash(values: np.ndarray) -> str:
    digest = sha256()
    digest.update(str(values.dtype).encode("ascii"))
    digest.update(np.asarray(values.shape, dtype=np.int64).tobytes())
    digest.update(values.tobytes())
    return digest.hexdigest()


def _write_source(path: Path, *, residual: bool = False) -> None:
    facets = """
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 1 0 0
  vertex 2 1 0
 endloop
endfacet
facet normal 0 0 1
 outer loop
  vertex 1 0 0
  vertex 0 1 0
  vertex 2 1 0
 endloop
endfacet
"""
    if residual:
        facets += """
facet normal 0 0 1
 outer loop
  vertex 4 0 0
  vertex 5 0 0
  vertex 4 1 0
 endloop
endfacet
"""
    path.write_text(f"solid source\n{facets}endsolid source\n", encoding="utf-8")


def _edge(faces: np.ndarray) -> tuple[int, int]:
    owners: dict[tuple[int, int], int] = {}
    for face in faces.tolist():
        for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = (min(int(first), int(second)), max(int(first), int(second)))
            owners[edge] = owners.get(edge, 0) + 1
    return next(edge for edge, count in owners.items() if count == 2)


def _source(tmp_path: Path, *, residual: bool = False, groups: tuple[str, ...] | None = None):
    path = tmp_path / "source.stl"
    _write_source(path, residual=residual)
    mesh = read_stl(path)
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    payloads = tuple("wall" for _ in faces)
    physical_groups = groups if groups is not None else payloads
    request = StrictPlanarFlipSourceRequest(
        source_path=path,
        source_sha256=sha256(path.read_bytes()).hexdigest(),
        vertices_sha256=_array_hash(vertices),
        faces_sha256=_array_hash(faces),
        patch_ids=AuthoritativeNativeTriPatchIds(payloads, True),
        feature_edges=AuthoritativeNativeTriFeatureEdges((), True),
        physical_groups=AuthoritativePhysicalGroupMapping(physical_groups, True),
    )
    result = ingest_strict_planar_flip_source_l0(request)
    assert result.accepted and result.source is not None
    return result.source, _edge(faces), vertices.copy(), faces.copy()


def test_source_locked_default_off_never_runs_a_product_candidate(tmp_path: Path) -> None:
    source, edge, _, _ = _source(tmp_path)
    with patch.dict(os.environ, {}, clear=True):
        result = materialize_strict_planar_flip_product_l0(source, edge)

    assert not result.accepted and result.product is None
    assert result.status == "reject_strict_planar_flip_disabled"


def test_enabled_actual_flip_preserves_authority_and_whole_face_envelope(tmp_path: Path) -> None:
    source, edge, before_vertices, before_faces = _source(tmp_path, residual=True)
    with patch.dict(os.environ, {_ENV: "1"}, clear=True):
        result = materialize_strict_planar_flip_product_l0(source, edge)

    assert result.accepted and result.product is not None
    assert result.status == "pass_strict_planar_flip_candidate"
    assert result.source_boundary_preserved and result.source_features_preserved
    assert result.topology_preserved and result.provenance_preserved
    assert result.authority_preserved and result.independent_product_ready is False
    product = result.product
    assert product.source_sha256 == source.source_sha256
    assert product.source_physical_groups_hash == source.physical_groups_sha256
    assert (
        product.patch_ids == source.patch_ids and product.physical_groups == source.physical_groups
    )
    assert product.face_region_provenance[:2] == ((0, 1), (0, 1))
    assert product.face_region_provenance[2] == (2,)
    assert not product.vertices.flags.writeable and not product.faces.flags.writeable
    np.testing.assert_array_equal(source.vertices, before_vertices)
    np.testing.assert_array_equal(source.faces, before_faces)
    assert product.faces[2].tobytes() == source.faces[2].tobytes()
    assert product.faces[0].tobytes() != source.faces[0].tobytes()
    assert product.faces[1].tobytes() != source.faces[1].tobytes()


def test_authority_pair_and_feature_mismatches_fail_closed(tmp_path: Path) -> None:
    source, edge, _, _ = _source(tmp_path, groups=("wall", "inlet"))
    with patch.dict(os.environ, {_ENV: "1"}, clear=True):
        group_mismatch = materialize_strict_planar_flip_product_l0(source, edge)
    assert group_mismatch.status == "reject_strict_planar_flip_preflight"
    assert group_mismatch.product is None

    path = tmp_path / "feature.stl"
    _write_source(path)
    mesh = read_stl(path)
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    request = StrictPlanarFlipSourceRequest(
        path,
        sha256(path.read_bytes()).hexdigest(),
        _array_hash(vertices),
        _array_hash(faces),
        AuthoritativeNativeTriPatchIds(("wall", "wall"), True),
        AuthoritativeNativeTriFeatureEdges((edge,), True),
        AuthoritativePhysicalGroupMapping(("wall", "wall"), True),
    )
    admitted = ingest_strict_planar_flip_source_l0(request)
    assert admitted.accepted and admitted.source is not None
    with patch.dict(os.environ, {_ENV: "1"}, clear=True):
        feature = materialize_strict_planar_flip_product_l0(admitted.source, edge)
    assert feature.status == "reject_strict_planar_flip_feature" and feature.product is None


def test_source_or_provenance_mismatch_never_materializes(tmp_path: Path, monkeypatch) -> None:
    assert materialize_strict_planar_flip_product_l0(object(), (0, 1)).product is None
    source, edge, _, _ = _source(tmp_path, residual=True)
    forged = replace(source, faces=source.faces.copy())
    with patch.dict(os.environ, {_ENV: "1"}, clear=True):
        source_mismatch = materialize_strict_planar_flip_product_l0(forged, edge)
    assert source_mismatch.status == "reject_strict_planar_flip_source"
    assert source_mismatch.product is None
    original = product_module.OperatorTransaction.flip_edge

    def _tampered_flip(self, candidate_edge):
        report = original(self, candidate_edge)
        if report.accepted:
            self.state.faces[2] = self.state.faces[2, ::-1]
        return report

    monkeypatch.setattr(product_module.OperatorTransaction, "flip_edge", _tampered_flip)
    with patch.dict(os.environ, {_ENV: "1"}, clear=True):
        result = materialize_strict_planar_flip_product_l0(source, edge)

    assert result.status == "reject_strict_planar_flip_certificate"
    assert result.rejection_reason == "source_region_certificate_failed"
    assert result.product is None
