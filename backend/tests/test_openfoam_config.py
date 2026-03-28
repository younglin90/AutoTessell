"""
Unit tests for mesh/openfoam_config.py

Covers:
  - build_domain: domain size (30L×10L×10L), location placement, minimum cell count,
    zero-length bbox rejection, stl_filename passthrough
  - block_mesh_dict: FoamFile header, vertex count, hex block nx/ny/nz
  - surface_feature_extract_dict: includedAngle defaults and complexity-based override
  - snappy_hex_mesh_dict: default refinement levels, complexity tiers (simple/moderate/
    complex), pro-mode overrides, s_max >= s_min invariant, distance-based refinement
    regions, n_layers auto, relaxed maxNonOrtho
  - control_dict: endTime parameter
  - fv_schemes / fv_solution: FoamFile headers present
"""

import math
import pytest

from mesh.openfoam_config import (
    FlowDomain,
    build_domain,
    block_mesh_dict,
    control_dict,
    fv_schemes,
    fv_solution,
    snappy_hex_mesh_dict,
    surface_feature_extract_dict,
)
from mesh.params import MeshParams
from mesh.stl_utils import BBox, StlComplexity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bbox(min_x=0.0, min_y=0.0, min_z=0.0, max_x=1.0, max_y=1.0, max_z=1.0) -> BBox:
    return BBox(min_x, min_y, min_z, max_x, max_y, max_z)


def _complexity(ratio: float, feat_angle: float = 30.0, s_min: int = 1,
                s_max: int = 3, feat: int = 3) -> StlComplexity:
    return StlComplexity(
        mean_curvature=0.1,
        p95_curvature=ratio * 0.1,
        complexity_ratio=ratio,
        resolve_feature_angle=feat_angle,
        surface_refine_min=s_min,
        surface_refine_max=s_max,
        feature_refine_level=feat,
    )


def _domain(L: float = 1.0, stl_name: str = "geometry.stl") -> FlowDomain:
    bbox = _bbox(0, 0, 0, L, L, L)
    return build_domain(bbox, stl_name)


# ---------------------------------------------------------------------------
# build_domain
# ---------------------------------------------------------------------------

class TestBuildDomain:
    def test_domain_x_span_is_30L(self):
        """x domain = upstream 10L + geometry span + downstream 20L ≈ 30L total."""
        L = 2.0
        bbox = BBox(0, 0, 0, L, L, L)
        d = build_domain(bbox, "shape.stl")
        assert (d.xmax - d.xmin) == pytest.approx(30 * L)

    def test_domain_y_span_is_10L(self):
        L = 3.0
        bbox = BBox(0, 0, 0, L, L, L)
        d = build_domain(bbox, "shape.stl")
        assert (d.ymax - d.ymin) == pytest.approx(10 * L)

    def test_domain_z_span_is_10L(self):
        L = 3.0
        bbox = BBox(0, 0, 0, L, L, L)
        d = build_domain(bbox, "shape.stl")
        assert (d.zmax - d.zmin) == pytest.approx(10 * L)

    def test_location_is_upstream_of_geometry(self):
        """locationInMesh must be upstream (x < xmin of geometry)."""
        L = 1.0
        bbox = BBox(0, 0, 0, L, L, L)
        d = build_domain(bbox, "shape.stl")
        # Geometry center = 0.5; location_x = 0.5 - 8*1 = -7.5
        # That must be < geometry xmin = 0.0
        assert d.location_x < 0.0

    def test_location_x_is_8L_upstream_of_center(self):
        L = 2.0
        cx = L / 2  # center_x = 1.0
        bbox = BBox(0, 0, 0, L, L, L)
        d = build_domain(bbox, "shape.stl")
        assert d.location_x == pytest.approx(cx - 8 * L)

    def test_stl_name_passed_through(self):
        d = build_domain(_bbox(), "my_part.stl")
        assert d.stl_name == "my_part.stl"

    def test_char_length_correct(self):
        bbox = BBox(0, 0, 0, 5.0, 2.0, 3.0)
        d = build_domain(bbox, "shape.stl")
        assert d.char_length == pytest.approx(5.0)

    def test_zero_characteristic_length_raises(self):
        bbox = BBox(1.0, 1.0, 1.0, 1.0, 1.0, 1.0)  # degenerate: all same point
        with pytest.raises(ValueError, match="zero characteristic length"):
            build_domain(bbox, "shape.stl")

    def test_minimum_cell_count_is_four(self):
        """nx, ny, nz must be >= 4 even for very coarse targets."""
        bbox = _bbox(0, 0, 0, 0.001, 0.001, 0.001)
        d = build_domain(bbox, "tiny.stl", target_background_cells=1)
        assert d.nx >= 4
        assert d.ny >= 4
        assert d.nz >= 4

    def test_higher_target_cells_gives_more_cells(self):
        """target_background_cells directly controls resolution, not geometry scale."""
        d_coarse = build_domain(_bbox(), "s.stl", target_background_cells=1_000)
        d_fine = build_domain(_bbox(), "s.stl", target_background_cells=100_000)
        total_coarse = d_coarse.nx * d_coarse.ny * d_coarse.nz
        total_fine = d_fine.nx * d_fine.ny * d_fine.nz
        assert total_fine > total_coarse

    def test_cell_count_scale_invariant(self):
        """Cell count depends only on target_cells, not absolute geometry size."""
        small = build_domain(_bbox(0, 0, 0, 0.1, 0.1, 0.1), "s.stl")
        large = build_domain(_bbox(0, 0, 0, 10.0, 10.0, 10.0), "l.stl")
        assert small.nx == large.nx
        assert small.ny == large.ny
        assert small.nz == large.nz

    def test_location_y_inside_domain(self):
        """locationInMesh y must be within [ymin, ymax]."""
        L = 2.0
        d = build_domain(BBox(0, 0, 0, L, L, L), "shape.stl")
        assert d.ymin < d.location_y < d.ymax

    def test_location_z_inside_domain(self):
        """locationInMesh z must be within [zmin, zmax]."""
        L = 2.0
        d = build_domain(BBox(0, 0, 0, L, L, L), "shape.stl")
        assert d.zmin < d.location_z < d.zmax

    def test_location_y_offset_from_center(self):
        """location_y = cy + 0.1*L (small offset ensures point is off the symmetry plane)."""
        L = 4.0
        bbox = BBox(0, 0, 0, L, L, L)
        d = build_domain(bbox, "shape.stl")
        cy = bbox.center_y
        assert d.location_y == pytest.approx(cy + 0.1 * L)


# ---------------------------------------------------------------------------
# block_mesh_dict
# ---------------------------------------------------------------------------

class TestBlockMeshDict:
    def test_contains_foam_header(self):
        d = _domain()
        s = block_mesh_dict(d)
        assert "FoamFile" in s
        assert "blockMeshDict" in s

    def test_contains_eight_vertices(self):
        d = _domain()
        s = block_mesh_dict(d)
        # 8 vertices labelled // 0 through // 7
        for i in range(8):
            assert f"// {i}" in s

    def test_nx_ny_nz_in_hex_block(self):
        d = _domain()
        s = block_mesh_dict(d)
        assert f"({d.nx} {d.ny} {d.nz})" in s

    def test_contains_inlet_and_outlet(self):
        d = _domain()
        s = block_mesh_dict(d)
        assert "inlet" in s
        assert "outlet" in s

    def test_contains_sides_symmetry_plane(self):
        """blockMeshDict must define a 'sides' symmetryPlane patch."""
        d = _domain()
        s = block_mesh_dict(d)
        assert "sides" in s
        assert "symmetryPlane" in s

    def test_domain_bounds_in_vertex_list(self):
        """The domain min/max coordinates must appear in the vertex list."""
        L = 3.0
        bbox = BBox(0, 0, 0, L, L, L)
        d = build_domain(bbox, "shape.stl")
        s = block_mesh_dict(d)
        # xmin should appear as one of the vertex x-coordinates
        assert f"{d.xmin:.6g}" in s
        assert f"{d.xmax:.6g}" in s


# ---------------------------------------------------------------------------
# surface_feature_extract_dict
# ---------------------------------------------------------------------------

class TestSurfaceFeatureExtractDict:
    def test_default_included_angle_is_150(self):
        s = surface_feature_extract_dict("shape.stl", complexity=None)
        assert "includedAngle   150" in s

    def test_complexity_adjusts_included_angle(self):
        c = _complexity(ratio=5.0, feat_angle=20.0)
        s = surface_feature_extract_dict("shape.stl", complexity=c)
        # includedAngle = 180 - 20 = 160
        assert "includedAngle   160" in s

    def test_simple_complexity_gives_higher_angle(self):
        c = _complexity(ratio=1.0, feat_angle=40.0)
        s = surface_feature_extract_dict("shape.stl", complexity=c)
        # includedAngle = 180 - 40 = 140
        assert "includedAngle   140" in s

    def test_stl_name_appears_in_dict(self):
        s = surface_feature_extract_dict("mypart.stl")
        assert "mypart.stl" in s

    def test_write_obj_is_yes(self):
        s = surface_feature_extract_dict("shape.stl")
        assert "writeObj    yes" in s


# ---------------------------------------------------------------------------
# snappy_hex_mesh_dict — default (no complexity, no params)
# ---------------------------------------------------------------------------

class TestSnappyHexMeshDictDefaults:
    def test_default_refine_levels_s_min_1_s_max_3(self):
        d = _domain()
        s = snappy_hex_mesh_dict(d)
        assert "level ( 1 3 )" in s

    def test_default_feature_angle_30(self):
        d = _domain()
        s = snappy_hex_mesh_dict(d)
        assert "resolveFeatureAngle 30.0" in s

    def test_default_n_layers_3(self):
        d = _domain()
        s = snappy_hex_mesh_dict(d)
        assert "nSurfaceLayers  3" in s

    def test_stl_name_in_geometry_section(self):
        d = build_domain(_bbox(), "wing.stl")
        s = snappy_hex_mesh_dict(d)
        assert "wing.stl" in s

    def test_stem_used_for_emesh(self):
        d = build_domain(_bbox(), "wing.stl")
        s = snappy_hex_mesh_dict(d)
        assert 'file "wing.eMesh"' in s

    def test_contains_foam_header(self):
        d = _domain()
        s = snappy_hex_mesh_dict(d)
        assert "FoamFile" in s
        assert "snappyHexMeshDict" in s

    def test_default_max_non_ortho_70(self):
        d = _domain()
        s = snappy_hex_mesh_dict(d)
        assert "maxNonOrtho             70" in s

    def test_default_relaxed_max_non_ortho_75(self):
        """Relaxed non-ortho = min(85, 70 + 5) = 75."""
        d = _domain()
        s = snappy_hex_mesh_dict(d)
        assert "maxNonOrtho 75" in s


# ---------------------------------------------------------------------------
# snappy_hex_mesh_dict — complexity tiers
# ---------------------------------------------------------------------------

class TestSnappyHexMeshDictComplexity:
    def test_simple_complexity_levels_1_2(self):
        c = _complexity(ratio=2.0, s_min=1, s_max=2)
        d = _domain()
        s = snappy_hex_mesh_dict(d, complexity=c)
        assert "level ( 1 2 )" in s

    def test_moderate_complexity_levels_1_3(self):
        c = _complexity(ratio=5.0, s_min=1, s_max=3)
        d = _domain()
        s = snappy_hex_mesh_dict(d, complexity=c)
        assert "level ( 1 3 )" in s

    def test_complex_complexity_levels_2_4(self):
        c = _complexity(ratio=15.0, s_min=2, s_max=4)
        d = _domain()
        s = snappy_hex_mesh_dict(d, complexity=c)
        assert "level ( 2 4 )" in s

    def test_simple_complexity_n_layers_3(self):
        c = _complexity(ratio=2.0, s_min=1, s_max=2)
        d = _domain()
        s = snappy_hex_mesh_dict(d, complexity=c)
        assert "nSurfaceLayers  3" in s

    def test_complex_complexity_n_layers_5(self):
        c = _complexity(ratio=12.0, s_min=2, s_max=4)
        d = _domain()
        s = snappy_hex_mesh_dict(d, complexity=c)
        assert "nSurfaceLayers  5" in s

    def test_feature_angle_from_complexity(self):
        c = _complexity(ratio=5.0, feat_angle=25.0, s_min=1, s_max=3)
        d = _domain()
        s = snappy_hex_mesh_dict(d, complexity=c)
        assert "resolveFeatureAngle 25.0" in s

    def test_refinement_region_distances_proportional_to_L(self):
        """near=0.1L, mid=0.5L, wake=2.0L must appear in the output."""
        L = 4.0
        bbox = BBox(0, 0, 0, L, L, L)
        d = build_domain(bbox, "shape.stl")
        c = _complexity(ratio=5.0, s_min=1, s_max=3)
        s = snappy_hex_mesh_dict(d, complexity=c)
        near = L * 0.10
        mid = L * 0.50
        wake = L * 2.00
        assert f"{near:.6g}" in s
        assert f"{mid:.6g}" in s
        assert f"{wake:.6g}" in s


# ---------------------------------------------------------------------------
# snappy_hex_mesh_dict — pro-mode overrides
# ---------------------------------------------------------------------------

class TestSnappyHexMeshDictProMode:
    def test_pro_refine_min_override(self):
        mp = MeshParams(snappy_refine_min=2)
        d = _domain()
        s = snappy_hex_mesh_dict(d, params=mp)
        assert "level ( 2 " in s  # s_min=2

    def test_pro_refine_max_override(self):
        mp = MeshParams(snappy_refine_max=5)
        d = _domain()
        s = snappy_hex_mesh_dict(d, params=mp)
        # s_min defaults to auto (1), s_max=5
        assert "level ( 1 5 )" in s

    def test_s_max_invariant_enforced_when_max_lt_min(self):
        """If pro overrides produce s_max < s_min, s_max must be clamped to s_min."""
        # Override only min (to 3) — auto s_max would be 3 from defaults, so force
        # a scenario where user sets min=4 without setting max
        mp = MeshParams(snappy_refine_min=4, snappy_refine_max=None)
        d = _domain()
        s = snappy_hex_mesh_dict(d, params=mp)
        # s_min=4, s_max from auto=3 (default no complexity), invariant forces s_max=4
        assert "level ( 4 4 )" in s

    def test_pro_n_layers_override(self):
        mp = MeshParams(snappy_n_layers=7)
        d = _domain()
        s = snappy_hex_mesh_dict(d, params=mp)
        assert "nSurfaceLayers  7" in s

    def test_pro_max_non_ortho_override(self):
        mp = MeshParams(snappy_max_non_ortho=80.0)
        d = _domain()
        s = snappy_hex_mesh_dict(d, params=mp)
        assert "maxNonOrtho             80" in s

    def test_relaxed_max_non_ortho_capped_at_85(self):
        """relaxed = min(85, max_non_ortho + 5). At 83, result = 85 (not 88)."""
        mp = MeshParams(snappy_max_non_ortho=83.0)
        d = _domain()
        s = snappy_hex_mesh_dict(d, params=mp)
        assert "maxNonOrtho 85" in s

    def test_pro_expansion_ratio_override(self):
        mp = MeshParams(snappy_expansion_ratio=1.4)
        d = _domain()
        s = snappy_hex_mesh_dict(d, params=mp)
        assert "expansionRatio          1.4" in s


# ---------------------------------------------------------------------------
# control_dict
# ---------------------------------------------------------------------------

class TestControlDict:
    def test_contains_foam_header(self):
        s = control_dict()
        assert "FoamFile" in s
        assert "controlDict" in s

    def test_default_end_time_zero(self):
        s = control_dict()
        assert "endTime         0;" in s

    def test_custom_end_time(self):
        s = control_dict(end_time=500)
        assert "endTime         500;" in s

    def test_application_is_simple_foam(self):
        s = control_dict()
        assert "application     simpleFoam" in s


# ---------------------------------------------------------------------------
# fv_schemes / fv_solution
# ---------------------------------------------------------------------------

class TestFvSchemes:
    def test_contains_foam_header(self):
        s = fv_schemes()
        assert "FoamFile" in s
        assert "fvSchemes" in s

    def test_contains_gauss_linear_grad(self):
        s = fv_schemes()
        assert "Gauss linear" in s

    def test_steady_state_ddt(self):
        s = fv_schemes()
        assert "steadyState" in s


class TestFvSolution:
    def test_contains_foam_header(self):
        s = fv_solution()
        assert "FoamFile" in s
        assert "fvSolution" in s

    def test_pressure_solver_is_gamg(self):
        s = fv_solution()
        assert "GAMG" in s

    def test_contains_simple_block(self):
        s = fv_solution()
        assert "SIMPLE" in s
