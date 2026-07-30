"""Fail-closed runtime contracts for the opt-in native-tri L2 route."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from core.preprocessor.native_tri.route import run_native_tri_l2_route
from core.preprocessor.pipeline import Preprocessor

_BENCHMARKS = Path(__file__).parent / "benchmarks"


@pytest.mark.parametrize("name", ["cube.stl", "sphere.stl"])
def test_native_tri_route_is_deterministic_unchanged_rejection(name: str) -> None:
    mesh = trimesh.load(str(_BENCHMARKS / name), force="mesh")
    results = [
        run_native_tri_l2_route(mesh.vertices, mesh.faces, target_faces=100, boundary_layers=0)
        for _ in range(3)
    ]

    for result in results:
        assert result.accepted is False
        assert result.reason == "source_contract_unavailable"
        assert result.source_envelope_preserved is True
        assert result.topology_preserved is True
        assert result.provenance_preserved is True
        assert result.source_vertices_hash == result.output_vertices_hash
        assert result.source_faces_hash == result.output_faces_hash == result.provenance_hash
        assert result.target_faces_requested == 100
        assert result.target_faces_actual == len(mesh.faces)
        assert result.target_faces_absolute_error == abs(len(mesh.faces) - 100)
        assert result.target_faces_relative_error == pytest.approx(abs(len(mesh.faces) - 100) / 100)
        assert result.boundary_layers_requested == 0
        assert result.boundary_layers_actual == 0
        assert result.layer_budget_reserved == 0
        np.testing.assert_array_equal(result.vertices, mesh.vertices)
        np.testing.assert_array_equal(result.faces, mesh.faces)

    assert [result.output_vertices_hash for result in results] == [
        results[0].output_vertices_hash
    ] * 3
    assert [result.output_faces_hash for result in results] == [results[0].output_faces_hash] * 3


def test_native_tri_pipeline_route_is_explicit_fail_closed() -> None:
    mesh = trimesh.load(str(_BENCHMARKS / "cube.stl"), force="mesh")
    output, passed, record = Preprocessor()._l2_remesh(
        mesh,
        target_faces=50,
        remesh_engine="native_tri",
        prefer_native=True,
    )

    assert passed is False
    assert record["method"] == "native_tri_fail_closed"
    assert record["params"]["reason"] == "source_contract_unavailable"
    assert record["params"]["target_faces_requested"] == 50
    assert record["params"]["target_faces_actual"] == len(mesh.faces)
    assert record["params"]["boundary_layers_actual"] == 0
    assert record["params"]["layer_budget_reserved"] == 0
    np.testing.assert_array_equal(output.vertices, mesh.vertices)
    np.testing.assert_array_equal(output.faces, mesh.faces)


def test_default_native_l2_does_not_select_the_opt_in_tri_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mesh = trimesh.load(str(_BENCHMARKS / "cube.stl"), force="mesh")
    preprocessor = Preprocessor()
    calls: list[str] = []

    def fake_isotropic(_mesh, _target_faces):
        calls.append("isotropic")
        return _mesh, True, {"method": "native_isotropic"}

    monkeypatch.setattr(preprocessor, "_l2_remesh_native", fake_isotropic)
    output, passed, record = preprocessor._l2_remesh(
        mesh,
        target_faces=50,
        remesh_engine="auto",
        prefer_native=True,
    )

    assert calls == ["isotropic"]
    assert passed is True
    assert record["method"] == "native_isotropic"
    assert output is mesh
