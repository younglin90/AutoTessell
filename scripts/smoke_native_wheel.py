#!/usr/bin/env python3
"""Smoke-test the installed first-party native wheel from outside the repo."""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.metadata
from pathlib import Path

import numpy as np

EXPECTED_MODULES = {
    "native_bl",
    "native_hex_quality",
    "native_metrics",
    "native_polymesh",
    "native_snap",
    "native_surface_padding",
    "native_tet_predicates",
    "native_tet_qopt",
}
FORBIDDEN_MODULES = {"cfmesh_native", "cinolib_hex", "ftetwild", "robusthex"}


def _extension_stem(path: Path) -> str | None:
    name = path.name
    for suffix in importlib.machinery.EXTENSION_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def _smoke_kernels(modules: dict[str, object]) -> None:
    metrics = modules["native_metrics"]
    centres, _, areas = metrics.compute_face_geometry(
        np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        [[0, 1, 2]],
    )
    assert np.asarray(centres).shape == (1, 3)
    np.testing.assert_allclose(np.asarray(areas), [0.5])

    native_bl = modules["native_bl"]
    mask = native_bl.nearby_opposite_front_mask(
        np.asarray([[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]),
        np.asarray([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0]]),
        0.2,
        -0.5,
    )
    assert np.asarray(mask, dtype=bool).tolist() == [True, True]

    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    cell_faces = [[[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]]
    topology = modules["native_polymesh"].build_topology(vertices, cell_faces, 1e-30)
    assert int(topology[5]) == 1

    first = np.asarray([[0.0, 0.0, 0.0]])
    second = np.asarray([[1.0, 0.0, 0.0]])
    third = np.asarray([[0.0, 1.0, 0.0]])
    best, distance2, valid = modules["native_snap"].closest_triangle_candidates(
        np.asarray([[0.25, 0.25, 1.0]]),
        first,
        second,
        third,
        np.asarray([[0]], dtype=np.int64),
    )
    np.testing.assert_allclose(np.asarray(best), [[0.25, 0.25, 0.0]])
    np.testing.assert_allclose(np.asarray(distance2), [1.0])
    assert np.asarray(valid).tolist() == [True]

    padded = modules["native_surface_padding"].pad_axis_aligned_surface_to_volume(
        vertices[:3], [[0, 1, 2]], 1, 1e-9
    )
    assert int(padded["report"]["prism_cells"]) == 1

    cube_points = np.asarray(
        [
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0], [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0], [0.0, 1.0, 1.0],
        ]
    )
    primitives = modules["native_hex_quality"].hex_quality_primitives(
        cube_points, np.asarray([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    )
    assert int(primitives[0]) == 6
    assert all(np.asarray(primitives[index]).shape == (1,) for index in (1, 2, 3))
    assert np.isfinite(float(primitives[4]))

    signs = modules["native_tet_predicates"].orient3d_signs(vertices.reshape(1, 4, 3))
    assert abs(int(np.asarray(signs)[0])) == 1

    comparison = modules["native_tet_qopt"].compare_quality_vectors(
        np.asarray([0.1, 0.3]), np.asarray([0.2, 0.3])
    )
    assert int(comparison) == 1


def main() -> int:
    distribution = importlib.metadata.distribution("auto-tessell")
    installed_extensions = {
        stem
        for item in distribution.files or ()
        if (stem := _extension_stem(Path(str(item)))) is not None
    }
    assert installed_extensions == EXPECTED_MODULES, (
        f"installed native module set mismatch: {sorted(installed_extensions)}"
    )
    assert not installed_extensions.intersection(FORBIDDEN_MODULES)

    modules: dict[str, object] = {}
    for name in sorted(EXPECTED_MODULES):
        module = importlib.import_module(name)
        path = Path(str(module.__file__)).resolve()
        assert _extension_stem(path) == name, f"{name} is not a native extension: {path}"
        modules[name] = module
    _smoke_kernels(modules)
    print("native-wheel-smoke: modules=8 kernels=8 forbidden=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
