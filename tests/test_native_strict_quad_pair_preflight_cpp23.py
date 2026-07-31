"""L0/L1 contracts for the fixed-vertex strict-quad pair preflight."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
import trimesh

from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_quad.strict_pair_preflight import (
    diagnose_strict_quad_pair_preflight,
    strict_quad_pair_preflight_cpp23_enabled,
)

_ENV = "AUTO_TESSELL_STRICT_QUAD_PREFLIGHT_CPP23"


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


def _cube() -> (
    tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[int], list[int]]
):
    vertices = np.array(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 1.0),
            (1.0, 1.0, 1.0),
            (0.0, 1.0, 1.0),
        ),
        dtype=np.float64,
    )
    source_quads = (
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    )
    triangles = np.asarray(
        [
            face
            for quad in source_quads
            for face in ((quad[0], quad[1], quad[2]), (quad[0], quad[2], quad[3]))
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
    quad_patches = list(range(6))
    return vertices, triangles, quads, provenance, features, source_patches, quad_patches


def _report(
    vertices: np.ndarray,
    triangles: np.ndarray,
    quads: np.ndarray,
    provenance: np.ndarray,
    features: np.ndarray,
    source_patches: object,
    quad_patches: object,
    *,
    source_groups: object | None = None,
    quad_groups: object | None = None,
    candidate_vertices: np.ndarray | None = None,
    candidate_triangles: np.ndarray | None = None,
):
    if source_groups is None:
        source_groups = AuthoritativePhysicalGroupMapping(
            tuple("group" for _ in range(len(triangles))),
            True,
        )
    if quad_groups is None:
        quad_groups = ["group"] * len(quads)
    return diagnose_strict_quad_pair_preflight(
        vertices,
        vertices.copy() if candidate_vertices is None else candidate_vertices,
        triangles,
        _empty_triangles() if candidate_triangles is None else candidate_triangles,
        quads,
        provenance,
        features,
        source_patch_ids=source_patches,
        candidate_quad_patch_ids=quad_patches,
        source_physical_groups=source_groups,
        candidate_quad_physical_groups=quad_groups,
    )


def _native() -> object:
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "strict_quad_pair_preflight"):
        pytest.skip("native strict_quad_pair_preflight is not built")
    return native


def test_l0_square_accepts_only_exact_fixed_vertex_pair() -> None:
    vertices, triangles, quads, provenance, features = _square()
    reports = [
        _report(vertices, triangles, quads, provenance, features, ["wall", "wall"], ["wall"])
        for _ in range(3)
    ]

    assert reports == [reports[0]] * 3
    report = reports[0]
    assert report.accepted is True
    assert report.rejection_reasons == ()
    assert dict(report.structural_facts) == {
        "valid": True,
        "coordinates_finite": True,
        "vertices_exact": True,
        "source_triangles_non_degenerate": True,
        "candidate_triangles_empty": True,
        "quads_degree_four": True,
        "provenance_complete": True,
        "pair_quads_exact": True,
        "pairs_coplanar": True,
        "source_manifold": True,
        "quad_manifold": True,
        "boundary_equal": True,
        "features_preserved": True,
        "source_component_count": 1,
        "quad_component_count": 1,
        "source_euler_characteristic": 1,
        "quad_euler_characteristic": 1,
    }


@pytest.mark.parametrize(
    "kind", ("triangles", "quad_order", "provenance", "vertex", "feature", "patch", "noncoplanar")
)
def test_l0_rejects_every_unsafe_pair_contract(kind: str) -> None:
    vertices, triangles, quads, provenance, features = _square()
    kwargs: dict[str, object] = {}
    if kind == "triangles":
        kwargs["candidate_triangles"] = triangles[:1].copy()
    elif kind == "quad_order":
        quads = quads[:, ::-1].copy()
    elif kind == "provenance":
        provenance = np.array(((0, 0),), dtype=np.int64)
    elif kind == "vertex":
        candidate = vertices.copy()
        candidate[0, 0] = 0.25
        kwargs["candidate_vertices"] = candidate
    elif kind == "feature":
        features = np.array(((0, 2),), dtype=np.int64)
    elif kind == "noncoplanar":
        vertices = vertices.copy()
        vertices[3, 2] = 0.5
    else:
        kwargs["quad_patches"] = ["different"]
    report = _report(
        vertices,
        triangles,
        quads,
        provenance,
        features,
        ["wall", "wall"],
        kwargs.pop("quad_patches", ["wall"]),
        **kwargs,
    )
    assert report.accepted is False
    assert report.rejection_reasons


def test_l0_default_off_never_loads_native_audit() -> None:
    vertices, triangles, quads, provenance, features = _square()
    with (
        patch.dict(os.environ, {}, clear=True),
        patch(
            "core.utils.native_extensions.load_native_metrics",
            side_effect=AssertionError("default-OFF selected native strict-quad audit"),
        ),
    ):
        assert strict_quad_pair_preflight_cpp23_enabled() is False
        assert _report(vertices, triangles, quads, provenance, features, [0, 0], [0]).accepted


def test_l0_native_abi_parity_and_malformed_result_fail_closed() -> None:
    native = _native()
    vertices, triangles, quads, provenance, features = _square()
    expected = _report(vertices, triangles, quads, provenance, features, [0, 0], [0])
    native_args = (
        vertices,
        vertices.copy(),
        triangles,
        _empty_triangles(),
        quads,
        provenance,
        features,
    )
    direct = native.strict_quad_pair_preflight(*native_args)  # type: ignore[attr-defined]
    assert direct == dict(expected.structural_facts)
    with pytest.raises((TypeError, ValueError), match="C-contiguous float64"):
        native.strict_quad_pair_preflight(  # type: ignore[attr-defined]
            vertices.astype(np.float32), *native_args[1:]
        )
    with pytest.raises((TypeError, ValueError), match="C-contiguous int64"):
        native.strict_quad_pair_preflight(  # type: ignore[attr-defined]
            vertices, vertices, triangles.astype(np.int32), *native_args[3:]
        )
    with pytest.raises((TypeError, ValueError), match="C-contiguous float64"):
        native.strict_quad_pair_preflight(  # type: ignore[attr-defined]
            vertices[:, ::-1], *native_args[1:]
        )
    malformed = SimpleNamespace(strict_quad_pair_preflight=lambda *_: {"valid": True})
    with (
        patch.dict(os.environ, {_ENV: "1"}),
        patch("core.utils.native_extensions.load_native_metrics", return_value=malformed),
        pytest.raises(RuntimeError, match="malformed audit"),
    ):
        _report(vertices, triangles, quads, provenance, features, [0, 0], [0])


def test_l1_cube_off_on_has_identical_strict_pair_evidence() -> None:
    _native()
    vertices, triangles, quads, provenance, features, source_patches, quad_patches = _cube()
    with patch.dict(os.environ, {}, clear=True):
        expected = _report(
            vertices, triangles, quads, provenance, features, source_patches, quad_patches
        )
    with patch.dict(os.environ, {_ENV: "1"}):
        actual = [
            _report(vertices, triangles, quads, provenance, features, source_patches, quad_patches)
            for _ in range(3)
        ]
    assert expected.accepted is True
    assert actual == [expected, expected, expected]
    facts = dict(expected.structural_facts)
    assert (facts["source_component_count"], facts["source_euler_characteristic"]) == (1, 2)
    assert len(features) == 12


@pytest.mark.parametrize("fixture", ("cylinder.stl", "sphere.stl"))
def test_l1_curved_source_has_no_fixed_vertex_strict_pair_product(fixture: str) -> None:
    _native()
    mesh = trimesh.load(str(Path(__file__).parent / "benchmarks" / fixture), force="mesh")
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    triangles = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    arguments = (
        vertices,
        triangles,
        np.empty((0, 4), dtype=np.int64),
        np.empty((0, 2), dtype=np.int64),
        np.empty((0, 2), dtype=np.int64),
        [None] * len(triangles),
        [],
    )
    with patch.dict(os.environ, {}, clear=True):
        expected = _report(*arguments)
    with patch.dict(os.environ, {_ENV: "1"}):
        actual = [_report(*arguments) for _ in range(3)]
    assert expected.accepted is False
    assert "valid" in expected.rejection_reasons
    assert actual == [expected, expected, expected]
