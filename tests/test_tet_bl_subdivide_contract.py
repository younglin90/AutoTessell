"""Focused result-contract tests for tet boundary-layer subdivision."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

import core.layers.tet_bl_subdivide as subject

MeshData = tuple[np.ndarray, list[list[int]], list[int], list[int]]


def _tet_mesh() -> MeshData:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    faces = [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
    return points, faces, [0] * len(faces), []


def _hex_mesh(vertex_offset: int = 0, cell_id: int = 0) -> MeshData:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
            [0.0, 1.0, 1.0],
        ]
    )
    faces = [
        [0, 3, 2, 1],
        [4, 5, 6, 7],
        [0, 1, 5, 4],
        [1, 2, 6, 5],
        [2, 3, 7, 6],
        [3, 0, 4, 7],
    ]
    shifted = [[vertex_offset + vertex for vertex in face] for face in faces]
    return points, shifted, [cell_id] * len(shifted), []


def _prism_mesh() -> MeshData:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 0.2],
            [1.0, 0.0, 0.2],
            [0.0, 1.0, 0.2],
        ]
    )
    faces = [
        [0, 2, 1],
        [3, 4, 5],
        [0, 1, 4, 3],
        [1, 2, 5, 4],
        [2, 0, 3, 5],
    ]
    return points, faces, [0] * len(faces), []


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mesh: MeshData,
    writes: dict[str, Any] | None = None,
) -> subject.TetSubdivResult:
    points, faces, owner, neighbour = mesh
    poly_dir = tmp_path / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True)
    (poly_dir / "faces").touch()

    boundary: list[dict[str, Any]] = [
        {"name": "wall", "type": "wall", "nFaces": len(faces), "startFace": 0}
    ]
    monkeypatch.setattr(subject, "parse_foam_points", lambda _path: points.tolist())
    monkeypatch.setattr(subject, "parse_foam_faces", lambda _path: faces)
    monkeypatch.setattr(
        subject,
        "parse_foam_labels",
        lambda path: owner if path.name == "owner" else neighbour,
    )
    monkeypatch.setattr(subject, "parse_foam_boundary", lambda _path: boundary)

    if writes is None:
        def unexpected_write(*_args: object, **_kwargs: object) -> None:
            pytest.fail("contract rejection/no-op must not rewrite polyMesh")

        monkeypatch.setattr(subject, "_write_points", unexpected_write)
        monkeypatch.setattr(subject, "_write_faces", unexpected_write)
        monkeypatch.setattr(subject, "_write_labels", unexpected_write)
        monkeypatch.setattr(subject, "_write_boundary", unexpected_write)
    else:
        monkeypatch.setattr(
            subject, "_write_points", lambda _path, data: writes.update(points=data)
        )
        monkeypatch.setattr(
            subject, "_write_faces", lambda _path, data: writes.update(faces=data)
        )
        monkeypatch.setattr(
            subject,
            "_write_labels",
            lambda path, data, _name: writes.setdefault("labels", {}).update(
                {path.name: data}
            ),
        )
        monkeypatch.setattr(
            subject,
            "_write_boundary",
            lambda _path, data: writes.update(boundary=data),
        )
    return subject.subdivide_prism_layers_to_tet(tmp_path, backup_original=False)


def test_all_tet_input_is_successful_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(tmp_path, monkeypatch, _tet_mesh())

    assert result.success
    assert result.subdivision_applied
    assert result.n_prism_before == 0
    assert result.n_tet_added == 0
    assert "이미 전체 tet" in result.message


def test_no_prism_hex_input_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run(tmp_path, monkeypatch, _hex_mesh())

    assert not result.success
    assert not result.subdivision_applied
    assert result.n_prism_before == 0
    assert "prism cell 없음" in result.message
    assert "non-tet cell 잔존" in result.message
    assert "count=1" in result.message


def test_prism_with_non_tet_bulk_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prism_points, prism_faces, prism_owner, _ = _prism_mesh()
    hex_points, hex_faces, hex_owner, _ = _hex_mesh(vertex_offset=6, cell_id=1)
    mesh = (
        np.vstack((prism_points, hex_points + np.array([3.0, 0.0, 0.0]))),
        prism_faces + hex_faces,
        prism_owner + hex_owner,
        [],
    )

    result = _run(tmp_path, monkeypatch, mesh)

    assert not result.success
    assert not result.subdivision_applied
    assert result.n_prism_before == 1
    assert result.n_tet_added == 0
    assert "non-tet bulk cell 잔존" in result.message
    assert "cells=1" in result.message


def test_closed_prism_boundary_children_inherit_wall_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writes: dict[str, Any] = {}
    mesh = _prism_mesh()
    result = _run(tmp_path, monkeypatch, mesh, writes)

    assert result.success
    assert result.subdivision_applied
    assert result.n_prism_before == 1
    assert result.n_tet_added == 3
    boundary = writes["boundary"]
    assert [patch["name"] for patch in boundary] == ["wall"]
    assert boundary[0]["nFaces"] == 8
    assert "bl_subdiv_side" not in {patch["name"] for patch in boundary}

    start = boundary[0]["startFace"]
    wall_faces = writes["faces"][start : start + boundary[0]["nFaces"]]
    side_parents = [set(face) for face in mesh[1] if len(face) == 4]
    side_children = [
        face
        for face in wall_faces
        if any(set(face) < parent for parent in side_parents)
    ]
    assert len(side_children) == 6


def test_boundary_child_with_conflicting_parent_patches_is_ambiguous() -> None:
    patch_index, conflicting_patches = subject._match_boundary_patch(
        (0, 1, 2),
        {},
        [
            (frozenset({0, 1, 2, 3}), 1),
            (frozenset({0, 1, 2, 4}), 0),
        ],
    )

    assert patch_index is None
    assert conflicting_patches == (0, 1)


def test_closed_input_with_truly_unmatched_face_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_match = subject._match_boundary_patch
    unmatched_injected = False

    def force_one_child_unmatched(
        face_key: tuple[int, ...],
        exact_patches: dict[tuple[int, ...], set[int]],
        polygon_parents: list[tuple[frozenset[int], int]],
    ) -> tuple[int | None, tuple[int, ...]]:
        nonlocal unmatched_injected
        match = original_match(face_key, exact_patches, polygon_parents)
        if not unmatched_injected and face_key not in exact_patches and match[0] is not None:
            unmatched_injected = True
            return None, ()
        return match

    monkeypatch.setattr(subject, "_match_boundary_patch", force_one_child_unmatched)
    result = _run(tmp_path, monkeypatch, _prism_mesh())

    assert unmatched_injected
    assert not result.success
    assert not result.subdivision_applied
    assert result.n_prism_before == 1
    assert result.n_tet_added == 0
    assert "closed boundary reconstruction 실패" in result.message
    assert "unmatched faces=1" in result.message
    assert "bl_subdiv_side" not in result.message
