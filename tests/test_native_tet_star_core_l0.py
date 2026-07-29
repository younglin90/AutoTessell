import numpy as np
import pytest
import trimesh

from core.generator.native_tet.core_certificate import snapshot_tet_core_certificate
from core.generator.native_tet.star_core_l0 import build_star_tet_core


def test_star_core_realizes_every_cube_source_face_on_the_boundary() -> None:
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    core = build_star_tet_core(cube.vertices, cube.faces)
    certificate = snapshot_tet_core_certificate(cube.faces, core.points, core.tets, "cube")

    assert core.points.shape == (9, 3)
    assert core.tets.shape == (12, 4)
    assert certificate.strict_source_face_ratio == 1.0
    assert certificate.boundary_source_face_ratio == 1.0
    assert certificate.n_zero_volume == 0


def test_star_core_is_deterministic() -> None:
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    first = build_star_tet_core(cube.vertices, cube.faces)
    second = build_star_tet_core(cube.vertices, cube.faces)

    assert np.array_equal(first.points, second.points)
    assert np.array_equal(first.tets, second.tets)


def test_star_core_keeps_cylinder_source_faces_on_the_boundary() -> None:
    cylinder = trimesh.creation.cylinder(radius=1.0, height=2.0, sections=32)
    core = build_star_tet_core(cylinder.vertices, cylinder.faces)
    certificate = snapshot_tet_core_certificate(cylinder.faces, core.points, core.tets, "cylinder")

    assert certificate.strict_source_face_ratio == 1.0
    assert certificate.boundary_source_face_ratio == 1.0
    assert certificate.n_zero_volume == 0


def test_star_core_rejects_a_center_outside_the_kernel() -> None:
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))

    with pytest.raises(ValueError, match="strict star point"):
        build_star_tet_core(cube.vertices, cube.faces, center=np.asarray((2.0, 0.0, 0.0)))
