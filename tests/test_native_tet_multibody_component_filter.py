from __future__ import annotations

import numpy as np
import trimesh

from core.preprocessor.pipeline import Preprocessor


def _box(extents: tuple[float, float, float], translation: tuple[float, float, float]) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(translation)
    return mesh


def test_final_validate_preserves_comparable_disjoint_bodies() -> None:
    mesh = trimesh.util.concatenate(
        [
            _box((1.0, 1.0, 1.0), (0.0, 0.0, 0.0)),
            _box((1.0, 1.0, 1.0), (2.0, 0.0, 0.0)),
        ],
    )

    validated = Preprocessor()._final_validate(mesh)
    components = validated.split(only_watertight=False)

    assert len(components) == 2
    np.testing.assert_allclose(sorted(float(c.area) for c in components), [6.0, 6.0])


def test_final_validate_discards_small_relative_fragment() -> None:
    mesh = trimesh.util.concatenate(
        [
            _box((1.0, 1.0, 1.0), (0.0, 0.0, 0.0)),
            _box((0.05, 0.05, 0.05), (2.0, 0.0, 0.0)),
        ],
    )

    validated = Preprocessor()._final_validate(mesh)
    components = validated.split(only_watertight=False)

    assert len(components) == 1
    np.testing.assert_allclose(float(components[0].area), 6.0)
