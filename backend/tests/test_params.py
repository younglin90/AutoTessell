"""
Unit tests for mesh/params.py — MeshParams dataclass.

Covers:
  - default construction and field values
  - to_json / from_json round-trip
  - from_dict with unknown keys filtered out
  - validated(): each clamping branch, invariant enforcement, None-skip paths
"""

import json
import pytest

from mesh.params import MeshParams


# ---------------------------------------------------------------------------
# Default construction
# ---------------------------------------------------------------------------

class TestMeshParamsDefaults:
    def test_tet_stop_energy_default_10(self):
        assert MeshParams().tet_stop_energy == 10.0

    def test_tet_edge_length_fac_default_none(self):
        assert MeshParams().tet_edge_length_fac is None

    def test_snappy_refine_min_default_none(self):
        assert MeshParams().snappy_refine_min is None

    def test_snappy_refine_max_default_none(self):
        assert MeshParams().snappy_refine_max is None

    def test_snappy_n_layers_default_none(self):
        assert MeshParams().snappy_n_layers is None

    def test_snappy_expansion_ratio_default(self):
        assert MeshParams().snappy_expansion_ratio == pytest.approx(1.2)

    def test_snappy_final_layer_thickness_default(self):
        assert MeshParams().snappy_final_layer_thickness == pytest.approx(0.3)

    def test_snappy_max_non_ortho_default(self):
        assert MeshParams().snappy_max_non_ortho == pytest.approx(70.0)

    def test_netgen_maxh_ratio_default(self):
        assert MeshParams().netgen_maxh_ratio == pytest.approx(15.0)

    def test_mmg_enabled_default_true(self):
        assert MeshParams().mmg_enabled is True

    def test_mmg_hausd_default_none(self):
        assert MeshParams().mmg_hausd is None

    def test_mmg_hgrad_default(self):
        assert MeshParams().mmg_hgrad == pytest.approx(1.3)

    def test_default_classmethod_equals_empty_constructor(self):
        assert MeshParams.default() == MeshParams()


# ---------------------------------------------------------------------------
# Serialisation: to_json / from_json / from_dict
# ---------------------------------------------------------------------------

class TestMeshParamsSerialisation:
    def test_to_json_produces_valid_json(self):
        s = MeshParams().to_json()
        parsed = json.loads(s)
        assert isinstance(parsed, dict)

    def test_to_json_contains_tet_stop_energy(self):
        s = MeshParams(tet_stop_energy=5.0).to_json()
        d = json.loads(s)
        assert d["tet_stop_energy"] == pytest.approx(5.0)

    def test_from_json_round_trip(self):
        mp = MeshParams(tet_stop_energy=7.5, snappy_refine_min=2, mmg_enabled=False)
        assert MeshParams.from_json(mp.to_json()) == mp

    def test_from_dict_ignores_unknown_keys(self):
        """Extra keys not in MeshParams must be silently dropped."""
        d = {"tet_stop_energy": 3.0, "unknown_key": "ignored", "another": 999}
        mp = MeshParams.from_dict(d)
        assert mp.tet_stop_energy == pytest.approx(3.0)

    def test_from_dict_partial_override_keeps_defaults(self):
        """from_dict with only one key must keep all others at default."""
        mp = MeshParams.from_dict({"snappy_max_non_ortho": 65.0})
        assert mp.snappy_max_non_ortho == pytest.approx(65.0)
        assert mp.tet_stop_energy == pytest.approx(10.0)  # default preserved

    def test_none_fields_survive_round_trip(self):
        mp = MeshParams(tet_edge_length_fac=None, snappy_refine_min=None, mmg_hausd=None)
        mp2 = MeshParams.from_json(mp.to_json())
        assert mp2.tet_edge_length_fac is None
        assert mp2.snappy_refine_min is None
        assert mp2.mmg_hausd is None


# ---------------------------------------------------------------------------
# validated(): clamping branches
# ---------------------------------------------------------------------------

class TestMeshParamsValidated:
    def test_tet_stop_energy_clamped_to_min(self):
        """Value below 0.5 must be raised to 0.5."""
        mp = MeshParams(tet_stop_energy=0.0).validated()
        assert mp.tet_stop_energy == pytest.approx(0.5)

    def test_tet_stop_energy_clamped_to_max(self):
        """Value above 100 must be clamped to 100."""
        mp = MeshParams(tet_stop_energy=999.0).validated()
        assert mp.tet_stop_energy == pytest.approx(100.0)

    def test_tet_stop_energy_in_range_unchanged(self):
        mp = MeshParams(tet_stop_energy=15.0).validated()
        assert mp.tet_stop_energy == pytest.approx(15.0)

    def test_tet_edge_length_fac_none_skipped(self):
        """None tet_edge_length_fac must remain None (no clamping attempted)."""
        mp = MeshParams(tet_edge_length_fac=None).validated()
        assert mp.tet_edge_length_fac is None

    def test_tet_edge_length_fac_clamped_to_min(self):
        mp = MeshParams(tet_edge_length_fac=0.0001).validated()
        assert mp.tet_edge_length_fac == pytest.approx(0.005)

    def test_tet_edge_length_fac_clamped_to_max(self):
        mp = MeshParams(tet_edge_length_fac=0.99).validated()
        assert mp.tet_edge_length_fac == pytest.approx(0.5)

    def test_snappy_refine_min_none_skipped(self):
        """None snappy_refine_min must remain None."""
        mp = MeshParams(snappy_refine_min=None).validated()
        assert mp.snappy_refine_min is None

    def test_snappy_refine_min_clamped_to_zero(self):
        mp = MeshParams(snappy_refine_min=-1).validated()
        assert mp.snappy_refine_min == 0

    def test_snappy_refine_min_clamped_to_five(self):
        mp = MeshParams(snappy_refine_min=10).validated()
        assert mp.snappy_refine_min == 5

    def test_snappy_refine_max_none_skipped(self):
        mp = MeshParams(snappy_refine_max=None).validated()
        assert mp.snappy_refine_max is None

    def test_snappy_refine_max_clamped_to_six(self):
        mp = MeshParams(snappy_refine_max=99).validated()
        assert mp.snappy_refine_max == 6

    def test_snappy_refine_invariant_enforced_when_both_set(self):
        """If min > max after individual clamping, max is raised to min."""
        # min=4 (in range), max=2 (in range) → invariant sets max = max(4, 2) = 4
        mp = MeshParams(snappy_refine_min=4, snappy_refine_max=2).validated()
        assert mp.snappy_refine_max >= mp.snappy_refine_min

    def test_snappy_refine_invariant_not_applied_when_only_min_set(self):
        """Invariant clamping must NOT run when only min is provided (max is None)."""
        mp = MeshParams(snappy_refine_min=3, snappy_refine_max=None).validated()
        assert mp.snappy_refine_max is None  # max stays None — not constrained to min

    def test_snappy_n_layers_none_skipped(self):
        mp = MeshParams(snappy_n_layers=None).validated()
        assert mp.snappy_n_layers is None

    def test_snappy_n_layers_clamped_to_zero(self):
        mp = MeshParams(snappy_n_layers=-5).validated()
        assert mp.snappy_n_layers == 0

    def test_snappy_n_layers_clamped_to_twelve(self):
        mp = MeshParams(snappy_n_layers=100).validated()
        assert mp.snappy_n_layers == 12

    def test_snappy_expansion_ratio_clamped(self):
        mp = MeshParams(snappy_expansion_ratio=0.5).validated()
        assert mp.snappy_expansion_ratio == pytest.approx(1.05)

    def test_snappy_expansion_ratio_max_clamped(self):
        mp = MeshParams(snappy_expansion_ratio=9.9).validated()
        assert mp.snappy_expansion_ratio == pytest.approx(2.0)

    def test_snappy_final_layer_thickness_clamped_min(self):
        mp = MeshParams(snappy_final_layer_thickness=0.0).validated()
        assert mp.snappy_final_layer_thickness == pytest.approx(0.05)

    def test_snappy_max_non_ortho_clamped_min(self):
        mp = MeshParams(snappy_max_non_ortho=10.0).validated()
        assert mp.snappy_max_non_ortho == pytest.approx(50.0)

    def test_snappy_max_non_ortho_clamped_max(self):
        mp = MeshParams(snappy_max_non_ortho=99.0).validated()
        assert mp.snappy_max_non_ortho == pytest.approx(85.0)

    def test_netgen_maxh_ratio_clamped_min(self):
        mp = MeshParams(netgen_maxh_ratio=0.5).validated()
        assert mp.netgen_maxh_ratio == pytest.approx(2.0)

    def test_netgen_maxh_ratio_clamped_max(self):
        mp = MeshParams(netgen_maxh_ratio=500.0).validated()
        assert mp.netgen_maxh_ratio == pytest.approx(100.0)

    def test_mmg_hausd_none_skipped(self):
        mp = MeshParams(mmg_hausd=None).validated()
        assert mp.mmg_hausd is None

    def test_mmg_hausd_clamped_min(self):
        mp = MeshParams(mmg_hausd=0.0).validated()
        assert mp.mmg_hausd == pytest.approx(1e-6)

    def test_mmg_hausd_clamped_max(self):
        mp = MeshParams(mmg_hausd=99.0).validated()
        assert mp.mmg_hausd == pytest.approx(1.0)

    def test_mmg_hgrad_clamped_min(self):
        mp = MeshParams(mmg_hgrad=0.5).validated()
        assert mp.mmg_hgrad == pytest.approx(1.0)

    def test_mmg_hgrad_clamped_max(self):
        mp = MeshParams(mmg_hgrad=10.0).validated()
        assert mp.mmg_hgrad == pytest.approx(5.0)

    def test_in_range_values_unchanged(self):
        """All values in valid range must pass through validated() unchanged."""
        mp = MeshParams(
            tet_stop_energy=8.0,
            tet_edge_length_fac=0.05,
            snappy_refine_min=1,
            snappy_refine_max=3,
            snappy_n_layers=4,
            snappy_expansion_ratio=1.3,
            snappy_final_layer_thickness=0.25,
            snappy_max_non_ortho=70.0,
            netgen_maxh_ratio=15.0,
            mmg_hausd=0.01,
            mmg_hgrad=1.5,
        )
        v = mp.validated()
        assert v == mp

    def test_validated_returns_new_instance(self):
        """validated() must return a new MeshParams, not mutate self."""
        mp = MeshParams(tet_stop_energy=999.0)
        v = mp.validated()
        assert v is not mp
        assert mp.tet_stop_energy == pytest.approx(999.0)  # original unchanged
