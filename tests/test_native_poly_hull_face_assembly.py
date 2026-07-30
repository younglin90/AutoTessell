"""Parity and fail-closed checks for C++23 dual hull-face assembly."""

from __future__ import annotations

import hashlib
import os
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.generator.native_poly import dual
from core.generator.native_tet.mesher import generate_native_tet
from core.utils import native_extensions

_FROZEN_SPHERE_PRIMAL_DIGEST = (
    "84856e4ffa7654beb46a0f894baa05d3a314508501d6d470d9be26de38ed7d6c"
)
_FROZEN_SPHERE_POLYMESH_DIGEST = (
    "c972331abbb502f25942adbf69143478f600339330d3f0def8064abc8eb4806a"
)
_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")


def _native_or_skip() -> Any:
    native = native_extensions.load_native_polymesh()
    if native is None or not hasattr(native, "assemble_dual_hull_faces"):
        pytest.skip("native dual hull-face assembly kernel is not built")
    return native


def _assembly_fixture() -> tuple[np.ndarray, ...]:
    scipy = pytest.importorskip("scipy.spatial")
    first = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        dtype=np.float64,
    )
    second = np.asarray(
        (
            (2.0, 0.0, 0.0),
            (3.0, 0.0, 0.0),
            (3.0, 1.0, 0.0),
            (2.0, 1.0, 0.0),
            (2.0, 0.0, 1.0),
            (3.0, 0.0, 1.0),
            (3.0, 1.0, 1.0),
            (2.0, 1.0, 1.0),
        ),
        dtype=np.float64,
    )
    hulls = [scipy.ConvexHull(first), scipy.ConvexHull(second)]
    points = np.ascontiguousarray(np.concatenate((first, second)), dtype=np.float64)
    point_offsets = np.asarray((0, len(first), len(first) + len(second)), dtype=np.int64)
    simplices = np.ascontiguousarray(
        np.concatenate([hull.simplices for hull in hulls]), dtype=np.int64
    )
    hull_offsets = np.asarray(
        (0, len(hulls[0].simplices), sum(len(hull.simplices) for hull in hulls)),
        dtype=np.int64,
    )
    equations = np.ascontiguousarray(
        np.concatenate([hull.equations for hull in hulls]), dtype=np.float64
    )
    n_tet_points = np.asarray((2, 4), dtype=np.int64)
    labels = np.asarray((-1, -1, 0, 0, -1, -1, -1, -1, 1, 1, 2, 2), dtype=np.int64)
    seed = np.asarray(((-0.0, 0.0, 0.0),), dtype=np.float64)
    return (
        seed,
        points,
        point_offsets,
        simplices,
        hull_offsets,
        equations,
        n_tet_points,
        labels,
    )


def _corrected_native(native: Any, inputs: tuple[np.ndarray, ...]) -> tuple[np.ndarray, ...]:
    raw = native.assemble_dual_hull_faces(*inputs)
    (
        accepted,
        reason,
        points,
        face_offsets,
        face_indices,
        cell_face_offsets,
        cap_flags,
        label_ids,
        ambiguity_flags,
    ) = dual._validate_dual_hull_assembly_output(
        raw,
        n_cells=len(inputs[6]),
        n_source_labels=3,
    )
    assert accepted, reason
    corrected_indices = dual._repair_native_ambiguous_face_order(
        inputs[1],
        inputs[2],
        inputs[3],
        inputs[4],
        inputs[5],
        points,
        face_offsets,
        face_indices,
        ambiguity_flags,
    )
    return (
        points,
        face_offsets,
        corrected_indices,
        cell_face_offsets,
        cap_flags,
        label_ids,
    )


def test_native_hull_faces_match_independent_python_oracle() -> None:
    native = _native_or_skip()
    inputs = _assembly_fixture()
    expected = dual._assemble_dual_hull_faces_python(*inputs)
    actual = _corrected_native(native, inputs)

    for actual_array, expected_array in zip(actual, expected, strict=True):
        assert actual_array.flags.c_contiguous
        assert actual_array.flags.owndata or actual_array.base is not None
        assert np.array_equal(actual_array, expected_array)
    assert np.signbit(actual[0][0, 0])
    assert dual._dual_hull_assembly_digest(actual) == dual._dual_hull_assembly_digest(expected)


def test_native_hull_faces_three_run_determinism() -> None:
    native = _native_or_skip()
    inputs = _assembly_fixture()
    results = [_corrected_native(native, inputs) for _ in range(3)]
    digests = [dual._dual_hull_assembly_digest(result) for result in results]
    assert len(set(digests)) == 1


def test_native_hull_faces_strict_arrays_and_malformed_contract() -> None:
    native = _native_or_skip()
    inputs = _assembly_fixture()
    with pytest.raises(TypeError):
        native.assemble_dual_hull_faces(inputs[0].astype(np.float32), *inputs[1:])

    malformed_offsets = inputs[2].copy()
    malformed_offsets[-1] -= 1
    with pytest.raises(ValueError, match="offsets must end"):
        native.assemble_dual_hull_faces(inputs[0], inputs[1], malformed_offsets, *inputs[3:])

    malformed_simplices = inputs[3].copy()
    malformed_simplices[0, 0] = len(inputs[1])
    with pytest.raises(IndexError, match="local point index is out of bounds"):
        native.assemble_dual_hull_faces(
            inputs[0], inputs[1], inputs[2], malformed_simplices, *inputs[4:]
        )

    malformed_labels = inputs[7].copy()
    malformed_labels[0] = -2
    with pytest.raises(ValueError, match="label ids must be -1 or nonnegative"):
        native.assemble_dual_hull_faces(*inputs[:7], malformed_labels)


def test_python_hull_abi_preflight_checks_count_overflow() -> None:
    with pytest.raises(OverflowError, match="size multiplication overflow"):
        dual._checked_array_product(sys.maxsize, 3, "synthetic")


def _snapshot(case_dir: Path) -> dict[str, tuple[str, bytes]]:
    result: dict[str, tuple[str, bytes]] = {}
    for path in sorted(item for item in case_dir.rglob("*") if item.is_file()):
        payload = path.read_bytes()
        result[str(path.relative_to(case_dir))] = (
            hashlib.sha256(payload).hexdigest(),
            payload,
        )
    return result


def _typed_array_digest(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        values = np.ascontiguousarray(array)
        digest.update(str(values.dtype).encode())
        digest.update(repr(values.shape).encode())
        digest.update(values.tobytes())
    return digest.hexdigest()


def _polymesh_snapshot(case_dir: Path) -> dict[str, bytes]:
    mesh_dir = case_dir / "constant" / "polyMesh"
    return {name: (mesh_dir / name).read_bytes() for name in _POLYMESH_FILES}


def _case_digest(case_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in case_dir.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(case_dir)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _without_hull_assembly_symbol(native: Any) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        **{
            name: getattr(native, name)
            for name in dir(native)
            if name != "assemble_dual_hull_faces" and not name.startswith("__")
        }
    )


def test_frozen_sphere_native_and_python_assembly_are_byte_exact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Executable promotion gate for the measured sphere primal and polyMesh."""
    native = _native_or_skip()
    assert hasattr(native, "assemble_dual_hull_faces")

    # Ambient campaign toggles must not silently select a different primal.
    for name in tuple(os.environ):
        if name.startswith("AUTO_TESSELL_"):
            monkeypatch.delenv(name, raising=False)

    sphere = Path(__file__).parent / "benchmarks" / "sphere.stl"
    surface = read_stl(sphere)
    primal = generate_native_tet(
        surface.vertices,
        surface.faces,
        tmp_path / "primal",
        target_edge_length=None,
        seed_density=8,
        enable_auto_fix_input=True,
        enable_phase_a=True,
        enable_bsp_insertion=False,
        enable_edge_recovery=False,
        enable_phase_b=False,
        enable_phase_c=False,
        target_cells=None,
        min_final_vertices=None,
        use_adaptive_sizing=False,
        use_anisotropic_metric=False,
        enable_amips_smooth=False,
        enable_chunked_delaunay=True,
        enable_edge_steiner=False,
        enable_cdt_recovery=False,
        enable_boundary_clip=False,
        use_torch_amips=False,
        enable_stellar_split=False,
    )
    assert primal.success, primal.message
    assert primal.tet_points is not None and primal.tets is not None
    points = np.ascontiguousarray(primal.tet_points, dtype=np.float64)
    tets = np.ascontiguousarray(primal.tets, dtype=np.int64)
    assert _typed_array_digest(points, tets) == _FROZEN_SPHERE_PRIMAL_DIGEST

    native_dir = tmp_path / "native"
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: native)
    native_result = dual.tet_to_poly_dual(points.copy(), tets.copy(), native_dir)

    python_dir = tmp_path / "python"
    python_only = _without_hull_assembly_symbol(native)
    assert not hasattr(python_only, "assemble_dual_hull_faces")
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: python_only)
    python_result = dual.tet_to_poly_dual(points.copy(), tets.copy(), python_dir)

    for result in (native_result, python_result):
        assert result.success, result.message
        assert result.n_cells == 669
        assert result.n_points == 5473
        assert result.invalid_star_cells == 0
        assert result.invalid_star_subtets == 0
    native_files = _polymesh_snapshot(native_dir)
    assert native_files == _polymesh_snapshot(python_dir)
    assert _case_digest(native_dir) == _FROZEN_SPHERE_POLYMESH_DIGEST
    assert _case_digest(python_dir) == _FROZEN_SPHERE_POLYMESH_DIGEST

    repeat_dir = tmp_path / "native_repeat"
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: native)
    repeat_result = dual.tet_to_poly_dual(points.copy(), tets.copy(), repeat_dir)
    assert repeat_result.success, repeat_result.message
    assert repeat_result.n_cells == 669
    assert repeat_result.n_points == 5473
    assert repeat_result.invalid_star_cells == 0
    assert repeat_result.invalid_star_subtets == 0
    assert _polymesh_snapshot(repeat_dir) == native_files
    assert _case_digest(repeat_dir) == _FROZEN_SPHERE_POLYMESH_DIGEST


def _small_primal() -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.3, 0.3, 1.0),
            (0.3, 0.3, -1.0),
        ),
        dtype=np.float64,
    )
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)
    return points, tets


def test_native_refusal_uses_exact_legacy_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    native = _native_or_skip()

    def refuse(*_args: object) -> tuple[object, ...]:
        return (
            False,
            "synthetic_refusal",
            np.empty((0, 3), dtype=np.float64),
            np.asarray((0,), dtype=np.int64),
            np.empty(0, dtype=np.int64),
            np.asarray((0,), dtype=np.int64),
            np.empty(0, dtype=np.uint8),
            np.empty(0, dtype=np.int64),
            np.empty(0, dtype=np.uint8),
        )

    fallback = types.SimpleNamespace(
        **{
            name: getattr(native, name)
            for name in (
                "build_tet_incidence_maps",
                "face_flip_mask",
                "face_plane_geometry",
                "star_validity",
            )
        }
    )
    refusing = types.SimpleNamespace(**vars(fallback), assemble_dual_hull_faces=refuse)
    points, tets = _small_primal()

    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: refusing)
    refused_dir = tmp_path / "refused"
    refused_result = dual.tet_to_poly_dual(points, tets, refused_dir)

    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: fallback)
    legacy_dir = tmp_path / "legacy"
    legacy_result = dual.tet_to_poly_dual(points, tets, legacy_dir)

    assert refused_result.success and legacy_result.success
    assert _snapshot(refused_dir) == _snapshot(legacy_dir)


def test_stale_native_hull_abi_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    native = _native_or_skip()
    stale = types.SimpleNamespace(
        build_tet_incidence_maps=native.build_tet_incidence_maps,
        assemble_dual_hull_faces=lambda *_args: None,
    )
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: stale)
    points, tets = _small_primal()

    result = dual.tet_to_poly_dual(points, tets, tmp_path / "stale")

    assert not result.success
    assert "stale ABI payload" in result.message
