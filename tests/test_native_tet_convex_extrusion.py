"""Convex constant-section extrusion regressions."""

from __future__ import annotations

import trimesh
import numpy as np

from core.generator.native_tet.convex_extrusion import build_convex_extrusion_wedges


def test_cube_gets_target_sized_structured_wedges() -> None:
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    mesh = build_convex_extrusion_wedges(cube.vertices, cube.faces, target_cells=10000)

    assert mesh is not None
    predicted_final = len(mesh.cell_faces) + 6 * mesh.n_cap_triangles
    assert 8500 <= predicted_final <= 11500
    assert 4 <= mesh.n_slabs <= 12
    assert mesh.tets.ndim == 2 and mesh.tets.shape[1] == 4
    assert len(mesh.cell_faces) == len(mesh.tets)

    p = mesh.points[mesh.tets]
    volumes = np.abs(np.einsum("ij,ij->i", p[:, 1] - p[:, 0], np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0]))) / 6.0
    assert np.all(volumes > 1e-12)
    assert np.isclose(volumes.sum(), 1.0, rtol=1e-10, atol=1e-10)


def test_cylinder_gets_target_sized_structured_wedges() -> None:
    cylinder = trimesh.creation.cylinder(radius=0.5, height=2.0, sections=32)
    mesh = build_convex_extrusion_wedges(
        cylinder.vertices, cylinder.faces, target_cells=10000
    )

    assert mesh is not None
    predicted_final = len(mesh.cell_faces) + 6 * mesh.n_cap_triangles
    assert 8500 <= predicted_final <= 11500
    assert mesh.extrusion_axis == 2


def test_high_resolution_smooth_cylinder_uses_quality_slabs() -> None:
    cylinder = trimesh.creation.cylinder(radius=0.5, height=2.0, sections=128)
    mesh = build_convex_extrusion_wedges(
        cylinder.vertices,
        cylinder.faces,
        target_cells=2000,
        bl_layers=3,
    )

    assert mesh is not None
    assert mesh.extrusion_axis == 2
    assert mesh.n_slabs == 20
    assert mesh.n_cap_triangles < 128
    assert len(mesh.tets) < 7000


def test_small_hole_bracket_uses_quality_hole_slabs(monkeypatch) -> None:
    monkeypatch.delenv("AUTO_TESSELL_CONVEX_HOLE_MIN_SLABS", raising=False)
    monkeypatch.delenv("AUTO_TESSELL_CONVEX_HOLE_MAX_SLABS", raising=False)
    monkeypatch.delenv("AUTO_TESSELL_CONVEX_TRIANGLE_MIN_ANGLE", raising=False)
    bracket = trimesh.load("tests/stl/03_hard_bracket.stl", force="mesh")
    mesh = build_convex_extrusion_wedges(
        bracket.vertices,
        bracket.faces,
        target_cells=1300,
    )

    assert mesh is not None
    assert mesh.tiny_hole_profile
    assert mesh.n_slabs == 18
    assert 200 <= mesh.n_cap_triangles <= 240
    assert 11500 < len(mesh.tets) < 12500


def test_high_aspect_gear_uses_one_layer_budget(monkeypatch) -> None:
    monkeypatch.delenv("AUTO_TESSELL_CONVEX_BUDGET_BL_LAYERS", raising=False)
    gear = trimesh.load("tests/stl/04_extreme_gear.stl", force="mesh")
    mesh = build_convex_extrusion_wedges(
        gear.vertices,
        gear.faces,
        target_cells=2000,
        bl_layers=3,
    )

    assert mesh is not None
    assert mesh.n_slabs == 4
    assert mesh.n_cap_triangles >= 280
    assert 3300 < len(mesh.tets) < 3600


def test_sphere_does_not_activate_constant_section_path() -> None:
    sphere = trimesh.creation.icosphere(subdivisions=2)

    assert build_convex_extrusion_wedges(
        sphere.vertices, sphere.faces, target_cells=10000
    ) is None


def test_elongated_curved_profile_uses_deterministic_extrusion_path() -> None:
    profile = trimesh.creation.cylinder(radius=0.5, height=0.1, sections=32)
    profile.vertices[:, 0] *= 10.0

    assert build_convex_extrusion_wedges(
        profile.vertices, profile.faces, target_cells=10000
    ) is not None


def test_sharp_profile_defers_to_constrained_tetrahedralizer() -> None:
    airfoil = trimesh.load("tests/benchmarks/naca0012.stl", force="mesh")

    assert build_convex_extrusion_wedges(
        airfoil.vertices, airfoil.faces, target_cells=2000
    ) is None
