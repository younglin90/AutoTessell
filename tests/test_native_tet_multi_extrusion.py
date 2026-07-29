"""Repeated extrusion component rescue regressions."""

from __future__ import annotations

import trimesh

from core.generator.native_tet.multi_extrusion import build_multi_extrusions


def test_convex_body_and_repeated_cylinders_are_preserved() -> None:
    components = [trimesh.creation.box(extents=(5.0, 5.0, 2.0))]
    for index in range(8):
        cylinder = trimesh.creation.cylinder(radius=0.15, height=3.0, sections=16)
        cylinder.apply_translation((-2.0 + 0.5 * index, 0.0, 0.0))
        components.append(cylinder)
    surface = trimesh.util.concatenate(components)

    mesh = build_multi_extrusions(
        surface.vertices,
        surface.faces,
        target_cells=500,
    )

    assert mesh is not None
    assert mesh.n_components == 9
    assert mesh.n_extrusions == 8
    assert len(mesh.cell_faces) > 8


def test_single_body_does_not_activate_multi_extrusion_rescue() -> None:
    box = trimesh.creation.box()

    assert build_multi_extrusions(box.vertices, box.faces, target_cells=500) is None
