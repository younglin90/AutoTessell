"""C++23 compact boundary-layer front summary parity and ABI contracts."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

import core.layers.layer_front as subject
from core.generator.polymesh_writer import write_generic_polymesh
from core.layers.layer_front import build_layer_front, build_layer_front_summary
from core.layers.native_bl import BLConfig, generate_native_bl
from core.utils.native_extensions import load_native_bl


def _oracle(
    faces: list[list[int]],
    face_ids: list[int],
    points: np.ndarray,
) -> dict[str, object]:
    front = build_layer_front(faces, face_ids, points=points)
    first = next((edge for edge in front.edges if edge.is_nonmanifold), None)
    return {
        "n_faces": len(front.active_faces),
        "n_ignored": len(front.ignored_faces),
        "n_vertices": len(front.vertices),
        "n_edges": len(front.edges),
        "n_boundary_edges": front.n_boundary_edges,
        "n_nonmanifold_edges": front.n_nonmanifold_edges,
        "n_feature_vertices": front.n_feature_vertices,
        "n_blocked_vertices": front.n_blocked_vertices,
        "first_nonmanifold_edge": None if first is None else first.vertices,
        "first_nonmanifold_faces": () if first is None else first.faces,
    }


def _assert_parity(
    faces: list[list[int]],
    face_ids: list[int],
    points: np.ndarray,
) -> None:
    assert asdict(build_layer_front_summary(faces, face_ids, points=points)) == _oracle(
        faces,
        face_ids,
        points,
    )


def test_open_square_summary_matches_python_oracle() -> None:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
         [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    _assert_parity([[0, 1, 2], [0, 2, 3]], [0, 1], points)


def test_cube_feature_and_blocked_counts_match_python_oracle() -> None:
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
         [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
        dtype=np.float64,
    )
    faces = [
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
    ]
    _assert_parity(faces, list(range(len(faces))), points)


def test_nonmanifold_edge_preserves_lexicographic_edge_and_face_order() -> None:
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0],
         [0, 0, 1], [0, -1, 0]],
        dtype=np.float64,
    )
    faces: list[list[int]] = [[] for _ in range(10)]
    faces[9] = [0, 1, 2]
    faces[2] = [1, 0, 3]
    faces[7] = [0, 1, 4]
    summary = build_layer_front_summary(faces, [9, 2, 7], points=points)

    assert asdict(summary) == _oracle(faces, [9, 2, 7], points)
    assert summary.first_nonmanifold_edge == (0, 1)
    assert summary.first_nonmanifold_faces == (9, 2, 7)


def test_empty_and_degenerate_fronts_match_python_oracle() -> None:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        dtype=np.float64,
    )
    _assert_parity([], [], points)
    _assert_parity([[0, 1, 2]], [0], points)


def test_seeded_triangle_soup_matches_python_oracle() -> None:
    rng = np.random.default_rng(20260730)
    points = rng.normal(size=(160, 3))
    faces = [
        [int(value) for value in row]
        for row in np.vstack(
            [rng.choice(160, size=3, replace=False) for _ in range(320)]
        )
    ]
    face_ids = list(range(len(faces)))
    rng.shuffle(face_ids)
    _assert_parity(faces, face_ids, points)


def test_python_fallback_matches_native_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
        dtype=np.float64,
    )
    faces = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]
    native = build_layer_front_summary(faces, [0, 1, 2, 3], points=points)
    monkeypatch.setattr(subject, "load_native_bl", lambda: None)
    fallback = build_layer_front_summary(faces, [0, 1, 2, 3], points=points)
    assert fallback == native


def test_native_abi_rejects_invalid_inputs() -> None:
    native = load_native_bl()
    if native is None or not hasattr(native, "layer_front_summary"):
        pytest.skip("native_bl.layer_front_summary unavailable")
    face_ids = np.array([0], dtype=np.int64)
    triangles = np.array([[0, 1, 2]], dtype=np.int64)
    points = np.eye(3, dtype=np.float64)

    with pytest.raises((ValueError, RuntimeError)):
        native.layer_front_summary(face_ids, triangles[:, :2], points, 0.9)
    with pytest.raises((ValueError, RuntimeError)):
        native.layer_front_summary(face_ids, np.array([[0, 1, 3]]), points, 0.9)
    bad_points = points.copy()
    bad_points[0, 0] = np.nan
    with pytest.raises((ValueError, RuntimeError)):
        native.layer_front_summary(face_ids, triangles, bad_points, 0.9)
    with pytest.raises((ValueError, RuntimeError)):
        native.layer_front_summary(face_ids, triangles, points, np.nan)


def test_generate_native_bl_polymesh_hash_parity_with_python_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
        dtype=np.float64,
    )
    faces = [[[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]]
    native_case = tmp_path / "native"
    fallback_case = tmp_path / "fallback"
    for case in (native_case, fallback_case):
        write_generic_polymesh(
            points,
            faces,
            case,
            patch_name="wall",
            patch_type="wall",
        )
    for name, value in {
        "AUTO_TESSELL_BL_VD_ENABLE": "0",
        "AUTO_TESSELL_BL_ASPECT_ENFORCE": "0",
        "AUTO_TESSELL_BL_ANTI_INVERT_CAP": "0",
        "AUTO_TESSELL_BL_ANISO_SPLIT": "0",
        "AUTO_TESSELL_BL_ANISO_SPLIT_DIAG": "0",
        "AUTO_TESSELL_BL_INNER_SMOOTH": "0",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AUTO_TESSELL_BL_VD_FOR", raising=False)

    def config() -> BLConfig:
        return BLConfig(
            num_layers=2,
            first_thickness=0.01,
            growth_ratio=1.2,
            collision_safety=False,
            feature_lock=False,
            quality_check_enabled=False,
            backup_original=False,
        )

    native_result = generate_native_bl(native_case, config())
    assert native_result.success, native_result.message
    monkeypatch.setattr(subject, "load_native_bl", lambda: None)
    fallback_result = generate_native_bl(fallback_case, config())
    assert fallback_result.success, fallback_result.message

    for filename in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (
            native_case / "constant" / "polyMesh" / filename
        ).read_bytes() == (
            fallback_case / "constant" / "polyMesh" / filename
        ).read_bytes()
