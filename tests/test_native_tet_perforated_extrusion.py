"""Structured perforated extrusion regressions."""

from __future__ import annotations

import numpy as np
import trimesh

from core.generator.native_tet.perforated_extrusion import (
    build_perforated_extrusion_wedges,
)


def _plate_with_tools(count: int = 8) -> trimesh.Trimesh:
    parts = [trimesh.creation.box(extents=(5.0, 5.0, 2.0))]
    for index in range(count):
        tool = trimesh.creation.cylinder(radius=0.15, height=3.0, sections=16)
        tool.apply_translation((-2.0 + 0.5 * index, 0.0, 0.0))
        parts.append(tool)
    return trimesh.util.concatenate(parts)


def test_crossing_tools_create_single_watertight_difference_surface() -> None:
    surface = _plate_with_tools()

    mesh = build_perforated_extrusion_wedges(
        surface.vertices,
        surface.faces,
        target_cells=1000,
    )

    assert mesh is not None
    assert mesh.n_holes == 8
    assert mesh.extrusion_axis == 2
    assert len(mesh.cell_faces) > 100
    reference = trimesh.Trimesh(
        vertices=mesh.reference_vertices,
        faces=mesh.reference_faces,
        process=False,
    )
    assert reference.is_watertight
    assert np.isclose(reference.volume, 50.0 - 8 * np.pi * 0.15**2 * 2.0, rtol=0.02)


def test_tools_that_do_not_cross_body_do_not_activate() -> None:
    surface = _plate_with_tools()
    surface.vertices[surface.vertices[:, 2] > 1.0, 2] = 0.9

    assert (
        build_perforated_extrusion_wedges(
            surface.vertices,
            surface.faces,
            target_cells=1000,
        )
        is None
    )
