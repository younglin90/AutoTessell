"""Contracts for explicit, surface-only native face remeshing."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import numpy as np
import pytest
import trimesh

from core.preprocessor.native_remesh import (
    SurfaceRemeshConfig,
    native_face_remesh,
    native_quad_dominant_remesh,
)
from core.preprocessor.native_remesh.isotropic import isotropic_remesh


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


def test_protected_edge_result_is_deterministic_across_three_runs() -> None:
    mesh = trimesh.creation.icosphere(subdivisions=1)
    edge = tuple(int(value) for value in mesh.faces[0, :2])
    hashes: list[str] = []
    for _ in range(3):
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
        assert result.diagnostics.gates["protected_edges"] is True
        digest = sha256()
        digest.update(np.ascontiguousarray(result.vertices).tobytes())
        digest.update(np.ascontiguousarray(result.faces).tobytes())
        hashes.append(digest.hexdigest())
    assert hashes[0] == hashes[1] == hashes[2]


def test_isotropic_never_splits_or_moves_an_explicit_protected_edge() -> None:
    mesh = trimesh.creation.icosphere(subdivisions=1)
    edge = tuple(sorted(int(value) for value in mesh.faces[0, :2]))
    vertices, faces = isotropic_remesh(
        mesh.vertices,
        mesh.faces,
        target_edge_length=0.1,
        n_iter=1,
        protected_edges=frozenset((edge,)),
    )
    output_edges = {
        tuple(sorted((int(triangle[index]), int(triangle[(index + 1) % 3]))))
        for triangle in faces
        for index in range(3)
    }

    assert edge in output_edges
    np.testing.assert_array_equal(vertices[list(edge)], mesh.vertices[list(edge)])


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
    remeshed, accepted, record = Preprocessor()._l2_remesh(
        mesh, None, remesh_engine="native_face_remesh", prefer_native=False
    )

    assert accepted is True
    assert record["method"] == "native_face_remesh"
    assert record["params"]["route"] == "native_face_remesh"
    assert record["params"]["contract"] == "native_face"
    assert record["params"]["rejection_reason"] is None
    assert remeshed.is_watertight is True


def test_pipeline_uses_native_quad_dominant_when_explicit() -> None:
    from core.preprocessor.pipeline import Preprocessor

    mesh = trimesh.creation.icosphere(subdivisions=1)
    remeshed, accepted, record = Preprocessor()._l2_remesh(
        mesh, None, remesh_engine="native_quad_dominant", prefer_native=False
    )
    direct = native_quad_dominant_remesh(mesh.vertices, mesh.faces)
    expected_faces = np.concatenate(
        (
            direct.triangles,
            direct.quads[:, (0, 1, 2)],
            direct.quads[:, (0, 2, 3)],
        ),
        axis=0,
    )

    assert accepted is True
    assert record["method"] == "native_quad_dominant"
    assert record["params"]["route"] == "native_quad_dominant"
    assert record["params"]["contract"] == "native_quad"
    assert "accepted_pairs" in record["params"]
    np.testing.assert_array_equal(remeshed.vertices, direct.vertices)
    np.testing.assert_array_equal(remeshed.faces, expected_faces)


def test_pipeline_native_face_rejection_does_not_fall_back_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.preprocessor.pipeline import Preprocessor

    preprocessor = Preprocessor()
    mesh = trimesh.creation.box()
    open_mesh = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces[:-1], process=False)

    def legacy_route(*args: Any, **kwargs: Any) -> tuple[trimesh.Trimesh, bool, dict[str, Any]]:
        raise AssertionError("explicit native face rejection must not reach legacy remeshing")

    monkeypatch.setattr(preprocessor._remesher, "remesh_l2", legacy_route)
    remeshed, accepted, record = preprocessor._l2_remesh(
        open_mesh,
        None,
        remesh_engine="native_face_remesh",
        prefer_native=False,
    )

    assert accepted is False
    assert record["method"] == "native_face_remesh"
    assert "watertight manifold" in record["params"]["rejection_reason"]
    np.testing.assert_array_equal(remeshed.vertices, open_mesh.vertices)
    np.testing.assert_array_equal(remeshed.faces, open_mesh.faces)


def test_pipeline_non_explicit_routes_preserve_existing_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.preprocessor.pipeline import Preprocessor

    preprocessor = Preprocessor()
    mesh = trimesh.creation.icosphere(subdivisions=1)
    calls: list[tuple[str, int | None, str | None]] = []
    legacy_record: dict[str, Any] = {"method": "legacy"}
    native_record: dict[str, Any] = {"method": "native_isotropic"}

    def legacy_route(
        passed_mesh: trimesh.Trimesh,
        target_faces: int | None = None,
        element_size: float | None = None,
        remesh_engine: str = "auto",
    ) -> tuple[trimesh.Trimesh, bool, dict[str, Any]]:
        assert element_size is None
        calls.append(("legacy", target_faces, remesh_engine))
        return passed_mesh, True, legacy_record

    def native_route(
        passed_mesh: trimesh.Trimesh,
        target_faces: int | None,
    ) -> tuple[trimesh.Trimesh, bool, dict[str, Any]]:
        calls.append(("native", target_faces, None))
        return passed_mesh, True, native_record

    monkeypatch.setattr(preprocessor._remesher, "remesh_l2", legacy_route)
    monkeypatch.setattr(preprocessor, "_l2_remesh_native", native_route)

    legacy_mesh, legacy_accepted, legacy_step = preprocessor._l2_remesh(
        mesh,
        31,
        remesh_engine="AUTO",
        prefer_native=False,
    )
    native_mesh, native_accepted, native_step = preprocessor._l2_remesh(
        mesh,
        47,
        remesh_engine="auto",
        prefer_native=True,
    )

    assert legacy_mesh is mesh
    assert legacy_accepted is True
    assert legacy_step is legacy_record
    assert native_mesh is mesh
    assert native_accepted is True
    assert native_step is native_record
    assert calls == [("legacy", 31, "AUTO"), ("native", 47, None)]
