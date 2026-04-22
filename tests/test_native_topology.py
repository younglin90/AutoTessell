"""core/analyzer/topology.py × trimesh 교차 검증 테스트.

v0.4 native-first: watertight/manifold/genus/components 등이 trimesh 결과와
일치하는지 검증.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.analyzer import topology as T
from core.analyzer.readers import read_stl

trimesh = pytest.importorskip("trimesh")


_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"
CUBE_STL = _REPO / "tests" / "benchmarks" / "cube.stl"


@pytest.fixture
def sphere_mesh():
    if not SPHERE_STL.exists():
        pytest.skip("sphere.stl 없음")
    return read_stl(SPHERE_STL)


@pytest.fixture
def cube_mesh():
    if not CUBE_STL.exists():
        pytest.skip("cube.stl 없음")
    return read_stl(CUBE_STL)


# ---------------------------------------------------------------------------
# Watertight / manifold
# ---------------------------------------------------------------------------


def test_sphere_watertight_matches_trimesh(sphere_mesh) -> None:
    t = trimesh.load(str(SPHERE_STL))
    assert T.is_watertight(sphere_mesh.faces) == t.is_watertight


def test_cube_watertight_matches_trimesh(cube_mesh) -> None:
    t = trimesh.load(str(CUBE_STL))
    assert T.is_watertight(cube_mesh.faces) == t.is_watertight


def test_sphere_manifold(sphere_mesh) -> None:
    assert T.is_manifold(sphere_mesh.faces) is True
    assert T.count_non_manifold_edges(sphere_mesh.faces) == 0


def test_open_surface_not_watertight(tmp_path: Path) -> None:
    """단일 삼각형 → watertight False, manifold True."""
    # 단일 삼각형 + dedupe (자체 stl reader) 검증용 STL 생성
    p = tmp_path / "tri.stl"
    p.write_text(
        "solid s\nfacet normal 0 0 1\n outer loop\n  vertex 0 0 0\n"
        "  vertex 1 0 0\n  vertex 0 1 0\n endloop\nendfacet\nendsolid s\n",
        encoding="utf-8",
    )
    m = read_stl(p)
    assert T.is_watertight(m.faces) is False
    assert T.is_manifold(m.faces) is True


# ---------------------------------------------------------------------------
# Genus / Euler
# ---------------------------------------------------------------------------


def test_sphere_genus_zero(sphere_mesh) -> None:
    assert T.compute_genus(sphere_mesh.n_vertices, sphere_mesh.faces) == 0


def test_cube_genus_zero(cube_mesh) -> None:
    assert T.compute_genus(cube_mesh.n_vertices, cube_mesh.faces) == 0


def test_sphere_euler_two(sphere_mesh) -> None:
    assert T.compute_euler(sphere_mesh.n_vertices, sphere_mesh.faces) == 2


def test_cube_euler_two(cube_mesh) -> None:
    assert T.compute_euler(cube_mesh.n_vertices, cube_mesh.faces) == 2


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


def test_sphere_single_component(sphere_mesh) -> None:
    assert T.num_connected_components(sphere_mesh.faces) == 1


def test_two_disconnected_triangles_are_two_components(tmp_path: Path) -> None:
    p = tmp_path / "two_tris.obj"
    p.write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        "v 5 5 5\nv 6 5 5\nv 5 6 5\n"
        "f 1 2 3\nf 4 5 6\n",
        encoding="utf-8",
    )
    from core.analyzer.readers import read_obj
    m = read_obj(p)
    assert T.num_connected_components(m.faces) == 2
    comps = T.split_components(m.faces)
    assert np.unique(comps).size == 2


# ---------------------------------------------------------------------------
# Dihedral / sharp edges
# ---------------------------------------------------------------------------


def test_sphere_no_sharp_edges(sphere_mesh) -> None:
    # coarse sphere 는 삼각형 normal 차이가 90° 이하가 대부분. 90° 이상 sharp 는 없어야 함.
    assert T.count_sharp_edges(sphere_mesh.vertices, sphere_mesh.faces, 90.0) == 0


def test_cube_has_sharp_edges(cube_mesh) -> None:
    # cube 의 모서리에는 90° dihedral 이 있어야 함.
    n = T.count_sharp_edges(cube_mesh.vertices, cube_mesh.faces, 80.0)
    assert n > 0


def test_dihedral_range(sphere_mesh) -> None:
    edges, angles = T.dihedral_angles(sphere_mesh.vertices, sphere_mesh.faces)
    assert edges.shape[0] == angles.shape[0]
    assert (angles >= 0).all() and (angles <= np.pi + 1e-9).all()


# ---------------------------------------------------------------------------
# Boundary edges
# ---------------------------------------------------------------------------


def test_closed_mesh_has_no_boundary_edges(sphere_mesh) -> None:
    assert T.boundary_edges(sphere_mesh.faces).shape[0] == 0


def test_single_tri_has_three_boundary_edges(tmp_path: Path) -> None:
    p = tmp_path / "tri.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    from core.analyzer.readers import read_obj
    m = read_obj(p)
    assert T.boundary_edges(m.faces).shape[0] == 3
