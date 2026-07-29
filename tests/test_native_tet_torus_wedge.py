"""Circular torus structured-wedge rescue regressions."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.evaluator.native_checker import NativeMeshChecker
from core.generator.native_tet.torus_wedge import build_torus_wedges
from core.pipeline.orchestrator import PipelineOrchestrator
from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels


def _torus_surface(center_x: float, n_major: int = 12, n_minor: int = 8):
    points = []
    faces = []
    for major in range(n_major):
        theta = 2.0 * np.pi * major / n_major
        for minor in range(n_minor):
            phi = 2.0 * np.pi * minor / n_minor
            points.append(
                [
                    center_x + (2.0 + 0.5 * np.cos(phi)) * np.cos(theta),
                    (2.0 + 0.5 * np.cos(phi)) * np.sin(theta),
                    0.5 * np.sin(phi),
                ]
            )
    for major in range(n_major):
        next_major = (major + 1) % n_major
        for minor in range(n_minor):
            next_minor = (minor + 1) % n_minor
            a = major * n_minor + minor
            b = next_major * n_minor + minor
            c = next_major * n_minor + next_minor
            d = major * n_minor + next_minor
            faces.extend(([a, b, c], [a, c, d]))
    return np.asarray(points), np.asarray(faces, dtype=np.int64)


def test_two_touching_tori_are_meshed_as_edge_components() -> None:
    first_points, first_faces = _torus_surface(0.0)
    second_points, second_faces = _torus_surface(5.0)
    points = np.vstack((first_points, second_points))
    faces = np.vstack((first_faces, second_faces + len(first_points)))

    mesh = build_torus_wedges(points, faces)

    assert mesh is not None
    assert mesh.n_components == 2
    assert len(mesh.cell_faces) == 2 * 24 * 16


def test_non_torus_surface_does_not_activate_rescue() -> None:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    faces = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]])

    assert build_torus_wedges(points, faces) is None


def test_high_genus_torus_defaults_to_valid_all_tet_mesh(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    case = tmp_path / "case"
    result = PipelineOrchestrator().run(
        root / "tests" / "benchmarks" / "high_genus_dual_torus.stl",
        case,
        quality_level="draft",
        mesh_type="tet",
        tier_hint="native_tet",
        max_iterations=1,
        auto_retry="off",
        write_of_case=True,
        max_cells=2_000,
        tier_specific_params={"max_cells": 2_000, "target_cells": 2_000},
    )

    assert result.success, result.error
    checked = NativeMeshChecker().run(case)
    assert checked.negative_volumes == 0
    assert checked.max_skewness < 8.0
    assert checked.max_non_orthogonality < 85.0

    poly = case / "constant" / "polyMesh"
    faces = parse_foam_faces(poly / "faces")
    owner = parse_foam_labels(poly / "owner")
    neighbour = parse_foam_labels(poly / "neighbour")
    cells = [set() for _ in range(max(owner + neighbour) + 1)]
    for index, face in enumerate(faces):
        cells[owner[index]].update(face)
        if index < len(neighbour):
            cells[neighbour[index]].update(face)
    assert all(len(cell) == 4 for cell in cells)
