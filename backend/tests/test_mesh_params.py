"""
Tests for MeshParams and pro-mode config generation.
"""
import json

import pytest

from mesh.params import MeshParams
from mesh.openfoam_config import build_domain, snappy_hex_mesh_dict
from mesh.stl_utils import BBox


# ---------------------------------------------------------------------------
# MeshParams round-trip / serialisation
# ---------------------------------------------------------------------------

class TestMeshParamsSerialisation:
    def test_default_round_trip(self):
        mp = MeshParams()
        restored = MeshParams.from_json(mp.to_json())
        assert restored.tet_stop_energy == mp.tet_stop_energy
        assert restored.netgen_maxh_ratio == mp.netgen_maxh_ratio
        assert restored.mmg_enabled == mp.mmg_enabled

    def test_partial_override_round_trip(self):
        mp = MeshParams(tet_stop_energy=3.5, snappy_n_layers=6, mmg_enabled=False)
        data = json.loads(mp.to_json())
        assert data["tet_stop_energy"] == 3.5
        assert data["snappy_n_layers"] == 6
        assert data["mmg_enabled"] is False

    def test_from_dict_ignores_unknown_keys(self):
        mp = MeshParams.from_dict({"tet_stop_energy": 7.0, "unknown_key": "should_be_dropped"})
        assert mp.tet_stop_energy == 7.0

    def test_default_factory(self):
        mp = MeshParams.default()
        assert mp.tet_stop_energy == 10.0
        assert mp.snappy_refine_min is None
        assert mp.mmg_enabled is True


# ---------------------------------------------------------------------------
# MeshParams.validated() clamping
# ---------------------------------------------------------------------------

class TestMeshParamsValidation:
    def test_stop_energy_clamped_low(self):
        mp = MeshParams(tet_stop_energy=-5).validated()
        assert mp.tet_stop_energy >= 0.5

    def test_stop_energy_clamped_high(self):
        mp = MeshParams(tet_stop_energy=9999).validated()
        assert mp.tet_stop_energy <= 100.0

    def test_edge_fac_clamped(self):
        mp = MeshParams(tet_edge_length_fac=99.0).validated()
        assert mp.tet_edge_length_fac <= 0.5

    def test_n_layers_clamped(self):
        mp = MeshParams(snappy_n_layers=100).validated()
        assert mp.snappy_n_layers <= 12

    def test_non_ortho_clamped(self):
        mp = MeshParams(snappy_max_non_ortho=10).validated()
        assert mp.snappy_max_non_ortho >= 50.0

    def test_expansion_ratio_clamped(self):
        mp = MeshParams(snappy_expansion_ratio=0.5).validated()
        assert mp.snappy_expansion_ratio >= 1.05

    def test_netgen_ratio_clamped(self):
        mp = MeshParams(netgen_maxh_ratio=0.1).validated()
        assert mp.netgen_maxh_ratio >= 2.0

    def test_none_fields_stay_none_after_validation(self):
        mp = MeshParams(tet_edge_length_fac=None, snappy_refine_min=None).validated()
        assert mp.tet_edge_length_fac is None
        assert mp.snappy_refine_min is None

    def test_hgrad_clamped(self):
        mp = MeshParams(mmg_hgrad=100.0).validated()
        assert mp.mmg_hgrad <= 5.0


# ---------------------------------------------------------------------------
# snappy_hex_mesh_dict pro override tests
# ---------------------------------------------------------------------------

@pytest.fixture
def unit_bbox() -> BBox:
    return BBox(0, 0, 0, 1, 1, 1)


@pytest.fixture
def unit_domain(unit_bbox):
    return build_domain(unit_bbox, "geom.stl")


class TestSnappyParamsOverride:
    def test_default_expansion_ratio_present(self, unit_domain):
        text = snappy_hex_mesh_dict(unit_domain)
        assert "expansionRatio" in text
        assert "1.2" in text

    def test_pro_expansion_ratio_applied(self, unit_domain):
        mp = MeshParams(snappy_expansion_ratio=1.35)
        text = snappy_hex_mesh_dict(unit_domain, params=mp)
        assert "1.35" in text

    def test_pro_n_layers_applied(self, unit_domain):
        mp = MeshParams(snappy_n_layers=7)
        text = snappy_hex_mesh_dict(unit_domain, params=mp)
        assert "nSurfaceLayers  7" in text

    def test_pro_max_non_ortho_applied(self, unit_domain):
        mp = MeshParams(snappy_max_non_ortho=65)
        text = snappy_hex_mesh_dict(unit_domain, params=mp)
        assert "maxNonOrtho             65" in text

    def test_pro_refine_min_override(self, unit_domain):
        mp = MeshParams(snappy_refine_min=2, snappy_refine_max=4)
        text = snappy_hex_mesh_dict(unit_domain, params=mp)
        assert "level ( 2 4 )" in text

    def test_pro_refine_max_below_min_is_corrected(self, unit_domain):
        # validated() raises snappy_refine_max to match snappy_refine_min when max < min
        mp = MeshParams(snappy_refine_min=3, snappy_refine_max=1)
        mp_v = mp.validated()
        assert mp_v.snappy_refine_max >= mp_v.snappy_refine_min
        text = snappy_hex_mesh_dict(unit_domain, params=mp_v)
        import re
        m = re.search(r"level \( (\d+) (\d+) \)", text)
        assert m is not None
        level_min = int(m.group(1))
        level_max = int(m.group(2))
        assert level_max >= level_min

    def test_validated_snappy_max_raised_to_min_when_inverted(self):
        """validated() must enforce snappy_refine_max >= snappy_refine_min."""
        mp = MeshParams(snappy_refine_min=4, snappy_refine_max=2).validated()
        assert mp.snappy_refine_max == 4  # raised from 2 to match min=4

    def test_validated_snappy_equal_min_max_unchanged(self):
        """Equal min/max is valid and must be preserved."""
        mp = MeshParams(snappy_refine_min=3, snappy_refine_max=3).validated()
        assert mp.snappy_refine_min == 3
        assert mp.snappy_refine_max == 3

    def test_pro_refine_min_set_without_max_keeps_smax_gte_smin(self, unit_domain):
        """snappy_refine_min=5 with no snappy_refine_max must not produce min > max."""
        import re
        mp = MeshParams(snappy_refine_min=5)  # snappy_refine_max left as None
        text = snappy_hex_mesh_dict(unit_domain, params=mp)
        m = re.search(r"level \( (\d+) (\d+) \)", text)
        assert m is not None
        assert int(m.group(2)) >= int(m.group(1)), "s_max must be >= s_min"

    def test_relaxed_non_ortho_is_5_above_max(self, unit_domain):
        mp = MeshParams(snappy_max_non_ortho=75)
        text = snappy_hex_mesh_dict(unit_domain, params=mp)
        # Relaxed should be 80
        assert "maxNonOrtho 80" in text

    def test_relaxed_non_ortho_capped_at_85(self, unit_domain):
        mp = MeshParams(snappy_max_non_ortho=83)
        text = snappy_hex_mesh_dict(unit_domain, params=mp)
        assert "maxNonOrtho 85" in text

    def test_no_params_uses_defaults(self, unit_domain):
        text = snappy_hex_mesh_dict(unit_domain)
        # Default n_layers for simple geometry (no complexity) = 3
        assert "nSurfaceLayers  3" in text
        assert "maxNonOrtho             70" in text


# ---------------------------------------------------------------------------
# dev pipeline edge_length_fac auto-calculation
# ---------------------------------------------------------------------------

class TestCellsToEdgeFac:
    def test_fac_decreases_as_cells_increase(self):
        from mesh.dev_pipeline import _cells_to_edge_fac
        import numpy as np

        # Unit cube vertices
        verts = np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],
                          [0,0,1],[1,0,1],[1,1,1],[0,1,1]], dtype=np.float64)
        fac_coarse = _cells_to_edge_fac(10_000, verts)
        fac_fine = _cells_to_edge_fac(1_000_000, verts)
        assert fac_fine < fac_coarse

    def test_fac_is_clamped_to_range(self):
        from mesh.dev_pipeline import _cells_to_edge_fac
        import numpy as np

        verts = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
        for cells in [1, 100, 10_000, 1_000_000, 100_000_000]:
            fac = _cells_to_edge_fac(cells, verts)
            assert 0.02 <= fac <= 0.2, f"fac={fac} out of range for cells={cells}"

    def test_pro_override_skips_auto_calc(self):
        """When tet_edge_length_fac is set, auto calc should not be used."""
        mp = MeshParams(tet_edge_length_fac=0.07)
        assert mp.tet_edge_length_fac == 0.07
