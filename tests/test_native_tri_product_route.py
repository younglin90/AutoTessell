from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.evaluator.surface_physical_group_provenance import AuthoritativePhysicalGroupMapping
from core.preprocessor.native_tri.product_route import run_native_tri_surface_product
from core.preprocessor.native_tri.release_route import NativeTriSourceAuthority


def _cube_authority(mesh) -> NativeTriSourceAuthority:
    groups = tuple("wall" for _ in mesh.faces)
    return NativeTriSourceAuthority(
        patch_ids=groups,
        physical_groups=AuthoritativePhysicalGroupMapping(groups, True),
        feature_edges=(),
        feature_authoritative=True,
    )


def test_tri_product_boundary_refuses_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("AUTO_TESSELL_NATIVE_TRI_RELEASE", raising=False)
    result = run_native_tri_surface_product(
        np.zeros((3, 3)), np.asarray([[0, 1, 2]], dtype=np.int64),
        target_edge_length=0.3, source_authority=None,
    )
    assert result["accepted"] is False
    assert result["reason"] == "explicit_product_route_required"


def test_tri_quad_never_enters_native_tri_product(monkeypatch):
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_RELEASE", "1")
    result = run_native_tri_surface_product(
        np.zeros((3, 3)), np.asarray([[0, 1, 2]], dtype=np.int64),
        target_edge_length=0.3, source_authority=None,
        product="tri_quad", explicit_route=True,
    )
    assert result["accepted"] is False
    assert result["reason"] == "product_boundary_mismatch"
    assert result["route_selected"] is False


def test_explicit_native_tri_cube_product_is_independent(monkeypatch):
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_RELEASE", "1")
    mesh = read_stl(Path("tests/benchmarks/cube.stl"))
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    edge_lengths = np.concatenate([
        np.linalg.norm(vertices[faces[index]] - vertices[faces[(index + 1) % 3]], axis=1)
        for index in range(3)
    ])
    result = run_native_tri_surface_product(
        vertices, faces, target_edge_length=float(np.median(edge_lengths) * 0.5),
        source_authority=_cube_authority(mesh), explicit_route=True,
    )
    assert result["accepted"] is True
    assert result["product"] == "native_tri_surface"
    assert result["route_selected"] is True
    assert result["independent_route"] is True
    assert result["evidence"]["output_topology_valid"] is True
