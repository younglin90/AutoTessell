"""Direct native-face TypeError reproduction and fail-closed evidence."""

from __future__ import annotations

from hashlib import sha256

import numpy as np
import pytest
import trimesh

from core.preprocessor.native_remesh import SurfaceRemeshConfig, native_face_remesh


def _digest(vertices: np.ndarray, faces: np.ndarray) -> str:
    digest = sha256()
    for values in (vertices, faces):
        contiguous = np.ascontiguousarray(values)
        digest.update(contiguous.dtype.str.encode("ascii"))
        digest.update(repr(contiguous.shape).encode("ascii"))
        digest.update(contiguous.tobytes())
    return digest.hexdigest()


@pytest.mark.parametrize(
    "protected",
    (
        False,
        True,
    ),
)
def test_direct_native_face_canonical_path_has_no_type_error_and_is_deterministic(
    protected: bool,
) -> None:
    """Current canonical direct calls reproduce no historical TypeError."""
    mesh = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    edge = tuple(int(value) for value in mesh.faces[0, :2])
    config = SurfaceRemeshConfig(
        target_edge_length=2.0 if protected else None,
        iterations=1,
        protected_edges=(edge,) if protected else (),
    )
    signatures: list[tuple[bool, str | None, str]] = []
    for _ in range(3):
        try:
            result = native_face_remesh(mesh.vertices, mesh.faces, config=config)
        except TypeError as error:
            pytest.fail(f"direct native_face_remesh TypeError reproduced: {error}")
        signatures.append(
            (
                result.accepted,
                result.diagnostics.rejection_reason,
                _digest(result.vertices, result.faces),
            )
        )
    assert signatures == [signatures[0], signatures[0], signatures[0]]
    assert signatures[0][0] is True


def test_direct_native_face_type_error_is_explicit_fail_closed_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lower-level TypeError never produces a repaired or accepted surface."""
    import core.preprocessor.native_remesh.face as face

    mesh = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    vertices_before = np.asarray(mesh.vertices, dtype=np.float64).copy()
    faces_before = np.asarray(mesh.faces, dtype=np.int64).copy()

    def raise_type_error(*_args: object, **_kwargs: object) -> tuple[np.ndarray, np.ndarray]:
        raise TypeError("cycle59 sentinel")

    monkeypatch.setattr(face, "isotropic_remesh", raise_type_error)
    result = native_face_remesh(mesh.vertices, mesh.faces, config=SurfaceRemeshConfig(iterations=1))

    assert result.accepted is False
    assert result.diagnostics.rejection_reason == "native operation failed: TypeError"
    np.testing.assert_array_equal(result.vertices, vertices_before)
    np.testing.assert_array_equal(result.faces, faces_before)
