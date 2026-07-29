"""Regressions for native BL front collision and selected-wall topology."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

import core.layers.native_bl as native_bl
from core.generator.polymesh_writer import write_generic_polymesh
from core.layers.native_bl import BLConfig, generate_native_bl


def _stable_bl_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_ENABLE", "0")
    monkeypatch.delenv("AUTO_TESSELL_BL_VD_FOR", raising=False)
    monkeypatch.setenv("AUTO_TESSELL_BL_ASPECT_ENFORCE", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANTI_INVERT_CAP", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT_DIAG", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_FRONT_STRICT", "0")


def _grid_points(side: int, z: float) -> np.ndarray:
    axis = np.arange(side, dtype=np.float64)
    xx, yy = np.meshgrid(axis, axis, indexing="xy")
    return np.column_stack(
        (xx.reshape(-1), yy.reshape(-1), np.full(side * side, z))
    )


def test_large_separated_opposite_fronts_do_not_collide_globally() -> None:
    lower = _grid_points(50, 0.0)
    upper = _grid_points(50, 100.0)
    points = np.vstack((lower, upper))
    normals = np.vstack(
        (
            np.tile([0.0, 0.0, 1.0], (len(lower), 1)),
            np.tile([0.0, 0.0, -1.0], (len(upper), 1)),
        )
    )

    collision = native_bl._nearby_opposite_front_mask(
        normals,
        points,
        search_radius=1.5,
    )

    assert collision.shape == (5000,)
    assert not collision.any()


def test_close_opposite_fronts_collide() -> None:
    lower = np.array(
        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0]],
        dtype=np.float64,
    )
    upper = lower + np.array([0.0, 0.0, 0.2])
    points = np.vstack((lower, upper))
    normals = np.vstack(
        (
            np.tile([0.0, 0.0, 1.0], (3, 1)),
            np.tile([0.0, 0.0, -1.0], (3, 1)),
        )
    )

    collision = native_bl._nearby_opposite_front_mask(
        normals,
        points,
        search_radius=0.3,
    )

    np.testing.assert_array_equal(collision, np.ones(6, dtype=bool))


def test_numpy_front_fallback_respects_pair_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    n_points = 129
    points = np.column_stack(
        (
            np.arange(n_points, dtype=np.float64) * 0.01,
            np.zeros(n_points),
            np.zeros(n_points),
        )
    )
    normals = np.zeros((n_points, 3), dtype=np.float64)
    normals[:, 2] = np.where(np.arange(n_points) % 2 == 0, 1.0, -1.0)
    pair_budget = 64
    largest_pair_block = 0
    real_einsum = native_bl.np.einsum

    def recording_einsum(
        subscripts: str,
        *operands: np.ndarray,
        **kwargs: Any,
    ) -> np.ndarray:
        nonlocal largest_pair_block
        if subscripts == "ijk,ijk->ij":
            largest_pair_block = max(
                largest_pair_block,
                int(operands[0].shape[0] * operands[0].shape[1]),
            )
        elif subscripts == "ik,jk->ij":
            largest_pair_block = max(
                largest_pair_block,
                int(operands[0].shape[0] * operands[1].shape[0]),
            )
        return real_einsum(subscripts, *operands, **kwargs)

    monkeypatch.setattr(native_bl.np, "einsum", recording_einsum)
    collision = native_bl._nearby_opposite_front_mask(
        normals,
        points,
        search_radius=10.0,
        prefer_kdtree=False,
        max_pair_entries=pair_budget,
    )

    assert collision.all()
    assert largest_pair_block <= pair_budget


def _write_nonmanifold_wall_case(case_dir: Path) -> dict[str, bytes]:
    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True)
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, -1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = [[0, 1, 2], [1, 0, 3], [0, 1, 4]]
    native_bl._write_points(poly_dir / "points", points)
    native_bl._write_faces(poly_dir / "faces", faces)
    native_bl._write_labels(
        poly_dir / "owner",
        np.zeros(3, dtype=np.int64),
        "owner",
    )
    native_bl._write_labels(
        poly_dir / "neighbour",
        np.empty(0, dtype=np.int64),
        "neighbour",
    )
    native_bl._write_boundary(
        poly_dir / "boundary",
        [{"name": "wall", "type": "wall", "nFaces": 3, "startFace": 0}],
    )
    return {path.name: path.read_bytes() for path in sorted(poly_dir.iterdir())}


def test_three_wall_triangles_sharing_edge_fail_without_output_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _write_nonmanifold_wall_case(tmp_path)
    _stable_bl_environment(monkeypatch)

    result = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            first_thickness=0.05,
            collision_safety=False,
            feature_lock=False,
            backup_original=True,
        ),
    )

    poly_dir = tmp_path / "constant" / "polyMesh"
    after = {path.name: path.read_bytes() for path in sorted(poly_dir.iterdir())}
    assert not result.success
    assert "non-manifold selected wall topology" in result.message
    assert "edge (0, 1)" in result.message
    assert "3 incident wall faces [0, 1, 2]" in result.message
    assert before == after
    assert not (tmp_path / "constant" / "polyMesh_pre_bl").exists()
    assert not (tmp_path / "native_bl_quality.json").exists()


def test_open_manifold_selected_wall_patch_remains_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    write_generic_polymesh(
        points,
        [
            [
                [0, 1, 2],
                [0, 3, 1],
                [1, 3, 2],
                [2, 3, 0],
            ]
        ],
        tmp_path,
        patch_name="wall",
        patch_type="wall",
    )
    _stable_bl_environment(monkeypatch)

    result = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            first_thickness=0.05,
            set_faces=[0, 1],
            collision_safety=False,
            feature_lock=False,
            quality_check_enabled=False,
            backup_original=False,
        ),
    )

    assert result.success, result.message
    assert result.n_wall_faces == 2
    assert result.n_prism_cells == 2
