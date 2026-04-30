"""native_ai skeleton unit tests."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.generator.native_ai import (
    AIVolumeConfig,
    AIVolumeResult,
    generate_native_ai_volume,
)


def _unit_cube_mesh() -> tuple[np.ndarray, np.ndarray]:
    V = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
         [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
        dtype=np.float64,
    )
    F = np.array(
        [[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
         [0, 5, 1], [0, 4, 5], [1, 6, 2], [1, 5, 6],
         [2, 7, 3], [2, 6, 7], [3, 4, 0], [3, 7, 4]],
        dtype=np.int64,
    )
    return V, F


def test_native_ai_config_defaults():
    cfg = AIVolumeConfig()
    assert cfg.mesh_type == "tet"
    assert cfg.quality_level == "standard"
    assert cfg.seed_density == 8
    assert cfg.enable_bl is True
    assert cfg.bl_num_layers == 3
    assert cfg.ai_smoothing is False
    assert cfg.ai_surface_repair is False
    assert cfg.ai_collision_predict is False


def test_native_ai_tet_dispatch():
    V, F = _unit_cube_mesh()
    with tempfile.TemporaryDirectory() as td:
        cfg = AIVolumeConfig(mesh_type="tet", enable_bl=False)
        r = generate_native_ai_volume(V, F, Path(td) / "c", cfg)
        assert isinstance(r, AIVolumeResult)
        assert r.success is True
        assert r.mesh_type == "tet"
        assert r.backend == "native_tet"
        assert r.n_cells > 0
        assert r.grade in ("A", "B", "C", "D")
        assert r.elapsed > 0
        # AI not yet applied
        assert r.ai_applied == {
            "smoothing": False,
            "surface_repair": False,
            "collision_predict": False,
        }


def test_native_ai_hex_dispatch():
    V, F = _unit_cube_mesh()
    with tempfile.TemporaryDirectory() as td:
        cfg = AIVolumeConfig(mesh_type="hex", seed_density=4, enable_bl=False)
        r = generate_native_ai_volume(V, F, Path(td) / "c", cfg)
        assert isinstance(r, AIVolumeResult)
        assert r.success is True
        assert r.mesh_type == "hex"
        assert r.backend == "native_hex"
        assert r.n_cells > 0


def test_native_ai_poly_dispatch():
    V, F = _unit_cube_mesh()
    with tempfile.TemporaryDirectory() as td:
        cfg = AIVolumeConfig(mesh_type="poly", seed_density=4, enable_bl=False)
        r = generate_native_ai_volume(V, F, Path(td) / "c", cfg)
        assert isinstance(r, AIVolumeResult)
        assert r.mesh_type == "poly"
        assert r.backend == "native_poly"


def test_native_ai_unknown_mesh_type():
    V, F = _unit_cube_mesh()
    with tempfile.TemporaryDirectory() as td:
        cfg = AIVolumeConfig(mesh_type="xxx", enable_bl=False)  # type: ignore[arg-type]
        r = generate_native_ai_volume(V, F, Path(td) / "c", cfg)
        assert r.success is False
        assert "unknown mesh_type" in r.message


def test_native_ai_with_bl_does_not_crash():
    V, F = _unit_cube_mesh()
    with tempfile.TemporaryDirectory() as td:
        cfg = AIVolumeConfig(mesh_type="tet", enable_bl=True, bl_num_layers=2)
        r = generate_native_ai_volume(V, F, Path(td) / "c", cfg)
        # success may be True (tet OK) — BL might fail on tiny cube, but
        # generate_native_ai_volume catches BL exceptions and continues.
        assert r.mesh_type == "tet"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
