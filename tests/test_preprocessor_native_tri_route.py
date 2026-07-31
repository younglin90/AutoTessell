"""Fail-closed runtime contracts for the opt-in native-tri L2 route."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import trimesh

from core.preprocessor.native_tri.route import run_native_tri_l2_route
from core.preprocessor.pipeline import Preprocessor

_BENCHMARKS = Path(__file__).parent / "benchmarks"
_CORPUS_FIXTURES = (
    "cube.stl",
    "cylinder.stl",
    "mixed_features_wing_with_spike.stl",
    "very_thin_disk_0_01mm.stl",
)


def _array_hash(values: np.ndarray) -> str:
    """Independent dtype/shape/byte hash for the source-preservation contract."""
    contiguous = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(str(contiguous.dtype).encode("ascii"))
    digest.update(np.asarray(contiguous.shape, dtype=np.int64).tobytes())
    digest.update(contiguous.tobytes())
    return digest.hexdigest()


def _feature_edges(vertices: np.ndarray, faces: np.ndarray) -> set[tuple[int, int]]:
    """Return the deterministic 30-degree interior-edge audit set."""
    incidence: dict[tuple[int, int], list[int]] = {}
    for face_index, (a, b, c) in enumerate(faces.tolist()):
        for first, second in ((a, b), (b, c), (c, a)):
            edge = tuple(sorted((int(first), int(second))))
            incidence.setdefault(edge, []).append(face_index)
    normals = np.cross(
        vertices[faces[:, 1]] - vertices[faces[:, 0]],
        vertices[faces[:, 2]] - vertices[faces[:, 0]],
    )
    lengths = np.linalg.norm(normals, axis=1)
    normals /= np.maximum(lengths[:, None], np.finfo(float).tiny)
    result: set[tuple[int, int]] = set()
    for edge, attached in incidence.items():
        if len(attached) != 2:
            continue
        cosine = float(np.clip(np.dot(normals[attached[0]], normals[attached[1]]), -1.0, 1.0))
        if float(np.degrees(np.arccos(cosine))) >= 30.0:
            result.add(edge)
    return result


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


def test_native_tri_route_is_explicit_without_prefer_native() -> None:
    mesh = trimesh.load(str(_BENCHMARKS / "cube.stl"), force="mesh")
    output, passed, record = Preprocessor()._l2_remesh(
        mesh,
        target_faces=50,
        remesh_engine="native_tri",
        prefer_native=False,
    )

    assert passed is False
    assert record["method"] == "native_tri_fail_closed"
    assert record["params"]["route"] == "native_tri"
    assert record["params"]["requested_surface_product"] == "tri"
    np.testing.assert_array_equal(output.vertices, mesh.vertices)
    np.testing.assert_array_equal(output.faces, mesh.faces)


@pytest.mark.parametrize(
    ("engine", "product"),
    (("native_strict_quad", "strict_quad"), ("native_tri_quad", "tri_quad")),
)
def test_surface_product_routes_defer_without_certificate(
    engine: str,
    product: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mesh = trimesh.load(str(_BENCHMARKS / "cube.stl"), force="mesh")
    preprocessor = Preprocessor()

    def unexpected_candidate(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("strict or mixed request must not use native_quad_dominant")

    monkeypatch.setattr(
        preprocessor,
        "_l2_remesh_native_quad_dominant",
        unexpected_candidate,
    )
    output, passed, record = preprocessor._l2_remesh(
        mesh,
        target_faces=50,
        remesh_engine=engine,
        prefer_native=False,
    )

    assert passed is False
    assert record["method"] == f"{engine}_deferred"
    assert record["params"]["route"] == engine
    assert record["params"]["requested_surface_product"] == product
    assert record["params"]["product_certificate"] == "required"
    assert record["params"]["rejection_reason"] == "source_product_certificate_required"
    assert record["params"]["source_geometry_preserved"] is True
    assert record["params"]["source_topology_preserved"] is True
    assert record["params"]["triangular_handoff"] is False
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


@pytest.mark.parametrize("name", _CORPUS_FIXTURES)
@pytest.mark.parametrize("boundary_layers", [0, 1])
def test_native_tri_fail_closed_corpus_preserves_source_and_layer_contract(
    name: str,
    boundary_layers: int,
) -> None:
    """Unsupported topology edits must reject every representative source exactly."""
    mesh = trimesh.load(str(_BENCHMARKS / name), force="mesh")
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    vertex_hash = _array_hash(vertices)
    face_hash = _array_hash(faces)
    feature_edges = _feature_edges(vertices, faces)

    results = [
        run_native_tri_l2_route(
            vertices,
            faces,
            target_faces=100,
            boundary_layers=boundary_layers,
        )
        for _ in range(3)
    ]

    expected_reason = (
        "source_contract_unavailable"
        if boundary_layers == 0
        else "boundary_layers_unsupported_by_surface_route"
    )
    signatures = {
        (
            result.reason,
            result.source_vertices_hash,
            result.source_faces_hash,
            result.output_vertices_hash,
            result.output_faces_hash,
            result.provenance_hash,
            result.boundary_layers_actual,
            result.layer_budget_reserved,
        )
        for result in results
    }
    assert len(signatures) == 1
    for result in results:
        assert result.accepted is False
        assert result.reason == expected_reason
        assert result.source_envelope_preserved is True
        assert result.topology_preserved is True
        assert result.provenance_preserved is True
        assert result.source_vertices_hash == vertex_hash == result.output_vertices_hash
        assert result.source_faces_hash == face_hash == result.output_faces_hash
        assert result.provenance_hash == face_hash
        assert result.vertices.dtype == vertices.dtype
        assert result.faces.dtype == faces.dtype
        assert result.vertices.shape == vertices.shape
        assert result.faces.shape == faces.shape
        assert _array_hash(result.vertices) == vertex_hash
        assert _array_hash(result.faces) == face_hash
        assert _feature_edges(result.vertices, result.faces) == feature_edges
        assert result.boundary_layers_requested == boundary_layers
        assert result.boundary_layers_actual == 0
        assert result.layer_budget_reserved == 0
        np.testing.assert_array_equal(result.vertices, vertices)
        np.testing.assert_array_equal(result.faces, faces)
