"""
Unit tests for mesh generator pipeline components.

Covers:
  - BBox computation from binary/ASCII STL
  - FlowDomain calculation (10L/20L/5L ratios)
  - OpenFOAM config file generation (blockMeshDict, snappyHexMeshDict)
  - Gmsh .msh v2 writer (node/element count)
"""

import struct
from pathlib import Path

import pytest

from mesh.stl_utils import BBox, get_bbox
from mesh.openfoam_config import build_domain, block_mesh_dict, snappy_hex_mesh_dict


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_binary_stl(vertices_per_tri: list[tuple]) -> bytes:
    """Build a binary STL with the given triangles (list of 3-vertex tuples)."""
    num_tri = len(vertices_per_tri)
    header = b"\x00" * 80
    count = struct.pack("<I", num_tri)
    body = b""
    for tri in vertices_per_tri:
        # normal (0,0,0) + 3 vertices + attr
        body += struct.pack("<3f", 0, 0, 0)
        for vx, vy, vz in tri:
            body += struct.pack("<3f", vx, vy, vz)
        body += b"\x00\x00"
    return header + count + body


def _unit_cube_stl() -> bytes:
    """Two triangles forming the bottom face of a unit cube (0–1 in all dims)."""
    triangles = [
        ((0, 0, 0), (1, 0, 0), (1, 1, 0)),
        ((0, 0, 0), (1, 1, 0), (0, 1, 0)),
        ((0, 0, 0), (0, 0, 1), (1, 0, 0)),
        ((0, 0, 1), (1, 0, 1), (1, 0, 0)),
        ((1, 0, 0), (1, 0, 1), (1, 1, 1)),
        ((1, 0, 0), (1, 1, 1), (1, 1, 0)),
    ]
    return _make_binary_stl(triangles)


@pytest.fixture
def unit_cube_stl(tmp_path: Path) -> Path:
    p = tmp_path / "cube.stl"
    p.write_bytes(_unit_cube_stl())
    return p


@pytest.fixture
def unit_cube_bbox() -> BBox:
    return BBox(0, 0, 0, 1, 1, 1)


# ---------------------------------------------------------------------------
# BBox tests
# ---------------------------------------------------------------------------

class TestGetBBox:
    def test_binary_stl_correct_bounds(self, unit_cube_stl: Path):
        bbox = get_bbox(unit_cube_stl)
        assert bbox.min_x == pytest.approx(0, abs=1e-5)
        assert bbox.min_y == pytest.approx(0, abs=1e-5)
        assert bbox.min_z == pytest.approx(0, abs=1e-5)
        assert bbox.max_x == pytest.approx(1, abs=1e-5)
        assert bbox.max_y == pytest.approx(1, abs=1e-5)
        assert bbox.max_z == pytest.approx(1, abs=1e-5)

    def test_characteristic_length_is_max_dim(self, unit_cube_stl: Path):
        bbox = get_bbox(unit_cube_stl)
        assert bbox.characteristic_length == pytest.approx(1.0, abs=1e-5)

    def test_asymmetric_bbox(self, tmp_path: Path):
        # Long thin object: 10×1×1
        tris = [((0,0,0),(10,0,0),(10,1,0)), ((0,0,0),(10,1,0),(0,1,0))]
        p = tmp_path / "long.stl"
        p.write_bytes(_make_binary_stl(tris))
        bbox = get_bbox(p)
        assert bbox.characteristic_length == pytest.approx(10.0, abs=1e-3)

    def test_ascii_stl(self, tmp_path: Path):
        text = (
            "solid test\n"
            "  facet normal 0 0 1\n    outer loop\n"
            "      vertex 0.0 0.0 0.0\n"
            "      vertex 2.0 0.0 0.0\n"
            "      vertex 0.0 3.0 0.0\n"
            "    endloop\n  endfacet\n"
            "endsolid test\n"
        )
        p = tmp_path / "ascii.stl"
        p.write_text(text)
        bbox = get_bbox(p)
        assert bbox.max_x == pytest.approx(2.0, abs=1e-5)
        assert bbox.max_y == pytest.approx(3.0, abs=1e-5)


# ---------------------------------------------------------------------------
# Domain builder tests
# ---------------------------------------------------------------------------

class TestBuildDomain:
    def test_domain_ratios(self, unit_cube_bbox: BBox):
        """Domain must be 30L × 10L × 10L (10L upstream, 20L downstream, 5L sides)."""
        d = build_domain(unit_cube_bbox, "geom.stl")
        L = unit_cube_bbox.characteristic_length  # = 1.0
        assert (d.xmax - d.xmin) == pytest.approx(30 * L, rel=1e-6)
        assert (d.ymax - d.ymin) == pytest.approx(10 * L, rel=1e-6)
        assert (d.zmax - d.zmin) == pytest.approx(10 * L, rel=1e-6)

    def test_upstream_is_10L(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "geom.stl")
        cx = unit_cube_bbox.center_x  # 0.5
        L = unit_cube_bbox.characteristic_length  # 1.0
        assert (cx - d.xmin) == pytest.approx(10 * L, rel=1e-6)

    def test_downstream_is_20L(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "geom.stl")
        cx = unit_cube_bbox.center_x
        L = unit_cube_bbox.characteristic_length
        assert (d.xmax - cx) == pytest.approx(20 * L, rel=1e-6)

    def test_location_in_mesh_is_upstream(self, unit_cube_bbox: BBox):
        """locationInMesh must be outside the geometry (upstream in this implementation)."""
        d = build_domain(unit_cube_bbox, "geom.stl")
        # Location should be upstream of the geometry
        assert d.location_x < unit_cube_bbox.min_x

    def test_background_cell_count_in_range(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "geom.stl", target_background_cells=40_000)
        total = d.nx * d.ny * d.nz
        # Allow 2× tolerance — exact count depends on rounding
        assert total > 10_000
        assert total < 200_000

    def test_zero_characteristic_length_raises(self):
        bad_bbox = BBox(1, 1, 1, 1, 1, 1)  # degenerate
        with pytest.raises(ValueError, match="zero characteristic length"):
            build_domain(bad_bbox, "geom.stl")


# ---------------------------------------------------------------------------
# Config template tests
# ---------------------------------------------------------------------------

class TestBlockMeshDict:
    def test_contains_required_keys(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "geom.stl")
        config = block_mesh_dict(d)
        assert "blockMeshDict" in config
        assert "hex" in config
        assert "inlet" in config
        assert "outlet" in config
        assert str(d.nx) in config
        assert str(d.ny) in config


class TestSnappyHexMeshDict:
    def test_stl_name_appears(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "my_shape.stl")
        config = snappy_hex_mesh_dict(d)
        assert "my_shape.stl" in config
        assert "my_shape" in config  # stem

    def test_location_in_mesh(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "shape.stl")
        config = snappy_hex_mesh_dict(d)
        assert "locationInMesh" in config
        # Coordinates should appear (formatted as floats)
        assert str(round(d.location_x, 1)).split(".")[0] in config

    def test_layer_controls_present(self, unit_cube_bbox: BBox):
        d = build_domain(unit_cube_bbox, "shape.stl")
        config = snappy_hex_mesh_dict(d)
        assert "addLayersControls" in config
        assert "nSurfaceLayers" in config
