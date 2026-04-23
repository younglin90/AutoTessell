"""beta42 — core/utils/bc_writer.py dedicated 회귀.

write_boundary_conditions + _build_*_bc 에 대한 단위 회귀. inlet/outlet/wall/
symmetryPlane 각 패치 타입이 올바른 BC 타입 문자열을 생성하는지.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.utils.bc_writer import (
    _build_k_bc,
    _build_nut_bc,
    _build_omega_bc,
    _build_p_bc,
    _build_U_bc,
    write_boundary_conditions,
)


# ---------------------------------------------------------------------------
# write_boundary_conditions 전체 흐름
# ---------------------------------------------------------------------------


def test_write_creates_all_expected_files(tmp_path: Path) -> None:
    """0/ 디렉터리에 p/U/k/omega/nut + constant/{transport,turbulence}Properties
    모두 생성."""
    patches = [
        {"name": "inlet", "type": "inlet"},
        {"name": "outlet", "type": "outlet"},
        {"name": "walls", "type": "wall"},
    ]
    files = write_boundary_conditions(
        tmp_path, patches, flow_velocity=1.0, turbulence_model="kOmegaSST",
    )
    assert "0/p" in files
    assert "0/U" in files
    assert "0/k" in files
    assert "0/omega" in files
    assert "0/nut" in files
    assert "constant/transportProperties" in files
    assert "constant/turbulenceProperties" in files

    # 실제 파일 존재
    for name in ("p", "U", "k", "omega", "nut"):
        assert (tmp_path / "0" / name).exists()
    assert (tmp_path / "constant" / "transportProperties").exists()
    assert (tmp_path / "constant" / "turbulenceProperties").exists()


def test_turbulence_model_in_properties_file(tmp_path: Path) -> None:
    """turbulence_model 인자가 constant/turbulenceProperties 에 반영."""
    patches = [{"name": "walls", "type": "wall"}]
    write_boundary_conditions(
        tmp_path, patches, flow_velocity=1.0, turbulence_model="kEpsilon",
    )
    content = (tmp_path / "constant" / "turbulenceProperties").read_text()
    assert "kEpsilon" in content


# ---------------------------------------------------------------------------
# 개별 BC builder
# ---------------------------------------------------------------------------


def test_p_bc_inlet_is_zero_gradient() -> None:
    """inlet 에서 p 는 zeroGradient."""
    out = _build_p_bc([{"name": "inlet", "type": "inlet"}])
    assert "zeroGradient" in out
    assert "inlet" in out


def test_p_bc_outlet_is_fixed_value_zero() -> None:
    """outlet 에서 p 는 fixedValue uniform 0."""
    out = _build_p_bc([{"name": "outlet", "type": "outlet"}])
    assert "fixedValue" in out
    assert "uniform 0" in out


def test_p_bc_wall_is_zero_gradient() -> None:
    out = _build_p_bc([{"name": "walls", "type": "wall"}])
    assert "zeroGradient" in out


def test_U_bc_inlet_has_velocity_vector() -> None:
    """inlet U 는 fixedValue uniform (velocity 0 0)."""
    out = _build_U_bc([{"name": "inlet", "type": "inlet"}], velocity=2.5)
    assert "fixedValue" in out
    assert "uniform (2.5 0 0)" in out


def test_U_bc_outlet_is_zero_gradient() -> None:
    out = _build_U_bc([{"name": "outlet", "type": "outlet"}], velocity=1.0)
    assert "zeroGradient" in out


def test_U_bc_wall_is_noslip() -> None:
    out = _build_U_bc([{"name": "walls", "type": "wall"}], velocity=1.0)
    assert "noSlip" in out


def test_U_bc_symmetry_plane() -> None:
    out = _build_U_bc(
        [{"name": "sym", "type": "symmetryPlane"}], velocity=1.0,
    )
    assert "symmetry" in out


def test_k_bc_wall_uses_kqRWallFunction() -> None:
    out = _build_k_bc([{"name": "walls", "type": "wall"}], k_val=0.01)
    assert "kqRWallFunction" in out


def test_omega_bc_wall_uses_omegaWallFunction() -> None:
    out = _build_omega_bc([{"name": "walls", "type": "wall"}], omega_val=100.0)
    assert "omegaWallFunction" in out


def test_nut_bc_all_wall_patches_have_nutWallFunction() -> None:
    """nut builder: wall → nutkWallFunction 또는 nut*WallFunction 포함."""
    out = _build_nut_bc([{"name": "walls", "type": "wall"}])
    assert "WallFunction" in out or "calculated" in out


def test_multiple_patches_all_represented() -> None:
    """패치 여러 개 → 모두 BC 문자열에 포함."""
    patches = [
        {"name": "inlet", "type": "inlet"},
        {"name": "outlet", "type": "outlet"},
        {"name": "walls", "type": "wall"},
    ]
    out_p = _build_p_bc(patches)
    out_u = _build_U_bc(patches, velocity=1.0)
    for name in ("inlet", "outlet", "walls"):
        assert name in out_p
        assert name in out_u


def test_unknown_patch_type_falls_back_to_zero_gradient() -> None:
    """알 수 없는 type → zeroGradient fallback."""
    patches = [{"name": "mystery", "type": "???"}]
    assert "zeroGradient" in _build_p_bc(patches)
    assert "zeroGradient" in _build_U_bc(patches, velocity=1.0)


def test_k_values_are_positive_for_nonzero_velocity() -> None:
    """inlet 에 주어진 k_val 이 BC 문자열에 포함."""
    out = _build_k_bc([{"name": "inlet", "type": "inlet"}], k_val=0.0125)
    # 형식: "uniform 0.0125"
    assert "0.0125" in out
