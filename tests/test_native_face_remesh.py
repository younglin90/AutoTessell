"""Contracts for explicit, surface-only native face remeshing."""

from __future__ import annotations

import numpy as np
import trimesh

from core.preprocessor.native_remesh import SurfaceRemeshConfig, native_face_remesh


def test_closed_surface_accepts_all_native_face_gates() -> None:
    mesh = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    result = native_face_remesh(mesh.vertices, mesh.faces, config=SurfaceRemeshConfig(iterations=1))

    assert result.accepted is True
    assert all(result.diagnostics.gates.values())
    assert result.diagnostics.watertight is True
    assert result.diagnostics.manifold is True


def test_open_surface_rejects_and_preserves_input() -> None:
    mesh = trimesh.creation.box()
    faces = mesh.faces[:-1]
    result = native_face_remesh(mesh.vertices, faces)

    assert result.accepted is False
    assert "watertight manifold" in (result.diagnostics.rejection_reason or "")
    assert np.array_equal(result.vertices, mesh.vertices)
    assert np.array_equal(result.faces, faces)


def test_predictor_failure_keeps_deterministic_native_path() -> None:
    class FailingPredictor:
        def predict(self, vertices: np.ndarray, faces: np.ndarray) -> dict[str, float]:
            raise RuntimeError("offline")

    mesh = trimesh.creation.icosphere(subdivisions=1)
    result = native_face_remesh(
        mesh.vertices,
        mesh.faces,
        config=SurfaceRemeshConfig(iterations=1),
        predictor=FailingPredictor(),
    )

    assert result.accepted is True
    assert result.diagnostics.predictor_used is False
    assert result.diagnostics.predictor_error == "predictor failed: RuntimeError"


def test_explicit_protected_edge_is_preserved_and_reported() -> None:
    mesh = trimesh.creation.icosphere(subdivisions=1)
    edge = tuple(int(value) for value in mesh.faces[0, :2])
    result = native_face_remesh(
        mesh.vertices,
        mesh.faces,
        config=SurfaceRemeshConfig(
            target_edge_length=2.0,
            iterations=1,
            protected_edges=(edge,),
        ),
    )

    assert result.accepted is True
    assert result.diagnostics.protected_edges == 1
    assert result.diagnostics.protected_edges_preserved is True
    assert result.diagnostics.gates["protected_edges"] is True


def test_invalid_protected_edge_fails_closed() -> None:
    mesh = trimesh.creation.icosphere(subdivisions=1)
    result = native_face_remesh(
        mesh.vertices,
        mesh.faces,
        config=SurfaceRemeshConfig(protected_edges=((0, len(mesh.vertices)),)),
    )

    assert result.accepted is False
    assert "protected_edges" in (result.diagnostics.rejection_reason or "")


def test_pipeline_uses_native_face_only_when_explicit() -> None:
    from core.preprocessor.pipeline import Preprocessor

    mesh = trimesh.creation.icosphere(subdivisions=1)
    _, accepted, record = Preprocessor()._l2_remesh(
        mesh, None, remesh_engine="native_face_remesh", prefer_native=False
    )

    assert accepted is True
    assert record["method"] == "native_face_remesh"


def test_pipeline_uses_native_quad_dominant_when_explicit() -> None:
    from core.preprocessor.pipeline import Preprocessor

    mesh = trimesh.creation.icosphere(subdivisions=1)
    _, accepted, record = Preprocessor()._l2_remesh(
        mesh, None, remesh_engine="native_quad_dominant", prefer_native=False
    )

    assert accepted is True
    assert record["method"] == "native_quad_dominant"
    assert record["params"]["route"] == "native_quad_dominant"
    assert record["params"]["contract"] == "native_quad"
    assert "accepted_pairs" in record["params"]
