"""C++23 parity contracts for the read-only native-tri source topology audit."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
import trimesh

from core.preprocessor.native_tri.certificate import (
    _surface_topology_audit,
    _surface_topology_audit_python,
    diagnose_native_tri_source_certificate,
    topology_audit_cpp23_enabled,
)

_TOPOLOGY_AUDIT_ENV = "AUTO_TESSELL_TRI_TOPOLOGY_AUDIT_CPP23"


def _native_audit() -> object:
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "triangle_surface_topology_audit"):
        pytest.skip("native_metrics.triangle_surface_topology_audit is not built")
    return native


def _sha256(values: np.ndarray) -> str:
    return hashlib.sha256(values.tobytes()).hexdigest()


def _signature(audit: object) -> tuple[object, ...]:
    return tuple(
        getattr(audit, name)
        for name in (
            "valid",
            "closed_oriented_manifold",
            "edge_count",
            "component_count",
            "euler_characteristic",
        )
    )


def _direct_signature(
    native: object, vertices: np.ndarray, faces: np.ndarray
) -> tuple[object, ...]:
    result = native.triangle_surface_topology_audit(vertices, faces)  # type: ignore[attr-defined]
    return tuple(
        result[name]
        for name in (
            "valid",
            "closed_oriented_manifold",
            "edge_count",
            "component_count",
            "euler_characteristic",
        )
    )


def _face_provenance(face_count: int) -> tuple[tuple[int, ...], ...]:
    return tuple((index,) for index in range(face_count))


def _fixture(name: str) -> tuple[np.ndarray, np.ndarray]:
    mesh = trimesh.load(str(Path(__file__).parent / "benchmarks" / name), force="mesh")
    return (
        np.ascontiguousarray(mesh.vertices, dtype=np.float64),
        np.ascontiguousarray(mesh.faces, dtype=np.int64),
    )


@pytest.mark.parametrize(
    ("vertices", "faces", "closed"),
    [
        (
            np.array(
                (
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (0.0, 0.0, 1.0),
                )
            ),
            np.array(((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)), dtype=np.int64),
            True,
        ),
        (
            np.array(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))),
            np.array(((0, 1, 2),), dtype=np.int64),
            False,
        ),
        (
            np.array(
                (
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (0.0, 0.0, 1.0),
                )
            ),
            np.array(((0, 1, 2), (0, 1, 3), (0, 3, 2), (1, 2, 3)), dtype=np.int64),
            False,
        ),
        (
            np.array(
                (
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (0.0, 0.0, 1.0),
                    (0.0, -1.0, 0.0),
                )
            ),
            np.array(((0, 1, 2), (1, 0, 3), (0, 1, 4)), dtype=np.int64),
            False,
        ),
    ],
)
def test_native_topology_audit_matches_python_for_valid_and_rejected_topology(
    vertices: np.ndarray,
    faces: np.ndarray,
    closed: bool,
) -> None:
    native = _native_audit()
    vertices = np.ascontiguousarray(vertices, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    expected = _surface_topology_audit_python(vertices, faces)

    assert _direct_signature(native, vertices, faces) == _signature(expected)
    assert expected.valid is True
    assert expected.closed_oriented_manifold is closed


def test_native_topology_audit_rejects_nonfinite_zero_area_and_invalid_index() -> None:
    native = _native_audit()
    cases = (
        (
            np.array(((np.nan, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))),
            np.array(((0, 1, 2),), dtype=np.int64),
        ),
        (
            np.array(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0))),
            np.array(((0, 1, 2),), dtype=np.int64),
        ),
        (
            np.array(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))),
            np.array(((0, 1, 3),), dtype=np.int64),
        ),
    )
    for vertices, faces in cases:
        result = native.triangle_surface_topology_audit(vertices, faces)  # type: ignore[attr-defined]
        assert result == {
            "valid": False,
            "closed_oriented_manifold": False,
            "edge_count": 0,
            "component_count": 0,
            "euler_characteristic": None,
        }


def test_native_topology_audit_direct_abi_is_strict_and_immutable() -> None:
    native = _native_audit()
    vertices, faces = _fixture("cube.stl")
    vertex_hash = _sha256(vertices)
    face_hash = _sha256(faces)

    outputs = [_direct_signature(native, vertices, faces) for _ in range(3)]

    assert outputs == [outputs[0]] * 3
    assert _sha256(vertices) == vertex_hash
    assert _sha256(faces) == face_hash
    with pytest.raises((TypeError, ValueError), match="C-contiguous float64"):
        native.triangle_surface_topology_audit(vertices.astype(np.float32), faces)  # type: ignore[attr-defined]
    with pytest.raises((TypeError, ValueError), match="C-contiguous int64"):
        native.triangle_surface_topology_audit(vertices, faces.astype(np.int32))  # type: ignore[attr-defined]
    with pytest.raises((TypeError, ValueError)):
        native.triangle_surface_topology_audit(vertices[:, ::-1], faces)  # type: ignore[attr-defined]


def test_default_off_never_loads_native_audit() -> None:
    vertices, faces = _fixture("cube.stl")
    expected = _surface_topology_audit_python(vertices, faces)

    with (
        patch.dict(os.environ, {}, clear=True),
        patch(
            "core.utils.native_extensions.load_native_metrics",
            side_effect=AssertionError("default-OFF audit selected native extension"),
        ),
    ):
        assert topology_audit_cpp23_enabled() is False
        assert _surface_topology_audit(vertices, faces) == expected


def test_opt_in_missing_symbol_falls_back_to_python_oracle() -> None:
    vertices, faces = _fixture("cube.stl")
    expected = _surface_topology_audit_python(vertices, faces)

    with (
        patch.dict(os.environ, {_TOPOLOGY_AUDIT_ENV: "1"}),
        patch("core.utils.native_extensions.load_native_metrics", return_value=SimpleNamespace()),
    ):
        assert _surface_topology_audit(vertices, faces) == expected


def test_opt_in_rejects_malformed_native_result() -> None:
    vertices, faces = _fixture("cube.stl")
    malformed = SimpleNamespace(
        triangle_surface_topology_audit=lambda *_: {
            "valid": True,
            "closed_oriented_manifold": True,
            "edge_count": "not-an-int",
            "component_count": 1,
            "euler_characteristic": 2,
        }
    )

    with (
        patch.dict(os.environ, {_TOPOLOGY_AUDIT_ENV: "1"}),
        patch("core.utils.native_extensions.load_native_metrics", return_value=malformed),
        pytest.raises(RuntimeError, match="invalid audit"),
    ):
        _surface_topology_audit(vertices, faces)


@pytest.mark.parametrize("name", ("cube.stl", "cylinder.stl", "sphere.stl"))
def test_opt_in_source_certificate_matches_python_reason_hashes_three_times(name: str) -> None:
    _native_audit()
    vertices, faces = _fixture(name)
    common = dict(
        source_vertices=vertices,
        source_faces=faces,
        candidate_vertices=vertices.copy(),
        candidate_faces=faces.copy(),
        face_provenance=_face_provenance(len(faces)),
    )
    with patch.dict(os.environ, {}, clear=True):
        expected = diagnose_native_tri_source_certificate(**common)
    with patch.dict(os.environ, {_TOPOLOGY_AUDIT_ENV: "1"}):
        actual = [diagnose_native_tri_source_certificate(**common) for _ in range(3)]

    assert actual == [expected, expected, expected]
