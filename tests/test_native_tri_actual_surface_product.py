from __future__ import annotations

from pathlib import Path

import pytest

from core.preprocessor.native_tri.actual_surface_product import (
    run_native_tri_actual_cad_surface_product,
)


def test_stl_is_not_relabelled_as_native_tri_cad_surface(tmp_path: Path) -> None:
    result = run_native_tri_actual_cad_surface_product(
        "tests/benchmarks/cube.stl",
        tmp_path / "out",
        explicit_mapping=[{"source_edge": 1}],
        owner_face_by_edge={1: 0},
        requested_layers=0,
        explicit_route=True,
    )
    assert result["accepted"] is False
    assert result["reason"] == "native_tri_actual_surface_requires_cad_brep_source"
    assert result["artifact_emitted"] is False
    assert not (tmp_path / "out").exists()


def test_cad_brep_product_requires_explicit_mapping(tmp_path: Path) -> None:
    result = run_native_tri_actual_cad_surface_product(
        tmp_path / "model.step",
        tmp_path / "out",
        explicit_mapping=None,
        owner_face_by_edge=None,
        requested_layers=0,
        explicit_route=True,
    )
    assert result["accepted"] is False
    assert result["reason"] == "explicit_surface_wall_edge_mapping_required"


def test_actual_cad_bl0_product_uses_authoritative_cpp_pack(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("native_brep_front_evidence_v2")
    from tests.test_native_surface_brep_actual_evidence_pack import _mapping, _write_styled_box

    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_surface_bl_front_shared_build")
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    mapping, owners = _mapping(source)
    result = run_native_tri_actual_cad_surface_product(
        source,
        tmp_path / "pack",
        explicit_mapping=mapping,
        owner_face_by_edge=owners,
        requested_layers=0,
        explicit_route=True,
        domain_side_authority_fixture=True,
    )
    assert result["accepted"] is True, result
    assert result["product"] == "native_tri_surface"
    assert result["route_selected"] is True
    assert result["independent_route"] is True
    assert result["release_claim"] is False
    assert result["publication_eligible"] is False
